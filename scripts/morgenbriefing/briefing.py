#!/usr/bin/env python3
"""Morgenbriefing: Termine, Abgaben und Wetter jeden Morgen per Matrix aufs Handy.

Ablauf: Radicale-Kalender (CalDAV) abfragen -> Wetter von Open-Meteo holen ->
kurze Textnachricht bauen -> als kalenderbot in den Matrix-Raum "Morgenbriefing" schicken.

Aufruf:
  python briefing.py          # Nachricht an Matrix schicken
  python briefing.py --test   # Nachricht nur im Terminal anzeigen, nichts senden

Entstanden mit KI-Hilfe (Claude); Code durchgesehen und verstanden von Miguel.
"""
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import caldav
import requests

TZ = ZoneInfo("Europe/Berlin")
WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
WOCHENTAGE_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]

# WMO-Wettercodes, wie Open-Meteo sie liefert, auf Deutsch
WETTER = {
    0: "klar", 1: "überwiegend klar", 2: "teils bewölkt", 3: "bedeckt",
    45: "Nebel", 48: "Nebel mit Reif",
    51: "leichter Niesel", 53: "Niesel", 55: "starker Niesel",
    56: "gefrierender Niesel", 57: "gefrierender Niesel",
    61: "leichter Regen", 63: "Regen", 65: "starker Regen",
    66: "gefrierender Regen", 67: "gefrierender Regen",
    71: "leichter Schneefall", 73: "Schneefall", 75: "starker Schneefall", 77: "Schneegriesel",
    80: "leichte Schauer", 81: "Schauer", 82: "heftige Schauer",
    85: "Schneeschauer", 86: "starke Schneeschauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "Gewitter mit Hagel",
}


def env(name):
    """Pflicht-Einstellung aus briefing.env lesen; bricht mit klarer Meldung ab, wenn sie fehlt."""
    wert = os.environ.get(name, "").strip()
    if not wert:
        sys.exit(f"Fehlt in briefing.env: {name}")
    return wert


# ---------------------------------------------------------------- Kalender

def termine_holen(von, bis):
    """Alle Termine zwischen von und bis aus allen Radicale-Kalendern, nach Beginn sortiert."""
    client = caldav.DAVClient(url=env("RADICALE_URL"),
                              username=env("RADICALE_USER"),
                              password=env("RADICALE_PASSWORD"))
    termine = []
    for kalender in client.principal().calendars():
        # expand=True: Serientermine (z. B. wöchentliche Vorlesung) werden in Einzeltermine aufgelöst
        for eintrag in kalender.search(start=von, end=bis, event=True, expand=True):
            for ev in eintrag.icalendar_instance.walk("VEVENT"):
                beginn = ev.decoded("DTSTART")
                ganztags = not isinstance(beginn, datetime)  # reines Datum = ganztägiger Termin
                if ganztags:
                    beginn = datetime.combine(beginn, dtime.min, tzinfo=TZ)
                elif beginn.tzinfo is None:
                    beginn = beginn.replace(tzinfo=TZ)
                else:
                    beginn = beginn.astimezone(TZ)
                termine.append({
                    "titel": str(ev.get("SUMMARY", "(ohne Titel)")),
                    "ort": str(ev.get("LOCATION", "")),
                    "beginn": beginn,
                    "ganztags": ganztags,
                })
    termine.sort(key=lambda t: t["beginn"])
    return termine


def ist_abgabe(termin, woerter):
    titel = termin["titel"].lower()
    return any(w in titel for w in woerter)


def kalender_teile(tag_start):
    """Baut die Abschnitte 'Heute' und 'Abgaben' für die Nachricht."""
    morgen = tag_start + timedelta(days=1)
    ende = tag_start + timedelta(days=8)          # heute + die nächsten 7 Tage
    woerter = [w.strip().lower() for w in
               os.environ.get("ABGABE_WORTE", "Abgabe,Deadline,Frist,Klausur,Prüfung").split(",")
               if w.strip()]

    termine = termine_holen(tag_start, ende)
    heute = [t for t in termine if t["beginn"] < morgen]
    # Ist ABGABE_WORTE leer, erscheinen alle Termine der nächsten 7 Tage
    spaeter = [t for t in termine if t["beginn"] >= morgen and (not woerter or ist_abgabe(t, woerter))]

    zeilen = ["📅 Heute"]
    if not heute:
        zeilen.append("• Keine Termine.")
    for t in heute:
        if t["ganztags"]:
            zeit = "ganztägig"
        elif t["beginn"] < tag_start:
            zeit = "läuft noch"                     # mehrtägiger Termin, der vor heute begann
        else:
            zeit = t["beginn"].strftime("%H:%M")
        merker = "❗ " if woerter and ist_abgabe(t, woerter) else ""
        ort = f" ({t['ort']})" if t["ort"] else ""
        zeilen.append(f"• {zeit} {merker}{t['titel']}{ort}")

    letzter = ende - timedelta(days=1)
    zeilen.append("")
    zeilen.append(f"📝 Abgaben bis {WOCHENTAGE_KURZ[letzter.weekday()]} {letzter:%d.%m.}")
    if not spaeter:
        zeilen.append("• Nichts fällig.")
    for t in spaeter:
        b = t["beginn"]
        datum = f"{WOCHENTAGE_KURZ[b.weekday()]} {b:%d.%m.}"
        if not t["ganztags"]:
            datum += f", {b:%H:%M}"
        tage = (b.date() - tag_start.date()).days
        zeilen.append(f"• {datum} – {t['titel']} (in {tage} {'Tag' if tage == 1 else 'Tagen'})")
    return "\n".join(zeilen)


