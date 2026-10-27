#!/usr/bin/env bash
# zeitung.sh – Startskript: führt alle Schritte nacheinander aus
#   1. sammeln.sh        Feeds holen
#   2. schreiben.sh      Ollama schreibt die Rubriken
#   3. zusammensetzen.sh HTML-Zeitung bauen
#   4. verteilen.sh      neueste Ausgabe in den Boox-Ordner legen
# Alles wird in logs/ mitprotokolliert.

set -uo pipefail   # bewusst ohne -e: Fehler behandeln wir selbst pro Schritt

SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SKRIPT_DIR}/logs"
SPERRE="${SKRIPT_DIR}/.laeuft"
LOGS_BEHALTEN=10

mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/zeitung-$(date '+%Y-%m-%d_%H-%M').log"

# Ab hier geht jede Ausgabe sowohl auf den Bildschirm als auch ins Log
exec > >(tee -a "$LOG") 2>&1

# --- Doppelstart verhindern ------------------------------------------
# mkdir ist atomar: Nur ein Lauf kann den Ordner anlegen.
# Eine Sperre, die älter als 12 Stunden ist, stammt von einem Absturz.
if [[ -d "$SPERRE" ]] && [[ -n "$(find "$SPERRE" -maxdepth 0 -mmin +720)" ]]; then
  echo "Alte Sperre von einem abgebrochenen Lauf gefunden – wird entfernt."
  rmdir "$SPERRE"
fi
if ! mkdir "$SPERRE" 2>/dev/null; then
  echo "Es läuft bereits eine Zeitung – Abbruch."
  exit 1
fi
trap 'rmdir "$SPERRE" 2>/dev/null' EXIT   # Sperre am Ende immer entfernen

# --- Hilfsfunktion: einen Schritt ausführen und Zeit messen -----------
schritt() {
  local name="$1" skript="$2" start dauer status
  echo
  echo "===== ${name} ($(date '+%H:%M:%S')) ====="
  start=$SECONDS
  "${SKRIPT_DIR}/${skript}"
  status=$?
  dauer=$(( SECONDS - start ))
  echo "----- ${name}: Status ${status}, Dauer $(( dauer / 60 )) Min. $(( dauer % 60 )) Sek."
  return "$status"
}

echo "Zeitungslauf gestartet: $(date '+%d.%m.%Y %H:%M:%S')"
gesamt_status=0

# Schritt 1: Ohne Meldungen ist alles Weitere sinnlos -> Abbruch
if ! schritt "1/4 Sammeln" sammeln.sh; then
  echo "Sammeln fehlgeschlagen – Abbruch, die alte Ausgabe bleibt bestehen."
  exit 1
fi

# Schritt 2: Einzelne Rubriken dürfen fehlschlagen -> trotzdem weiter
if ! schritt "2/4 Schreiben" schreiben.sh; then
  echo "Nicht alle Rubriken wurden geschrieben – die Zeitung wird trotzdem gebaut."
  gesamt_status=1
fi

# Schritt 3
if ! schritt "3/4 Zusammensetzen" zusammensetzen.sh; then
  echo "Zusammensetzen fehlgeschlagen – die alte Ausgabe bleibt bestehen."
  exit 1
fi

# Schritt 4: Die Zeitung ist fertig und im Browser erreichbar,
# ein Fehler hier betrifft nur den Boox -> melden, nicht abbrechen
if ! schritt "4/4 Verteilen" verteilen.sh; then
  echo "Kopieren in den Boox-Ordner fehlgeschlagen – die Zeitung ist trotzdem im Browser erreichbar."
  gesamt_status=1
fi

# --- Alte Logs aufräumen: nur die neuesten behalten -------------------
ls -1t "${LOG_DIR}"/zeitung-*.log | tail -n +$(( LOGS_BEHALTEN + 1 )) | xargs -r rm -f

echo
echo "Zeitungslauf beendet: $(date '+%d.%m.%Y %H:%M:%S'), Gesamtdauer $(( SECONDS / 60 )) Min."
exit "$gesamt_status"
