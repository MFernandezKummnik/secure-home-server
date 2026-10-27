#!/usr/bin/env bash
# zusammensetzen.sh – Schritt 3 der Zeitungsautomation
# Baut aus daten/<rubrik>.md und daten/meldungen.tsv eine HTML-Zeitung.
# Ergebnis: ausgabe/zeitung-<Jahr>-KW<Nr>.html und ausgabe/index.html

set -euo pipefail

# --- Einstellungen ---------------------------------------------------
SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATEN_DIR="${SKRIPT_DIR}/daten"
AUSGABE_DIR="${SKRIPT_DIR}/ausgabe"
STIL="${SKRIPT_DIR}/vorlage/stil.css"
MELDUNGEN="${DATEN_DIR}/meldungen.tsv"

MODELL="${MODELL:-qwen3.5:9b}"   # nur für die Fußzeile
MAX_QUELLEN=20                   # wie viele Meldungen schreiben.sh pro Rubrik nutzt
WOERTER_PRO_MINUTE=200

# Dateiname der Rubrik | Überschrift in der Zeitung
RUBRIKEN=(
  "innenpolitik|Innenpolitik"
  "aussenpolitik|Außenpolitik"
  "cyber|Cybersecurity &amp; Open Source"
  "maerkte|Märkte &amp; Investitionen"
)

# --- Hilfsfunktionen -------------------------------------------------

# Macht Text HTML-sicher: < > & " können sonst die Seite zerstören
html_escape() {
  sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g'
}

# Lesezeit in Minuten, aufgerundet
lesezeit() {
  local woerter
  woerter=$(wc -w < "$1")
  echo $(( (woerter + WOERTER_PRO_MINUTE - 1) / WOERTER_PRO_MINUTE ))
}

# Quellenliste einer Rubrik als HTML-<li>-Einträge
quellen_liste() {
  local rubrik="$1"
  awk -F'\t' -v r="$rubrik" -v max="$MAX_QUELLEN" '$1 == r && n < max { print; n++ }' "$MELDUNGEN" \
    | tr '\t' '\037' \
    | while IFS=$'\x1f' read -r _ epoch quelle titel link _; do
        local datum titel_h quelle_h link_h
        datum=$(date -d "@${epoch}" '+%d.%m.')
        titel_h=$(printf '%s' "$titel"  | html_escape)
        quelle_h=$(printf '%s' "$quelle" | html_escape)
        # Nur echte Web-Links verlinken
        if [[ "$link" =~ ^https?:// ]]; then
          link_h=$(printf '%s' "$link" | html_escape)
          printf '<li><a href="%s">%s</a> <span class="quelle">%s, %s</span></li>\n' \
            "$link_h" "$titel_h" "$quelle_h" "$datum"
        else
          printf '<li>%s <span class="quelle">%s, %s</span></li>\n' \
            "$titel_h" "$quelle_h" "$datum"
        fi
      done
}

# --- Vorbereitung ----------------------------------------------------
mkdir -p "$AUSGABE_DIR"

JAHR=$(date +%G)          # Jahr der Kalenderwoche
KW=$(date +%V)            # Kalenderwoche
VON=$(date -d '-7 days' '+%d.%m.')
BIS=$(date '+%d.%m.%Y')
DATEI="${AUSGABE_DIR}/zeitung-${JAHR}-KW${KW}.html"
TMP="${DATEI}.tmp"

# Gesamt-Lesezeit über alle vorhandenen Rubriken
gesamt=0
for eintrag in "${RUBRIKEN[@]}"; do
  IFS='|' read -r rubrik _ <<< "$eintrag"
  md="${DATEN_DIR}/${rubrik}.md"
  [[ -s "$md" ]] && gesamt=$(( gesamt + $(lesezeit "$md") ))
done

# --- HTML erzeugen ---------------------------------------------------
{
  cat <<EOF
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wochenzeitung KW ${KW}/${JAHR}</title>
<style>
$(cat "$STIL")
</style>
</head>
<body>
<main>
<header>
  <h1>Wochenzeitung</h1>
  <div class="meta">KW ${KW} · ${VON} bis ${BIS} · ca. ${gesamt} Minuten Lesezeit</div>
</header>
<nav>
<ol>
EOF

  # Inhaltsverzeichnis
  for eintrag in "${RUBRIKEN[@]}"; do
    IFS='|' read -r rubrik titel <<< "$eintrag"
    md="${DATEN_DIR}/${rubrik}.md"
    if [[ -s "$md" ]]; then
      printf '<li><a href="#%s">%s</a> <span>· %s Min.</span></li>\n' "$rubrik" "$titel" "$(lesezeit "$md")"
    else
      printf '<li><a href="#%s">%s</a> <span>· fehlt diese Woche</span></li>\n' "$rubrik" "$titel"
    fi
  done
  echo '</ol>'
  echo '</nav>'

  # Rubriken
  for eintrag in "${RUBRIKEN[@]}"; do
    IFS='|' read -r rubrik titel <<< "$eintrag"
    md="${DATEN_DIR}/${rubrik}.md"

    printf '<section id="%s">\n<h2>%s</h2>\n' "$rubrik" "$titel"

    if [[ -s "$md" ]]; then
      minuten=$(lesezeit "$md")
      if (( minuten == 1 )); then einheit="Minute"; else einheit="Minuten"; fi
      printf '<div class="rubrik-meta">ca. %s %s</div>\n' "$minuten" "$einheit"
      # Markdown -> HTML. Überschriften des Modells eine Ebene tiefer (h1/h2 -> h3),
      # weil h2 schon der Rubrik-Titel ist. cmark entfernt rohes HTML aus der Eingabe.
      cmark "$md" | sed -E -e 's#<(/?)h[12]>#<\1h3>#g'
    else
      echo '<p class="fehlt">Diese Rubrik konnte diese Woche nicht erstellt werden.</p>'
    fi

    quellen=$(quellen_liste "$rubrik")
    if [[ -n "$quellen" ]]; then
      printf '<details>\n<summary>Quellen (%s Meldungen)</summary>\n<ul>\n%s\n</ul>\n</details>\n' \
        "$(wc -l <<< "$quellen")" "$quellen"
    fi
    echo '</section>'
  done

  cat <<EOF
<footer>Automatisch erstellt am $(date '+%d.%m.%Y um %H:%M') mit ${MODELL} aus $(wc -l < "$MELDUNGEN") Meldungen.<br>
Zusammenfassungen einer KI – im Zweifel die verlinkten Quellen prüfen.</footer>
</main>
</body>
</html>
EOF
} > "$TMP"

# Erst wenn alles fertig ist, die echte Datei ersetzen
mv "$TMP" "$DATEI"
cp "$DATEI" "${AUSGABE_DIR}/index.html"

echo "Fertig: ${DATEI}"
echo "Aktuelle Ausgabe außerdem als: ${AUSGABE_DIR}/index.html"
