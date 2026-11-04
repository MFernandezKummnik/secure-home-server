#!/usr/bin/env python3
"""karteikarten.py – Anki-Karteikarten aus Vorlesungsfolien (PDF) erstellen

    Semester2/<Fach>/Folien/<Vorlesung>.pdf
      → Text pro Folie (pdftotext)
      → KI erstellt Karten, immer ein paar Folien auf einmal
      → Semester2/<Fach>/Karteikarten/<Vorlesung>.apkg  (zum Import in AnkiDroid)
      → Semester2/<Fach>/Karteikarten/<Vorlesung>.md    (Vorschau zum Durchsehen)

Jede PDF wird nur einmal verarbeitet. Ändert sich die Datei (neue Version der
Folien), wird sie neu verarbeitet. Die KI ist umschaltbar: lokal per Ollama
oder über eine Cloud-API, die das OpenAI-Format spricht.
"""

import hashlib
import html
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import genanki
import requests

# --- Einstellungen (alle per Umgebungsvariable änderbar) ---------------
SKRIPT_DIR = Path(__file__).resolve().parent
SEMESTER = Path(os.environ.get("SEMESTER", "/semester"))          # = /mnt/user/Semester2
FOLIEN_ORDNER = os.environ.get("FOLIEN_ORDNER", "Folien")
KARTEN_ORDNER = os.environ.get("KARTEN_ORDNER", "Karteikarten")
STAPEL_OBEN = os.environ.get("STAPEL_OBEN", "Semester2")           # oberster Anki-Stapel

KI_ANBIETER = os.environ.get("KI_ANBIETER", "ollama")              # "ollama", "anthropic" oder "openai"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
API_URL = os.environ.get("API_URL", "https://api.anthropic.com/v1" if KI_ANBIETER == "anthropic"
                         else "https://api.openai.com/v1")         # nur für Cloud-Anbieter
API_SCHLUESSEL = os.environ.get("API_SCHLUESSEL", "")              # nur für Cloud-Anbieter
MODELL = os.environ.get("MODELL", "qwen3.5:9b")
KONTEXT = int(os.environ.get("KONTEXT", "8192"))                   # nur Ollama

FOLIEN_PRO_ABSCHNITT = int(os.environ.get("FOLIEN_PRO_ABSCHNITT", "6"))
MAX_ZEICHEN_PRO_ABSCHNITT = int(os.environ.get("MAX_ZEICHEN_PRO_ABSCHNITT", "6000"))
MAX_KARTEN_PRO_ABSCHNITT = int(os.environ.get("MAX_KARTEN_PRO_ABSCHNITT", "8"))
MIN_ZEICHEN_PRO_FOLIE = 40          # weniger Text = Titel- oder reine Bildfolie
VERSUCHE = 3
MIN_ALTER_MINUTEN = int(os.environ.get("MIN_ALTER_MINUTEN", "10"))  # PDF wird evtl. noch synchronisiert
ERZWINGEN = os.environ.get("ERZWINGEN", "0") == "1"                 # alle PDFs neu verarbeiten
NUR = os.environ.get("NUR", "").lower()     # nur PDFs, deren Pfad diesen Text enthält (zum Testen)
# Fächer ohne Karteikarten, durch Komma getrennt, z. B. "Mathematik2" (Übungsfach)
AUSLASSEN = {f.strip().lower() for f in os.environ.get("AUSLASSEN", "").split(",") if f.strip()}

DATEN_DIR = SKRIPT_DIR / "daten"
STATUS_DATEI = DATEN_DIR / "erledigt.json"    # Pfad der PDF → Prüfsumme der verarbeiteten Version
LOG_DIR = SKRIPT_DIR / "logs"
SPERRE = SKRIPT_DIR / ".laeuft"
LOGS_BEHALTEN = 20

# Feste IDs: Anki erkennt daran beim erneuten Import "dieselbe Kartenart".
# Einmal zufällig gewählt – NIE ändern, sonst entstehen doppelte Notiztypen.
NOTIZTYP_ID = 2049444930

