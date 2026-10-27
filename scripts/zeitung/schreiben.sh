#!/usr/bin/env bash
# schreiben.sh – Schritt 2 der Zeitungsautomation
# Liest daten/meldungen.tsv und lässt Ollama pro Rubrik einen
# Zeitungsteil schreiben. Ergebnis: daten/<rubrik>.md

set -euo pipefail

# --- Einstellungen ---------------------------------------------------
SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATEN_DIR="${SKRIPT_DIR}/daten"
PROMPT_DIR="${SKRIPT_DIR}/prompts"
MELDUNGEN="${DATEN_DIR}/meldungen.tsv"

OLLAMA_URL="${OLLAMA_URL:-http://172.17.0.1:11434}"  # Ollama auf dem Host
MODELL="${MODELL:-qwen3.5:9b}"
KONTEXT="${KONTEXT:-8192}"     # Kontextfenster in Tokens (Eingabe + Ausgabe)
VERSUCHE="${VERSUCHE:-3}"      # Wiederholungen pro Rubrik bei Fehlern
MIN_ZEICHEN=500                # kürzere Antworten gelten als kaputt

# Rubrik | max. Meldungen als Eingabe | max. Tokens für die Antwort
RUBRIKEN=(
  "innenpolitik|20|2500"
  "aussenpolitik|20|2500"
  "cyber|20|1500"
  "maerkte|20|1500"
)

# --- Hilfsfunktion: Meldungen einer Rubrik als Liste für das Modell ---
meldungen_auflisten() {
  local rubrik="$1" max="$2"
  # awk wählt die Zeilen der Rubrik aus und hört nach "max" Stück auf.
  # tr macht aus Tabs \x1f, damit leere Spalten nicht verrutschen.
  awk -F'\t' -v r="$rubrik" -v max="$max" '$1 == r && n < max { print; n++ }' "$MELDUNGEN" \
    | tr '\t' '\037' \
    | while IFS=$'\x1f' read -r _ epoch quelle titel _ text; do
        printf -- '- [%s, %s] %s: %s\n' \
          "$quelle" "$(date -d "@${epoch}" '+%d.%m.')" "$titel" "$text"
      done
}

# --- Hilfsfunktion: eine Anfrage an Ollama --------------------------
# Gibt den Text nur aus, wenn die Antwort vollständig und lang genug ist.
ollama_fragen() {
  local system="$1" auftrag="$2" max_tokens="$3"
  local anfrage antwort grund text

  # JSON-Anfrage mit jq bauen (kümmert sich um Anführungszeichen etc.)
  anfrage=$(jq -n \
    --arg modell "$MODELL" --arg system "$system" --arg auftrag "$auftrag" \
    --argjson kontext "$KONTEXT" --argjson max "$max_tokens" \
    '{
       model: $modell,
       stream: false,
       think: false,
       options: { num_ctx: $kontext, num_predict: $max, temperature: 0.3 },
       messages: [
         { role: "system", content: $system },
         { role: "user",   content: $auftrag }
       ]
     }')

  # Anfrage schicken; bis zu 20 Minuten warten (Modell läuft teils auf der CPU)
  if ! antwort=$(printf '%s' "$anfrage" | curl -fsS --max-time 1200 \
         -H 'Content-Type: application/json' \
         --data-binary @- "${OLLAMA_URL}/api/chat"); then
    echo "    ! Ollama nicht erreichbar oder Fehler" >&2
    return 1
  fi

  # Warum hat das Modell aufgehört? "stop" = fertig, "length" = abgeschnitten
  grund=$(jq -r '.done_reason // "unbekannt"' <<< "$antwort")
  text=$(jq -r '.message.content // ""' <<< "$antwort" \
         | awk '/<think>/{skip=1} !skip{print} /<\/think>/{skip=0}')

  if [[ "$grund" != "stop" ]]; then
    echo "    ! Antwort unvollständig (Grund: ${grund})" >&2
    return 1
  fi
  if (( ${#text} < MIN_ZEICHEN )); then
    echo "    ! Antwort zu kurz (${#text} Zeichen)" >&2
    return 1
  fi

  printf '%s\n' "$text"
}

# --- Vorab-Prüfungen -------------------------------------------------
if [[ ! -s "$MELDUNGEN" ]]; then
  echo "Keine Meldungen gefunden – zuerst sammeln.sh ausführen." >&2
  exit 1
fi
SYSTEM=$(cat "${PROMPT_DIR}/system.txt")

echo "Modell: ${MODELL} | Kontext: ${KONTEXT} | Ollama: ${OLLAMA_URL}"
fehlgeschlagen=0

# --- Hauptschleife: jede Rubrik einzeln schreiben lassen --------------
for eintrag in "${RUBRIKEN[@]}"; do
  IFS='|' read -r rubrik max_meldungen max_tokens <<< "$eintrag"
  ziel="${DATEN_DIR}/${rubrik}.md"
  rm -f "$ziel"    # alte Ausgabe weg, damit nichts Veraltetes liegen bleibt
  echo "→ ${rubrik}"

  liste=$(meldungen_auflisten "$rubrik" "$max_meldungen")
  if [[ -z "$liste" ]]; then
    echo "  – keine Meldungen, übersprungen"
    continue
  fi
  echo "  $(wc -l <<< "$liste") Meldungen als Grundlage"

  auftrag="$(cat "${PROMPT_DIR}/${rubrik}.txt")

Meldungen der vergangenen Woche:
${liste}"

  erfolg=0
  for (( versuch = 1; versuch <= VERSUCHE; versuch++ )); do
    echo "  Versuch ${versuch}/${VERSUCHE} …"
    if text=$(ollama_fragen "$SYSTEM" "$auftrag" "$max_tokens"); then
      printf '%s\n' "$text" > "$ziel"
      echo "  ✓ $(wc -w < "$ziel") Wörter geschrieben"
      erfolg=1
      break
    fi
  done

  if (( erfolg == 0 )); then
    echo "  ✗ ${rubrik} nach ${VERSUCHE} Versuchen fehlgeschlagen" >&2
    fehlgeschlagen=$((fehlgeschlagen + 1))
  fi
done

echo
if (( fehlgeschlagen > 0 )); then
  echo "Achtung: ${fehlgeschlagen} Rubrik(en) fehlgeschlagen." >&2
  exit 1
fi
echo "Fertig: alle Rubriken geschrieben."
