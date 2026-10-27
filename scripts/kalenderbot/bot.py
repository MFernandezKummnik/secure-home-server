"""bot.py – Matrix-Kalenderbot

Ablauf:  Nachricht → KI zerlegt sie in Felder → Code rechnet das Datum
         → je nach Aktion: eintragen (mit Rückfrage), löschen (Auswahl per Nummer)
           oder Termine anzeigen.
"""

import asyncio
import json
import logging
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from nio import (AsyncClient, LoginResponse, MatrixRoom, RoomCreateResponse,
                 RoomMessageText, RoomPreset, RoomVisibility, WhoamiResponse)

from datum import datum_anzeigen, datum_berechnen, zeitraum_berechnen
from kalender import BERLIN, Kalender
from verstehen import KALENDER, nachricht_verstehen

# --- Einstellungen (kommen als Umgebungsvariablen aus docker run) ----------
MATRIX_URL         = os.environ["MATRIX_URL"]           # http://127.0.0.1:8008
MATRIX_BENUTZER    = os.environ["MATRIX_BENUTZER"]      # @kalenderbot:...
MATRIX_PASSWORT    = os.environ["MATRIX_PASSWORT"]
ERLAUBTER_BENUTZER = os.environ["ERLAUBTER_BENUTZER"]   # @<du>:<server>
OLLAMA_URL         = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODELL             = os.environ.get("MODELL", "qwen3.5:4b")
CALDAV_URL         = os.environ["CALDAV_URL"]           # http://127.0.0.1:5232/<benutzer>/
CALDAV_BENUTZER    = os.environ["CALDAV_BENUTZER"]
CALDAV_PASSWORT    = os.environ["CALDAV_PASSWORT"]
DATEN_DIR          = Path(os.environ.get("DATEN_DIR", "/daten"))
SITZUNG            = DATEN_DIR / "sitzung.json"
BESTAETIGEN_MINUTEN = 10
LOESCHEN_SUCHTAGE   = 60      # beim Löschen ohne Datum: so weit in die Zukunft suchen
MAX_TREFFER         = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kalenderbot")

HILFE = (
    "Das kann ich:\n\n"
    "Eintragen:\n"
    "• nächste Woche Dienstag Abgabe ALDA\n"
    "• morgen 18 Uhr Schicht im Restaurant bis 23 Uhr\n\n"
    "Abfragen:\n"
    "• was steht morgen an?\n"
    "• was habe ich diese Woche / nächste Woche?\n\n"
    "Löschen:\n"
    "• lösche Abgabe ALDA\n"
    "• lösch den Zahnarzt am Freitag\n\n"
    f"Kalender: {', '.join(KALENDER)}. Vor dem Eintragen und Löschen frage ich immer nach.\n"
    "Wiederkehrende Termine (Vorlesungen, Gym) löschst du bitte in der Kalender-App."
)

JA = {"ja", "j", "ok", "yes", "passt", "👍", "✅"}
NEIN = {"nein", "n", "no", "abbrechen", "stop", "❌"}