# ---------------------------------------------------------------- Wetter

def wetter_holen():
    """Tagesvorhersage von Open-Meteo (kostenlos, kein Konto, kein API-Schlüssel)."""
    params = {
        "latitude": env("BREITE"),
        "longitude": env("LAENGE"),
        "timezone": "Europe/Berlin",
        "forecast_days": 1,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "hourly": "precipitation_probability",
    }
    antwort = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=20)
    antwort.raise_for_status()
    daten = antwort.json()

    tag = daten["daily"]
    tief, hoch = round(tag["temperature_2m_min"][0]), round(tag["temperature_2m_max"][0])
    text = f"🌤 Stockach: {WETTER.get(tag['weather_code'][0], 'wechselhaft')}, {tief} bis {hoch} °C"

    # Stunden zwischen 6 und 22 Uhr mit mindestens 50 % Regenwahrscheinlichkeit
    regen = [int(zeit[11:13])
             for zeit, prozent in zip(daten["hourly"]["time"], daten["hourly"]["precipitation_probability"])
             if prozent is not None and prozent >= 50 and 6 <= int(zeit[11:13]) <= 22]
    if regen:
        text += f"\n☂️ Schirm einpacken: Regen wahrscheinlich etwa {regen[0]}–{regen[-1] + 1} Uhr"
    if tief <= 1:
        text += "\n🧊 Frostig: Glätte möglich"
    return text


# ---------------------------------------------------------------- Zeitung

def zeitung_hinweis(heute):
    """Nur mittwochs: prüft, ob der Zeitungslauf von 4 Uhr eine neue Ausgabe abgelegt hat."""
    if heute.weekday() != 2:
        return None
    ordner = os.environ.get("ZEITUNG_ORDNER", "").strip()
    if not ordner:
        return "📰 Die neue Wochenzeitung sollte auf dem Boox liegen."
    try:
        neu = [p for p in Path(ordner).iterdir()
               if p.is_file() and time.time() - p.stat().st_mtime < 6 * 3600]
    except OSError:
        return "⚠️ Zeitungsordner nicht lesbar – Pfad in briefing.env prüfen."
    if neu:
        return f"📰 Neue Wochenzeitung liegt bereit ({neu[0].name})."
    return "⚠️ Heute ist keine neue Zeitung erschienen – Lauf von 4 Uhr prüfen."


# ---------------------------------------------------------------- Matrix

def an_matrix(text):
    """Schickt die Nachricht als kalenderbot in den Raum (Matrix Client-Server-API)."""
    server = env("MATRIX_HOMESERVER").rstrip("/")
    raum = quote(env("MATRIX_RAUM_ID"), safe="")
    url = f"{server}/_matrix/client/v3/rooms/{raum}/send/m.room.message/{uuid.uuid4()}"
    antwort = requests.put(url,
                           json={"msgtype": "m.text", "body": text},
                           headers={"Authorization": f"Bearer {env('MATRIX_TOKEN')}"},
                           timeout=20)
    antwort.raise_for_status()


# ---------------------------------------------------------------- Hauptprogramm

def main():
    testlauf = "--test" in sys.argv
    jetzt = datetime.now(TZ)
    heute = jetzt.date()
    tag_start = datetime.combine(heute, dtime.min, tzinfo=TZ)

    teile = [f"☀️ Guten Morgen! {WOCHENTAGE[heute.weekday()]}, {heute.day}. {MONATE[heute.month - 1]}"]

    # Jeder Abschnitt fängt seine Fehler selbst ab: fällt das Wetter aus,
    # kommen die Termine trotzdem an (und umgekehrt).
    try:
        teile.append(wetter_holen())
    except Exception as fehler:
        teile.append(f"🌤 Wetter gerade nicht abrufbar ({type(fehler).__name__}).")

    try:
        teile.append(kalender_teile(tag_start))
    except Exception as fehler:
        teile.append(f"📅 Kalender nicht erreichbar ({type(fehler).__name__}: {fehler}).")

    hinweis = zeitung_hinweis(heute)
    if hinweis:
        teile.append(hinweis)

    text = "\n\n".join(teile)
    if testlauf:
        print(text)
    else:
        an_matrix(text)
        print(f"{jetzt:%d.%m.%Y %H:%M} Morgenbriefing gesendet.")


if __name__ == "__main__":
    main()