# Die KI muss genau diese Struktur liefern ("structured output").
SCHEMA = {
    "type": "object",
    "properties": {
        "karten": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "frage":   {"type": "string"},
                    "antwort": {"type": "string"},
                    "folie":   {"type": "integer"},
                },
                "required": ["frage", "antwort", "folie"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["karten"],
    "additionalProperties": False,
}


# --- Ausgabe: gleichzeitig auf den Bildschirm und ins Log ---------------
class Log:
    def __init__(self, datei: Path):
        self.datei = open(datei, "a", encoding="utf-8")

    def __call__(self, text: str = "") -> None:
        print(text, flush=True)
        self.datei.write(text + "\n")
        self.datei.flush()


# --- Hilfsfunktionen ----------------------------------------------------
def pruefsumme(datei: Path) -> str:
    """SHA-256 der Datei – ändert sich, sobald sich auch nur ein Byte ändert."""
    h = hashlib.sha256()
    with open(datei, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def atomar_schreiben(ziel: Path, inhalt: bytes) -> None:
    """Erst in eine temporäre Datei im selben Ordner, dann umbenennen.
    So sehen Syncthing und AnkiDroid nie eine halb geschriebene Datei."""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ziel.parent, prefix=".tmp-", suffix=ziel.suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(inhalt)
        # mkstemp legt Dateien nur für den Besitzer lesbar an (0600) – dann käme
        # z. B. SMB nicht dran. Deshalb die üblichen Rechte wie bei jeder neuen Datei.
        maske = os.umask(0)
        os.umask(maske)
        os.chmod(tmp, 0o666 & ~maske)
        os.replace(tmp, ziel)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    if ziel.stat().st_size == 0:
        raise OSError(f"{ziel} ist nach dem Schreiben leer")


def beschreibbar(ordner: Path) -> bool:
    """Prüft vorab, ob wir in den Ordner schreiben dürfen (legt ihn bei Bedarf an)."""
    try:
        ordner.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(ordner, os.W_OK)


def folien_lesen(pdf: Path) -> list[str]:
    """Text jeder Folie. pdftotext trennt Seiten mit einem Seitenvorschub (\\f)."""
    ergebnis = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
        capture_output=True, timeout=300, check=True,
    )
    seiten = ergebnis.stdout.decode("utf-8", errors="replace").split("\f")
    if seiten and not seiten[-1].strip():
        seiten.pop()                               # nach der letzten Seite steht auch ein \f
    seiten_zeilen = [[re.sub(r"[ \t]{2,}", "  ", z).strip() for z in seite.splitlines()]
                     for seite in seiten]

    # Kopf- und Fußzeilen (z. B. "Autor, Buchtitel ©2025") stehen auf fast jeder Folie.
    # Sie bringen dem Modell nichts und kosten Platz im Kontextfenster.
    # Regel: Zeilen ab 15 Zeichen, die auf mindestens der Hälfte der Folien vorkommen.
    # (Kurze Zeilen wie "}" in Code-Beispielen bleiben dadurch unangetastet.)
    vorkommen: dict[str, int] = {}
    for zeilen in seiten_zeilen:
        for zeile in set(zeilen):
            if len(zeile) >= 15:
                vorkommen[zeile] = vorkommen.get(zeile, 0) + 1
    wiederholt = ({z for z, n in vorkommen.items() if n >= len(seiten_zeilen) / 2}
                  if len(seiten_zeilen) >= 4 else set())

    bereinigt = []
    for zeilen in seiten_zeilen:
        text = "\n".join(z for z in zeilen if z not in wiederholt)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        bereinigt.append(text)
    return bereinigt


def abschnitte_bilden(folien: list[str]) -> list[list[tuple[int, str]]]:
    """Teilt die Folien in kleine Gruppen, damit jede Anfrage ins Kontextfenster passt.
    Folien mit (fast) keinem Text werden ausgelassen."""
    abschnitte, aktuell, zeichen = [], [], 0
    for nummer, text in enumerate(folien, start=1):
        if len(text) < MIN_ZEICHEN_PRO_FOLIE:
            continue
        text = text[:MAX_ZEICHEN_PRO_ABSCHNITT]    # einzelne Riesenfolie kappen
        if aktuell and (len(aktuell) >= FOLIEN_PRO_ABSCHNITT
                        or zeichen + len(text) > MAX_ZEICHEN_PRO_ABSCHNITT):
            abschnitte.append(aktuell)
            aktuell, zeichen = [], 0
        aktuell.append((nummer, text))
        zeichen += len(text)
    if aktuell:
        abschnitte.append(aktuell)
    return abschnitte


# --- KI-Anfrage ---------------------------------------------------------
def ki_ollama(system: str, auftrag: str) -> tuple[str, str]:
    """Lokale KI. Gibt (Antworttext, Abbruchgrund) zurück."""
    antwort = requests.post(f"{OLLAMA_URL}/api/chat", timeout=1800, json={
        "model": MODELL,
        "stream": False,
        "think": False,
        "format": SCHEMA,                         # Ollama erzwingt diese JSON-Struktur
        "options": {"num_ctx": KONTEXT, "num_predict": 3000, "temperature": 0.2},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": auftrag}],
    })
    antwort.raise_for_status()
    daten = antwort.json()
    return daten.get("message", {}).get("content", ""), daten.get("done_reason", "")


def ki_openai(system: str, auftrag: str) -> tuple[str, str]:
    """Cloud-KI im OpenAI-Format (OpenAI selbst und viele andere Anbieter)."""
    antwort = requests.post(
        f"{API_URL}/chat/completions", timeout=600,
        headers={"Authorization": f"Bearer {API_SCHLUESSEL}"},
        json={
            "model": MODELL,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": auftrag}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "karteikarten", "strict": True, "schema": SCHEMA}},
        },
    )
    antwort.raise_for_status()
    wahl = antwort.json()["choices"][0]
    return wahl["message"].get("content") or "", wahl.get("finish_reason", "")


def ki_anthropic(system: str, auftrag: str) -> tuple[str, str]:
    """Claude-API (Anthropic). Eigenes Format: Schlüssel im Header "x-api-key",
    JSON-Struktur über "output_config", die Antwort steht im ersten Textblock."""
    antwort = requests.post(
        f"{API_URL}/messages", timeout=600,
        headers={"x-api-key": API_SCHLUESSEL, "anthropic-version": "2023-06-01"},
        json={
            "model": MODELL,
            "max_tokens": 4000,
            "system": system,
            "messages": [{"role": "user", "content": auftrag}],
            "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
        },
    )
    antwort.raise_for_status()
    daten = antwort.json()
    text = next((b.get("text", "") for b in daten.get("content", []) if b.get("type") == "text"), "")
    # "max_tokens" = abgeschnitten, "refusal" = abgelehnt; alles andere ist ein normales Ende.
    # Wir übersetzen in "stop", damit dieselbe Prüfung wie bei Ollama greift.
    grund = daten.get("stop_reason", "")
    return text, grund if grund in ("max_tokens", "refusal") else "stop"


def karten_erfragen(system: str, abschnitt: list[tuple[int, str]], bisherige: list[str],
                    log: Log) -> list[dict] | None:
    """Fragt die KI nach Karten für einen Abschnitt. Nimmt nur vollständige,
    gültige Antworten an; sonst bis zu VERSUCHE Wiederholungen."""
    nummern = {nummer for nummer, _ in abschnitt}
    auftrag = "\n\n".join(f"=== Folie {nummer} ===\n{text}" for nummer, text in abschnitt)
    # Jeder Abschnitt wird einzeln angefragt; ohne diese Liste wüsste das Modell nicht,
    # welche Inhalte frühere Abschnitte schon abgefragt haben (z. B. "Suchraum halbiert sich").
    # Nur die letzten 40 Fragen, damit das Kontextfenster reicht.
    if bisherige:
        liste = "\n".join(f"- {frage}" for frage in bisherige[-40:])
        auftrag = (f"=== Diese Fragen gibt es schon – diese Inhalte NICHT erneut abfragen ===\n"
                   f"{liste}\n\n{auftrag}")
    fragen = {"ollama": ki_ollama, "anthropic": ki_anthropic, "openai": ki_openai}[KI_ANBIETER]

    for versuch in range(1, VERSUCHE + 1):
        try:
            text, grund = fragen(system, auftrag)
        except (requests.RequestException, KeyError, ValueError) as fehler:
            log(f"    ! KI nicht erreichbar oder Fehler ({fehler}), Versuch {versuch}")
            time.sleep(5)
            continue
        if grund != "stop":                        # "length" = Antwort wurde abgeschnitten
            log(f"    ! Antwort unvollständig (Grund: {grund or '?'}), Versuch {versuch}")
            continue
        try:
            roh = json.loads(text)["karten"]
        except (ValueError, KeyError, TypeError):
            log(f"    ! Antwort ist kein gültiges JSON, Versuch {versuch}")
            continue

        karten, mit_folienverweis = [], 0
        for karte in roh if isinstance(roh, list) else []:
            if not isinstance(karte, dict):
                continue
            frage = str(karte.get("frage", "")).strip()
            antwort = str(karte.get("antwort", "")).strip()
            folie = karte.get("folie")
            if len(frage) < 8 or len(antwort) < 2:
                continue                           # leere oder sinnlose Karte
            # "das Beispiel aus Folie 23": beim Lernen sieht man die Folie nicht.
            # Der Prompt verbietet das, kleine Modelle halten sich aber nicht immer daran.
            if re.search(r"Folie\s*\d", frage, re.IGNORECASE):
                mit_folienverweis += 1
                continue
            if folie not in nummern:               # erfundene Foliennummer → erste des Abschnitts
                folie = min(nummern)
            karten.append({"frage": frage, "antwort": antwort, "folie": folie})
        if mit_folienverweis:
            log(f"    – {mit_folienverweis} Karte(n) verworfen: Frage verweist auf eine Folie")
        return karten[:MAX_KARTEN_PRO_ABSCHNITT]   # auch eine leere Liste ist gültig
    return None


# --- Anki-Paket bauen ---------------------------------------------------
NOTIZTYP = genanki.Model(
    NOTIZTYP_ID,
    "Folienkarte (automatisch)",
    fields=[{"name": "Frage"}, {"name": "Antwort"}, {"name": "Quelle"}],
    templates=[{
        "name": "Karte 1",
        "qfmt": '<div class="frage">{{Frage}}</div>',
        "afmt": '<div class="frage">{{Frage}}</div><hr id="answer">'
                '<div class="antwort">{{Antwort}}</div><div class="quelle">{{Quelle}}</div>',
    }],
    # Für E-Ink: nur reines Schwarz auf reinem Weiß. Grautöne muss das Display
    # aus schwarzen Punkten zusammensetzen (Dithering) – das wirkt kriselig.
    # Etwas kräftigere Schrift, weil dünne Linien auf E-Ink ausfransen.
    css=""".card { font-family: sans-serif; font-size: 22px; line-height: 1.45;
        font-weight: 500; color: #000; background: #fff; text-align: left; padding: 8px; }
.frage { font-weight: bold; }
.antwort { margin-top: 6px; }
.quelle { margin-top: 18px; font-size: 16px; font-style: italic; color: #000; }
hr#answer { border: none; border-top: 2px solid #000; }
.nightMode .card, .card.nightMode { color: #fff; background: #000; }
.nightMode .quelle { color: #fff; }
.nightMode hr#answer { border-top-color: #fff; }""",
)


def stabile_id(text: str) -> int:
    """Gleicher Name → gleiche Stapel-ID, auch bei späteren Läufen."""
    return int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:12], 16)


