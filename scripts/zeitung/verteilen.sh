#!/usr/bin/env bash
# verteilen.sh – Schritt 4 der Zeitungsautomation
# Legt die neueste Ausgabe in den Boox-Ordner (wird per Syncthing synchronisiert)
# und entfernt dort ältere Ausgaben. Andere Dateien im Ordner bleiben unberührt.

set -euo pipefail

# --- Einstellungen ---------------------------------------------------
SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUSGABE_DIR="${SKRIPT_DIR}/ausgabe"
BOOX_DIR="${BOOX_DIR:-${SKRIPT_DIR}/boox}"

# --- Neueste Ausgabe finden ------------------------------------------
# Die Shell ersetzt das Muster durch alle passenden Dateien.
# -nt heißt "newer than": Wir merken uns jeweils die neueste.
neueste=""
for datei in "${AUSGABE_DIR}"/zeitung-*.html; do
  [[ -e "$datei" ]] || continue          # Muster hat nichts gefunden
  if [[ -z "$neueste" || "$datei" -nt "$neueste" ]]; then
    neueste="$datei"
  fi
done

if [[ -z "$neueste" ]]; then
  echo "Keine Ausgabe in ${AUSGABE_DIR} gefunden – zuerst zusammensetzen.sh ausführen." >&2
  exit 1
fi

if [[ ! -d "$BOOX_DIR" ]]; then
  echo "Boox-Ordner ${BOOX_DIR} existiert nicht – bitte einmalig anlegen." >&2
  exit 1
fi

name=$(basename "$neueste")

# --- Neue Ausgabe hineinlegen (erst versteckt kopieren, dann umbenennen) ---
cp "$neueste" "${BOOX_DIR}/.${name}.tmp"
mv "${BOOX_DIR}/.${name}.tmp" "${BOOX_DIR}/${name}"
echo "Neu im Boox-Ordner: ${name}"

# --- Ältere Ausgaben entfernen ---------------------------------------
# Nur Dateien nach dem Muster zeitung-*.html, und nie die gerade kopierte.
# Syncthings eigene Dateien (.stfolder usw.) werden so nie angefasst.
for alt in "${BOOX_DIR}"/zeitung-*.html; do
  [[ -e "$alt" ]] || continue
  [[ "$(basename "$alt")" == "$name" ]] && continue
  rm -f "$alt"
  echo "Entfernt: $(basename "$alt")"
done
