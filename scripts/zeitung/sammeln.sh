#!/usr/bin/env bash
# sammeln.sh – Schritt 1 der Zeitungsautomation
# Lädt alle Feeds aus feeds.conf, behält nur Meldungen der letzten Tage
# und schreibt sie in eine einheitliche Datei: daten/meldungen.tsv

set -euo pipefail

# --- Einstellungen ---------------------------------------------------
SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FEEDS_DATEI="${SKRIPT_DIR}/feeds.conf"
DATEN_DIR="${SKRIPT_DIR}/daten"
AUSGABE="${DATEN_DIR}/meldungen.tsv"
TAGE_ZURUECK="${TAGE_ZURUECK:-7}"
TRENNER=$'\x1f'   # unsichtbares Trennzeichen, kommt in Nachrichtentexten nie vor

mkdir -p "$DATEN_DIR"
: > "$AUSGABE"    # Ausgabedatei leeren

GRENZE=$(date -d "-${TAGE_ZURUECK} days" +%s)
fehlgeschlagen=0

# --- Hilfsfunktion: Feed-XML in Zeilen "Titel␟Link␟Datum␟Text" umwandeln ---
eintraege_lesen() {
  local xml="$1" ergebnis

  # Versuch 1: RSS-Format (<item>)
  ergebnis=$(printf '%s' "$xml" | xmlstarlet sel -T -t -m '//item' \
      -v 'normalize-space(title)'       -o "$TRENNER" \
      -v 'normalize-space(link)'        -o "$TRENNER" \
      -v 'normalize-space(pubDate)'     -o "$TRENNER" \
      -v 'normalize-space(description)' -n 2>/dev/null || true)

  # Versuch 2: Atom-Format (<entry>), falls RSS nichts geliefert hat
  if [[ -z "$ergebnis" ]]; then
    ergebnis=$(printf '%s' "$xml" | xmlstarlet sel -T \
        -N a="http://www.w3.org/2005/Atom" -t -m '//a:entry' \
        -v 'normalize-space(a:title)'                         -o "$TRENNER" \
        -v 'a:link[not(@rel) or @rel="alternate"][1]/@href'   -o "$TRENNER" \
        -v 'normalize-space((a:published|a:updated)[1])'      -o "$TRENNER" \
        -v 'normalize-space((a:summary|a:content)[1])'        -n 2>/dev/null || true)
  fi

  printf '%s' "$ergebnis"
}

# --- Hilfsfunktion: Text säubern ---------------------------------------
# Entfernt HTML-Tags, wandelt übrig gebliebene HTML-Codes um
# und löscht die Bezahl-Markierung "[$]" von LWN.
saeubern() {
  printf '%s' "$1" | sed \
    -e 's/<[^>]*>//g' \
    -e 's/&#160;/ /g'  -e 's/&nbsp;/ /g' \
    -e 's/&quot;/"/g'  -e "s/&#39;/'/g" \
    -e 's/&lt;/</g'    -e 's/&gt;/>/g' \
    -e 's/&amp;/\&/g' \
    -e 's/^\[\$\] //'
}

# --- Hauptschleife: jeden Feed abarbeiten ------------------------------
while IFS='|' read -r rubrik quelle url || [[ -n "${rubrik:-}" ]]; do
  # Leerzeilen und Kommentare überspringen
  [[ -z "${rubrik// /}" || "$rubrik" == \#* ]] && continue

  echo "→ ${quelle} (${rubrik})"

  if ! xml=$(curl -fsSL --max-time 30 --retry 2 -A "zeitung-bot/1.0" "$url"); then
    echo "  ✗ Feed nicht erreichbar: $url" >&2
    fehlgeschlagen=$((fehlgeschlagen + 1))
    continue
  fi

  eintraege=$(eintraege_lesen "$xml")
  if [[ -z "$eintraege" ]]; then
    echo "  ✗ Keine Einträge erkannt (Format unbekannt?)" >&2
    fehlgeschlagen=$((fehlgeschlagen + 1))
    continue
  fi

  anzahl=0
  while IFS="$TRENNER" read -r titel link datum text; do
    # Datum in Sekunden umrechnen; unlesbare Daten überspringen
    epoch=$(date -d "$datum" +%s 2>/dev/null) || continue
    (( epoch < GRENZE )) && continue

    # Titel und Text säubern, Text auf 600 Zeichen kürzen
    titel=$(saeubern "$titel")
    text=$(saeubern "$text" | cut -c1-600)

    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$rubrik" "$epoch" "$quelle" "$titel" "$link" "$text" >> "$AUSGABE"
    anzahl=$((anzahl + 1))
  done <<< "$eintraege"

  echo "  ✓ ${anzahl} Meldungen aus den letzten ${TAGE_ZURUECK} Tagen"
done < "$FEEDS_DATEI"

# --- Aufräumen: Duplikate (gleicher Link) raus, sortieren ---------------
sort -t $'\t' -k5,5 -u "$AUSGABE" \
  | sort -t $'\t' -k1,1 -k2,2nr > "${AUSGABE}.tmp"
mv "${AUSGABE}.tmp" "$AUSGABE"

echo
echo "Fertig: $(wc -l < "$AUSGABE") Meldungen in ${AUSGABE}"
echo "Pro Rubrik:"
cut -f1 "$AUSGABE" | sort | uniq -c

if (( fehlgeschlagen > 0 )); then
  echo "Achtung: ${fehlgeschlagen} Feed(s) fehlgeschlagen – siehe oben." >&2
fi