def als_html(text: str) -> str:
    """KI-Text sicher anzeigen: HTML-Zeichen entschärfen, Zeilenumbrüche erhalten."""
    return html.escape(text).replace("\n", "<br>")


def normalisieren(text: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]", "", text.lower())


def paket_bauen(fach: str, vorlesung: str, karten: list[dict]) -> bytes:
    stapelname = f"{STAPEL_OBEN}::{fach}::{vorlesung}"
    stapel = genanki.Deck(stabile_id(stapelname), stapelname)
    schlagwort = re.sub(r"\s+", "_", fach)
    for karte in karten:
        stapel.add_note(genanki.Note(
            model=NOTIZTYP,
            fields=[als_html(karte["frage"]), als_html(karte["antwort"]),
                    als_html(f"{vorlesung} · Folie {karte['folie']}")],
            tags=[schlagwort, "automatisch"],
            # Gleiche Frage im gleichen Fach → gleiche ID. Beim erneuten Import
            # wird die Karte aktualisiert statt verdoppelt; der Lernstand bleibt.
            guid=genanki.guid_for(fach, normalisieren(karte["frage"])),
        ))
    with tempfile.TemporaryDirectory() as tmp:
        datei = Path(tmp) / "paket.apkg"
        genanki.Package(stapel).write_to_file(datei)
        return datei.read_bytes()


