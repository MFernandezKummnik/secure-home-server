"""kalender.py – spricht CalDAV mit Radicale: Kalender finden, suchen, eintragen, löschen."""

import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests

BERLIN = ZoneInfo("Europe/Berlin")
DAV = "{DAV:}"
CALDAV = "{urn:ietf:params:xml:ns:caldav}"

PROPFIND = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:"><d:prop><d:displayname/><d:resourcetype/></d:prop></d:propfind>"""

# "Gib mir alle Termine, die den Zeitraum berühren" – Standard-Abfrage von CalDAV
SUCHE = """<?xml version="1.0" encoding="utf-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop><d:getetag/><c:calendar-data/></d:prop>
  <c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">
    <c:time-range start="{start}" end="{ende}"/>
  </c:comp-filter></c:comp-filter></c:filter>
</c:calendar-query>"""

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/Berlin
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE"""


class Kalender:
    def __init__(self, basis_url: str, benutzer: str, passwort: str):
        # basis_url z. B. http://127.0.0.1:5232/<benutzer>/
        self.basis = basis_url.rstrip("/") + "/"
        self.auth = (benutzer, passwort)

    # --- Kalender finden ------------------------------------------------------
    def kalender_finden(self) -> dict[str, tuple[str, str]]:
        """{'uni': ('Uni', '/<benutzer>/abc.../'), ...} – Schlüssel klein, Wert: Anzeigename + Adresse"""
        antwort = requests.request(
            "PROPFIND", self.basis, data=PROPFIND, auth=self.auth, timeout=15,
            headers={"Depth": "1", "Content-Type": "application/xml"})
        antwort.raise_for_status()

        gefunden = {}
        for eintrag in ET.fromstring(antwort.content).iter(f"{DAV}response"):
            href = eintrag.findtext(f"{DAV}href", "")
            name = (eintrag.findtext(f".//{DAV}displayname", "") or "").strip()
            ist_kalender = eintrag.find(f".//{DAV}resourcetype/{CALDAV}calendar") is not None
            if ist_kalender and name:
                gefunden[name.lower()] = (name, href)
        return gefunden

    # --- Eintragen ------------------------------------------------------------
    def eintragen(self, kalender_name: str, titel: str, tag: date,
                  start: str = "", ende: str = "") -> None:
        """Legt einen Termin an. Ohne Startzeit wird er ganztägig."""
        treffer = self.kalender_finden().get(kalender_name.lower())
        if treffer is None:
            raise ValueError(f"Kalender '{kalender_name}' gibt es auf dem Server nicht.")

        uid = str(uuid.uuid4())
        ziel = urljoin(self.basis, treffer[1]) + f"{uid}.ics"
        antwort = requests.put(
            ziel, data=_ics_bauen(uid, titel, tag, start, ende).encode("utf-8"),
            auth=self.auth, timeout=15,
            headers={"Content-Type": "text/calendar; charset=utf-8",
                     "If-None-Match": "*"})        # niemals einen bestehenden Termin überschreiben
        antwort.raise_for_status()

    # --- Suchen ---------------------------------------------------------------
    def termine(self, von: datetime, bis: datetime) -> list[dict]:
        """Alle Termine aller Kalender im Zeitraum, Wiederholungen einzeln aufgelöst."""
        utc = {"start": f"{von.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}",
               "ende":  f"{bis.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}"}
        ergebnis = []

        for anzeigename, href in self.kalender_finden().values():
            antwort = requests.request(
                "REPORT", urljoin(self.basis, href), data=SUCHE.format(**utc),
                auth=self.auth, timeout=15,
                headers={"Depth": "1", "Content-Type": "application/xml"})
            antwort.raise_for_status()

            for eintrag in ET.fromstring(antwort.content).iter(f"{DAV}response"):
                datei = eintrag.findtext(f"{DAV}href", "")
                etag = eintrag.findtext(f".//{DAV}getetag", "")
                daten = eintrag.findtext(f".//{CALDAV}calendar-data", "")
                if not daten:
                    continue
                cal = icalendar.Calendar.from_ical(daten)
                serie = any("RRULE" in e for e in cal.walk("VEVENT"))

                # Aus Wiederholungsregeln die einzelnen Termine im Zeitraum berechnen
                for ev in recurring_ical_events.of(cal).between(von, bis):
                    ergebnis.append(_termin(ev, anzeigename, datei, etag, serie))

        return sorted(ergebnis, key=lambda t: t["sortierung"])

    # --- Löschen --------------------------------------------------------------
    def loeschen(self, datei: str, etag: str) -> None:
        """Löscht genau diese Datei – aber nur, wenn sie seit der Suche unverändert ist."""
        kopf = {"If-Match": etag} if etag else {}
        antwort = requests.delete(urljoin(self.basis, datei), auth=self.auth,
                                  timeout=15, headers=kopf)
        antwort.raise_for_status()


def _termin(ev, kalender: str, datei: str, etag: str, serie: bool) -> dict:
    """Macht aus einem icalendar-Ereignis ein einfaches Dictionary."""
    beginn = ev["DTSTART"].dt
    ende = ev["DTEND"].dt if "DTEND" in ev else beginn
    ganztaegig = not isinstance(beginn, datetime)
    if not ganztaegig:
        beginn = beginn.astimezone(BERLIN) if beginn.tzinfo else beginn.replace(tzinfo=BERLIN)
        ende = ende.astimezone(BERLIN) if ende.tzinfo else ende.replace(tzinfo=BERLIN)
    return {
        "titel": str(ev.get("SUMMARY", "(ohne Titel)")),
        "ort": str(ev.get("LOCATION", "")),
        "kalender": kalender,
        "tag": beginn if ganztaegig else beginn.date(),
        "start": "" if ganztaegig else f"{beginn:%H:%M}",
        "ende": "" if ganztaegig else f"{ende:%H:%M}",
        "serie": serie,
        "datei": datei,
        "etag": etag,
        # Ganztägiges zuerst, dann nach Uhrzeit
        "sortierung": (beginn if ganztaegig else beginn.date(), "" if ganztaegig else f"{beginn:%H:%M}"),
    }


def _ics_escape(text: str) -> str:
    """Sonderzeichen, die im iCalendar-Format eine Bedeutung haben, maskieren."""
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))


def _ics_bauen(uid: str, titel: str, tag: date, start: str, ende: str) -> str:
    stempel = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zeilen = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Heimserver//Kalenderbot//DE"]

    if start:
        beginn = datetime.combine(tag, datetime.strptime(start, "%H:%M").time())
        schluss = (datetime.combine(tag, datetime.strptime(ende, "%H:%M").time())
                   if ende else beginn + timedelta(hours=1))
        if schluss <= beginn:                       # z. B. 22:00 bis 01:00
            schluss += timedelta(days=1)
        zeilen.append(VTIMEZONE)
        zeit = [f"DTSTART;TZID=Europe/Berlin:{beginn:%Y%m%dT%H%M%S}",
                f"DTEND;TZID=Europe/Berlin:{schluss:%Y%m%dT%H%M%S}"]
    else:
        # Ganztägig: Ende ist laut Standard der FOLGENDE Tag (exklusiv)
        zeit = [f"DTSTART;VALUE=DATE:{tag:%Y%m%d}",
                f"DTEND;VALUE=DATE:{tag + timedelta(days=1):%Y%m%d}"]

    zeilen += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stempel}",
               f"SUMMARY:{_ics_escape(titel)}", *zeit, "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(zeilen) + "\r\n"