class Bot:
    def __init__(self):
        self.client = AsyncClient(MATRIX_URL, MATRIX_BENUTZER)
        self.kalender = Kalender(CALDAV_URL, CALDAV_BENUTZER, CALDAV_PASSWORT)
        self.offen: dict[str, dict] = {}      # Raum-ID → Vorschlag, der auf Antwort wartet
        self.start_ms = int(time.time() * 1000)
        self.sitzung: dict = {}

    # --- Anmeldung -----------------------------------------------------------
    async def anmelden(self):
        """Gespeicherte Sitzung wiederverwenden, sonst neu mit Passwort anmelden."""
        if SITZUNG.exists():
            self.sitzung = json.loads(SITZUNG.read_text())
            self.client.restore_login(MATRIX_BENUTZER, self.sitzung["device_id"],
                                      self.sitzung["access_token"])
            if isinstance(await self.client.whoami(), WhoamiResponse):
                log.info("Mit gespeicherter Sitzung angemeldet")
                return
            log.warning("Gespeicherte Sitzung ungültig, melde neu an")

        antwort = await self.client.login(MATRIX_PASSWORT, device_name="kalenderbot")
        if not isinstance(antwort, LoginResponse):
            await self.beenden(f"Anmeldung fehlgeschlagen: {antwort}")
        self.sitzung = {"device_id": antwort.device_id, "access_token": antwort.access_token}
        self._sitzung_speichern()
        log.info("Neu angemeldet")

    def _sitzung_speichern(self):
        DATEN_DIR.mkdir(parents=True, exist_ok=True)
        SITZUNG.write_text(json.dumps(self.sitzung))
        SITZUNG.chmod(0o600)           # enthält den Zugangsschlüssel des Bots

    async def beenden(self, grund: str):
        """Verbindung sauber schließen und mit Fehlermeldung aufhören."""
        await self.client.close()
        raise SystemExit(grund)

    # --- Raum ----------------------------------------------------------------
    async def raum_sicherstellen(self):
        """Eigenen, unverschlüsselten Raum anlegen, falls es noch keinen gibt."""
        raum_id = self.sitzung.get("raum_id")
        if raum_id and raum_id in self.client.rooms:
            return
        antwort = await self.client.room_create(
            visibility=RoomVisibility.private, name="Kalender", is_direct=True,
            preset=RoomPreset.trusted_private_chat, invite=[ERLAUBTER_BENUTZER],
            federate=False)
        if not isinstance(antwort, RoomCreateResponse):
            await self.beenden(f"Raum konnte nicht angelegt werden: {antwort}")
        self.sitzung["raum_id"] = antwort.room_id
        self._sitzung_speichern()
        log.info("Raum angelegt, Einladung an %s verschickt", ERLAUBTER_BENUTZER)

    async def senden(self, raum_id: str, text: str):
        await self.client.room_send(raum_id, "m.room.message",
                                    {"msgtype": "m.text", "body": text})

    # --- Nachrichten ---------------------------------------------------------
    async def nachricht(self, raum: MatrixRoom, event: RoomMessageText):
        # Nur neue Nachrichten, nur von dir, nur im eigenen Raum
        if event.server_timestamp < self.start_ms:
            return
        if event.sender != ERLAUBTER_BENUTZER:
            return
        if raum.room_id != self.sitzung.get("raum_id"):
            return

        raum_id = raum.room_id
        text = event.body.strip()
        kurz = text.lower().rstrip(".!")
        offen = self.offen.get(raum_id)

        # Offenen Vorschlag verwerfen, wenn er zu alt ist
        if offen and time.time() - offen["zeit"] > BESTAETIGEN_MINUTEN * 60:
            self.offen.pop(raum_id)
            offen = None

        if offen and kurz in NEIN:
            self.offen.pop(raum_id)
            await self.senden(raum_id, "Abgebrochen, nichts geändert.")
        elif offen and offen["art"] == "eintragen" and kurz in JA:
            self.offen.pop(raum_id)
            await self.eintragen_bestaetigt(raum_id, offen)
        elif offen and offen["art"] == "loeschen" and kurz.isdigit():
            await self.loeschen_bestaetigt(raum_id, offen, int(kurz))
        elif kurz in {"hilfe", "help", "?"}:
            await self.senden(raum_id, HILFE)
        else:
            self.offen.pop(raum_id, None)       # neue Anfrage ersetzt alte Rückfrage
            await self.verarbeiten(raum_id, text)

    async def verarbeiten(self, raum_id: str, text: str):
        heute = datetime.now(BERLIN).date()
        try:
            # requests blockiert – darum in einem eigenen Thread, damit der Bot reaktionsfähig bleibt
            felder = await asyncio.to_thread(nachricht_verstehen, text, heute, OLLAMA_URL, MODELL)
        except Exception as fehler:
            log.exception("KI-Anfrage fehlgeschlagen")
            await self.senden(raum_id, f"Die KI ist gerade nicht erreichbar ({type(fehler).__name__}).")
            return
        log.info("KI hat erkannt: %s", felder)

        aktion = felder.get("aktion")
        try:
            if aktion == "abfragen":
                await self.abfragen(raum_id, felder, heute)
            elif aktion == "loeschen":
                await self.loeschen_suchen(raum_id, felder, heute)
            else:
                await self.eintragen_vorschlagen(raum_id, felder, heute)
        except Exception as fehler:
            log.exception("Kalender-Zugriff fehlgeschlagen")
            await self.senden(raum_id, f"❌ Kalender nicht erreichbar: {type(fehler).__name__}")

    # --- Eintragen -----------------------------------------------------------
    async def eintragen_vorschlagen(self, raum_id: str, felder: dict, heute: date):
        tag = datum_berechnen(felder, heute)
        titel = felder.get("titel", "").strip()
        if not titel or tag is None:
            await self.senden(raum_id, "Das habe ich nicht ganz verstanden. Wann ist der Termin, "
                                       "und wie soll er heißen? (\"hilfe\" zeigt Beispiele)")
            return

        kalender = felder.get("kalender")
        if kalender not in KALENDER:
            kalender = "Privat"
        start, ende = felder.get("start", ""), felder.get("ende", "")
        if not _uhrzeit_ok(start) or (ende and not _uhrzeit_ok(ende)):
            start, ende = "", ""

        vorschlag = {"art": "eintragen", "titel": titel, "tag": tag, "start": start,
                     "ende": ende, "kalender": kalender, "zeit": time.time()}
        self.offen[raum_id] = vorschlag
        await self.senden(raum_id, f"📅 {_beschreiben(vorschlag)}\n\n"
                                   "Eintragen? Antworte mit ja oder nein.")

    async def eintragen_bestaetigt(self, raum_id: str, v: dict):
        try:
            await asyncio.to_thread(self.kalender.eintragen, v["kalender"], v["titel"],
                                    v["tag"], v["start"], v["ende"])
        except Exception as fehler:
            log.exception("Eintragen fehlgeschlagen")
            await self.senden(raum_id, f"❌ Eintragen fehlgeschlagen: {fehler}")
            return
        log.info("Eingetragen: %s", v["titel"])
        await self.senden(raum_id, f"✅ Eingetragen: {_beschreiben(v)}")

    # --- Abfragen ------------------------------------------------------------
    async def abfragen(self, raum_id: str, felder: dict, heute: date):
        zeitraum = zeitraum_berechnen(felder, heute)
        if zeitraum is None:
            await self.senden(raum_id, "Welchen Tag meinst du? (\"hilfe\" zeigt Beispiele)")
            return
        von, bis = zeitraum
        termine = await asyncio.to_thread(self.kalender.termine, _mitternacht(von), _mitternacht(bis))

        letzter_tag = bis - timedelta(days=1)
        if von == letzter_tag:
            ueberschrift = datum_anzeigen(von)
        else:
            ueberschrift = f"{datum_anzeigen(von)} bis {datum_anzeigen(letzter_tag)}"
        if not termine:
            await self.senden(raum_id, f"📆 {ueberschrift}: keine Termine.")
            return

        # Nach Tagen gruppieren
        zeilen, aktueller_tag = [f"📆 {ueberschrift}"], None
        for t in termine:
            if t["tag"] != aktueller_tag and von != letzter_tag:
                zeilen.append(f"\n{datum_anzeigen(t['tag'])}")
                aktueller_tag = t["tag"]
            zeilen.append(f"• {_termin_zeile(t)}")
        await self.senden(raum_id, "\n".join(zeilen))

    # --- Löschen -------------------------------------------------------------
    async def loeschen_suchen(self, raum_id: str, felder: dict, heute: date):
        suchbegriff = felder.get("titel", "").strip()
        if not suchbegriff:
            await self.senden(raum_id, "Welchen Termin soll ich löschen?")
            return

        # Mit Datum: nur dieser Tag. Ohne Datum: die nächsten Wochen.
        tag = datum_berechnen(felder, heute) if felder.get("tag") != "unklar" else None
        von, bis = (tag, tag + timedelta(days=1)) if tag else \
                   (heute, heute + timedelta(days=LOESCHEN_SUCHTAGE))
        termine = await asyncio.to_thread(self.kalender.termine, _mitternacht(von), _mitternacht(bis))

        # Alle Wörter des Suchbegriffs müssen im Titel vorkommen, Groß/klein egal
        woerter = suchbegriff.lower().split()
        passend = [t for t in termine if all(w in t["titel"].lower() for w in woerter)]
        einzeln = [t for t in passend if not t["serie"]][:MAX_TREFFER]

        if not passend:
            await self.senden(raum_id, f"Keinen kommenden Termin mit „{suchbegriff}“ gefunden.")
            return
        if not einzeln:
            await self.senden(raum_id, f"„{suchbegriff}“ gehört zu einem wiederkehrenden Termin. "
                                       "Den löschst du bitte in der Kalender-App, dort kannst du "
                                       "zwischen einem Termin und der ganzen Serie wählen.")
            return

        self.offen[raum_id] = {"art": "loeschen", "treffer": einzeln, "zeit": time.time()}
        liste = "\n".join(f"{i}. {_termin_zeile(t, mit_datum=True)}" for i, t in enumerate(einzeln, 1))
        await self.senden(raum_id, f"Gefunden:\n{liste}\n\n"
                                   "Welchen löschen? Antworte mit der Nummer oder nein.")

    async def loeschen_bestaetigt(self, raum_id: str, offen: dict, nummer: int):
        treffer = offen["treffer"]
        if not 1 <= nummer <= len(treffer):
            await self.senden(raum_id, f"Bitte eine Nummer von 1 bis {len(treffer)} oder nein.")
            return
        self.offen.pop(raum_id)
        t = treffer[nummer - 1]
        try:
            await asyncio.to_thread(self.kalender.loeschen, t["datei"], t["etag"])
        except Exception as fehler:
            log.exception("Löschen fehlgeschlagen")
            await self.senden(raum_id, f"❌ Löschen fehlgeschlagen: {fehler}\n"
                                       "Wurde der Termin inzwischen geändert? Dann such ihn nochmal.")
            return
        log.info("Gelöscht: %s", t["titel"])
        await self.senden(raum_id, f"🗑️ Gelöscht: {_termin_zeile(t, mit_datum=True)}")

    # --- Start ---------------------------------------------------------------
    async def starten(self):
        await self.anmelden()
        await self.client.sync(timeout=10000, full_state=True)   # Räume kennenlernen
        await self.raum_sicherstellen()
        self.client.add_event_callback(self.nachricht, RoomMessageText)
        log.info("Bereit, warte auf Nachrichten")
        await self.client.sync_forever(timeout=30000)


# --- Hilfsfunktionen ---------------------------------------------------------
def _mitternacht(tag: date) -> datetime:
    return datetime(tag.year, tag.month, tag.day, tzinfo=BERLIN)


def _uhrzeit_ok(text: str) -> bool:
    try:
        stunde, minute = (int(x) for x in text.split(":"))
        return 0 <= stunde < 24 and 0 <= minute < 60
    except ValueError:
        return False


def _zeit(start: str, ende: str) -> str:
    if not start:
        return "ganztägig"
    return f"{start}–{ende} Uhr" if ende else f"ab {start} Uhr"


def _beschreiben(v: dict) -> str:
    return (f"{v['titel']} · {datum_anzeigen(v['tag'])} · {_zeit(v['start'], v['ende'])}"
            f" · Kalender {v['kalender']}")


def _termin_zeile(t: dict, mit_datum: bool = False) -> str:
    teile = [datum_anzeigen(t["tag"])] if mit_datum else []
    teile += [_zeit(t["start"], t["ende"]), t["titel"]]
    zusatz = t["kalender"] + (f", {t['ort']}" if t["ort"] else "")
    return " · ".join(teile) + f" ({zusatz})"


if __name__ == "__main__":
    asyncio.run(Bot().starten())