def vorschau_bauen(fach: str, vorlesung: str, karten: list[dict], uebersprungen: list[int]) -> str:
    zeilen = [f"# Karteikarten: {vorlesung}", "",
              f"Fach: {fach} · {len(karten)} Karten · erstellt {datetime.now():%d.%m.%Y %H:%M} "
              f"mit {MODELL}", ""]
    if uebersprungen:
        zeilen += [f"Ohne Text (Titel-/Bildfolien, nicht berücksichtigt): Folie "
                   f"{', '.join(map(str, uebersprungen))}", ""]
    for i, karte in enumerate(karten, start=1):
        zeilen += [f"## {i}. {karte['frage']}", "", karte["antwort"], "",
                   f"*Folie {karte['folie']}*", ""]
    zeilen += ["---", "*Automatisch erstellt. Falsche Karten nach dem Import in AnkiDroid "
               "löschen oder bearbeiten.*"]
    return "\n".join(zeilen) + "\n"


# --- Eine PDF verarbeiten ----------------------------------------------
def pdf_verarbeiten(pdf: Path, fach: str, system_vorlage: str, log: Log) -> bool:
    vorlesung = pdf.stem.strip()
    ziel_ordner = SEMESTER / fach / KARTEN_ORDNER

    # Vor der langen KI-Arbeit prüfen, ob wir das Ergebnis überhaupt speichern können
    if not beschreibbar(ziel_ordner):
        log(f"  ✗ Keine Schreibrechte für {ziel_ordner} – nächster Lauf neuer Versuch")
        return False

    try:
        folien = folien_lesen(pdf)
    except (subprocess.SubprocessError, OSError) as fehler:
        log(f"  ✗ PDF nicht lesbar ({fehler})")
        return False
    abschnitte = abschnitte_bilden(folien)
    uebersprungen = [n for n, t in enumerate(folien, start=1) if len(t) < MIN_ZEICHEN_PRO_FOLIE]
    log(f"  {len(folien)} Folien, davon {len(uebersprungen)} ohne Text, "
        f"{len(abschnitte)} Abschnitt(e)")
    if not abschnitte:
        log("  ✗ Kein Text gefunden – ist die PDF gescannt (nur Bilder)?")
        return False

    system = (system_vorlage.replace("{fach}", fach)
              .replace("{max_karten}", str(MAX_KARTEN_PRO_ABSCHNITT)))
    karten, gesehen = [], set()
    for i, abschnitt in enumerate(abschnitte, start=1):
        start = time.monotonic()
        neue = karten_erfragen(system, abschnitt, [k["frage"] for k in karten], log)
        if neue is None:
            log(f"  ✗ Abschnitt {i} nach {VERSUCHE} Versuchen fehlgeschlagen – "
                f"nächster Lauf neuer Versuch")
            return False
        doppelt = 0
        for karte in neue:
            schluessel = normalisieren(karte["frage"])
            if schluessel in gesehen:
                doppelt += 1
                continue
            gesehen.add(schluessel)
            karten.append(karte)
        log(f"  Abschnitt {i}/{len(abschnitte)} (Folie {abschnitt[0][0]}–{abschnitt[-1][0]}): "
            f"{len(neue) - doppelt} Karten in {time.monotonic() - start:.0f} s")

    if not karten:
        log("  ✗ Die KI hat keine einzige Karte erstellt")
        return False

    try:
        atomar_schreiben(ziel_ordner / f"{vorlesung}.apkg", paket_bauen(fach, vorlesung, karten))
        atomar_schreiben(ziel_ordner / f"{vorlesung}.md",
                         vorschau_bauen(fach, vorlesung, karten, uebersprungen).encode("utf-8"))
    except OSError as fehler:
        log(f"  ✗ Speichern fehlgeschlagen ({fehler})")
        return False
    log(f"  ✓ {len(karten)} Karten gespeichert → {KARTEN_ORDNER}/{vorlesung}.apkg")
    return True


# --- Hauptprogramm ------------------------------------------------------
def pdfs_finden() -> list[tuple[Path, str]]:
    """Alle PDFs in <Fach>/Folien/, die älter als MIN_ALTER_MINUTEN sind."""
    grenze = time.time() - MIN_ALTER_MINUTEN * 60
    gefunden = []
    for fach_ordner in sorted(p for p in SEMESTER.iterdir() if p.is_dir()):
        if fach_ordner.name.lower() in AUSLASSEN:
            continue                                # Fach bewusst ausgeschlossen
        folien_ordner = fach_ordner / FOLIEN_ORDNER
        if not folien_ordner.is_dir():
            continue
        for pdf in sorted(folien_ordner.iterdir()):
            if (pdf.is_file() and pdf.suffix.lower() == ".pdf" and not pdf.name.startswith(".")
                    and pdf.stat().st_mtime < grenze):
                gefunden.append((pdf, fach_ordner.name))
    return gefunden


def main() -> int:
    DATEN_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    # "docker stop" schickt SIGTERM. Ohne eigene Behandlung würde Python sofort
    # beendet (bzw. als PID 1 im Container das Signal ignorieren) und die Sperre
    # bliebe liegen. So wird daraus ein normales Programmende, und "finally" räumt auf.
    signal.signal(signal.SIGTERM, lambda nummer, rahmen: sys.exit(143))

    # Doppelstart verhindern (wie bei Zeitung und Transkript); alte Sperre nach 12 h entfernen
    if SPERRE.is_dir() and time.time() - SPERRE.stat().st_mtime > 12 * 3600:
        SPERRE.rmdir()
    try:
        SPERRE.mkdir()
    except FileExistsError:
        print("Läuft bereits – Abbruch.")
        return 1

    try:
        log = Log(LOG_DIR / f"karteikarten-{datetime.now():%Y-%m-%d_%H-%M}.log")
        return lauf(log)
    finally:
        SPERRE.rmdir()
        alte = sorted(LOG_DIR.glob("karteikarten-*.log"), key=lambda p: p.stat().st_mtime,
                      reverse=True)[LOGS_BEHALTEN:]
        for datei in alte:
            datei.unlink(missing_ok=True)


def lauf(log: Log) -> int:
    start = time.monotonic()
    log(f"Start: {datetime.now():%d.%m.%Y %H:%M:%S} | KI: {KI_ANBIETER}, Modell: {MODELL}")
    if KI_ANBIETER not in ("ollama", "anthropic", "openai"):
        log(f"✗ Unbekannter KI_ANBIETER '{KI_ANBIETER}' (erlaubt: ollama, anthropic, openai)")
        return 1
    if KI_ANBIETER != "ollama" and not API_SCHLUESSEL:
        log(f"✗ KI_ANBIETER={KI_ANBIETER}, aber kein API_SCHLUESSEL gesetzt")
        return 1
    if not shutil.which("pdftotext"):
        log("✗ pdftotext fehlt (Paket poppler-utils)")
        return 1

    system_vorlage = (SKRIPT_DIR / "prompts" / "karten.txt").read_text(encoding="utf-8")
    status = json.loads(STATUS_DATEI.read_text()) if STATUS_DATEI.exists() else {}

    offen = []
    for pdf, fach in pdfs_finden():
        schluessel = str(pdf.relative_to(SEMESTER))
        if NUR and NUR not in schluessel.lower():
            continue                                # Testlauf mit Filter: andere PDFs auslassen
        summe = pruefsumme(pdf)
        if not ERZWINGEN and status.get(schluessel) == summe:
            continue                                # diese Version ist schon fertig
        offen.append((pdf, fach, schluessel, summe))
    log(f"{len(offen)} neue oder geänderte Foliensätze")

    fehler = 0
    for pdf, fach, schluessel, summe in offen:
        log(f"→ {fach} / {pdf.name}")
        if pdf_verarbeiten(pdf, fach, system_vorlage, log):
            status[schluessel] = summe
            # Nach jeder PDF speichern: bricht der Lauf ab, ist Erledigtes nicht verloren
            atomar_schreiben(STATUS_DATEI,
                             json.dumps(status, indent=1, ensure_ascii=False).encode("utf-8"))
        else:
            fehler += 1

    log(f"\nEnde: {datetime.now():%d.%m.%Y %H:%M:%S}, Dauer "
        f"{(time.monotonic() - start) / 60:.0f} Min., Fehler: {fehler}")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
