#!/usr/bin/env bash
# transkript.sh – Vorlesungsaufnahmen automatisch transkribieren und zusammenfassen
#
#   mp3Dateien/<Fach> <TT.MM.JJ>.mp3
#     → <Fach>/vorlesungstranskripte/<Name>.txt     (Whisper, GPU)
#     → <Fach>/ZusammenfassungVorlesung/<Name>.md   (Ollama)
#     → Vorlesungsarchiv/<Fach>/<Name>.mp3          (Original)

set -uo pipefail     # ohne -e: Fehler einer Datei sollen die anderen nicht stoppen

# --- Einstellungen ---------------------------------------------------
SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEMESTER="${SEMESTER:-/semester}"                     # = /mnt/user/Semester2
EINGANG="${EINGANG:-${SEMESTER}/mp3Dateien}"
ARCHIV="${ARCHIV:-/archiv}"                           # = /mnt/user/Vorlesungsarchiv
TRANSKRIPT_ORDNER="vorlesungstranskripte"
ZUSAMMENFASSUNG_ORDNER="ZusammenfassungVorlesung"

WHISPER_URL="${WHISPER_URL:-http://127.0.0.1:9000}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
MODELL="${MODELL:-qwen3.5:9b}"
KONTEXT="${KONTEXT:-8192}"
WOERTER_PRO_ABSCHNITT="${WOERTER_PRO_ABSCHNITT:-2000}"
VERSUCHE=3
MIN_ALTER_MINUTEN="${MIN_ALTER_MINUTEN:-10}"   # Dateien, die gerade noch synchronisiert werden, auslassen
WHISPER_PAUSE="${WHISPER_PAUSE:-320}"          # Sekunden, bis Whisper das Modell aus dem VRAM wirft

ALIASE="${SKRIPT_DIR}/aliase.conf"                  # Abkürzungen wie "BeSy = Betriebssysteme"
DATEN_DIR="${SKRIPT_DIR}/daten"
WARTESCHLANGE="${DATEN_DIR}/zusammenfassen.liste"   # Transkripte, die noch eine Zusammenfassung brauchen
LOG_DIR="${SKRIPT_DIR}/logs"
SPERRE="${SKRIPT_DIR}/.laeuft"
LOGS_BEHALTEN=20

mkdir -p "$DATEN_DIR" "$LOG_DIR"
touch "$WARTESCHLANGE"
LOG="${LOG_DIR}/transkript-$(date '+%Y-%m-%d_%H-%M').log"
exec > >(tee -a "$LOG") 2>&1

# --- Doppelstart verhindern (wie bei der Zeitung) ---------------------
if [[ -d "$SPERRE" && -n "$(find "$SPERRE" -maxdepth 0 -mmin +720)" ]]; then
  echo "Alte Sperre gefunden – wird entfernt."; rmdir "$SPERRE"
fi
if ! mkdir "$SPERRE" 2>/dev/null; then
  echo "Läuft bereits – Abbruch."; exit 1
fi
trap 'rmdir "$SPERRE" 2>/dev/null' EXIT

fehler=0
echo "Start: $(date '+%d.%m.%Y %H:%M:%S')"

# --- Hilfsfunktionen -------------------------------------------------

# "Algorithmen und Datenstrukturen" und "AlgorithmenUndDatenstrukturen" → "algorithmenunddatenstrukturen"
normalisieren() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9'
}

# Sucht in Semester2 den Fachordner, der zum Namensteil passt. Gibt den Ordnernamen aus.
# 1. direkter Vergleich mit den Ordnernamen, 2. Abkürzungen aus aliase.conf
fach_finden() {
  local gesucht ordner name kurz ziel
  gesucht=$(normalisieren "$1")

  for ordner in "$SEMESTER"/*/; do
    name=$(basename "$ordner")
    [[ "$name" == "$(basename "$EINGANG")" ]] && continue
    if [[ "$(normalisieren "$name")" == "$gesucht" ]]; then
      printf '%s' "$name"
      return 0
    fi
  done

  [[ -f "$ALIASE" ]] || return 1
  while IFS='=' read -r kurz ziel || [[ -n "$kurz" ]]; do
    [[ "$kurz" =~ ^[[:space:]]*(#|$) ]] && continue        # Kommentare, Leerzeilen
    ziel=$(printf '%s' "$ziel" | xargs)                    # Leerzeichen am Rand entfernen
    if [[ "$(normalisieren "$kurz")" == "$gesucht" && -d "${SEMESTER}/${ziel}" ]]; then
      printf '%s' "$ziel"
      return 0
    fi
  done < "$ALIASE"
  return 1
}

# Speichert Text atomar: erst .tmp, dann umbenennen. Rückgabe ≠ 0 bei jedem Fehler.
speichern() {
  local ziel="$1" inhalt="$2"
  mkdir -p "$(dirname "$ziel")" 2>/dev/null &&
    printf '%s\n' "$inhalt" > "${ziel}.tmp" 2>/dev/null &&
    mv "${ziel}.tmp" "$ziel" 2>/dev/null &&
    [[ -s "$ziel" ]]
}

# Prüft, ob in einen Ordner geschrieben werden darf (legt ihn bei Bedarf an)
beschreibbar() {
  mkdir -p "$1" 2>/dev/null && [[ -w "$1" ]]
}

# Fragt Ollama; gibt nur vollständige Antworten aus (done_reason = stop)
ollama_fragen() {
  local system="$1" auftrag="$2" max_tokens="$3" anfrage antwort grund text versuch
  anfrage=$(jq -n --arg m "$MODELL" --arg s "$system" --arg a "$auftrag" \
    --argjson ctx "$KONTEXT" --argjson np "$max_tokens" \
    '{model: $m, stream: false, think: false,
      options: {num_ctx: $ctx, num_predict: $np, temperature: 0.2},
      messages: [{role: "system", content: $s}, {role: "user", content: $a}]}')

  for (( versuch = 1; versuch <= VERSUCHE; versuch++ )); do
    if antwort=$(printf '%s' "$anfrage" | curl -fsS --max-time 1800 \
         -H 'Content-Type: application/json' --data-binary @- "${OLLAMA_URL}/api/chat"); then
      grund=$(jq -r '.done_reason // ""' <<< "$antwort")
      text=$(jq -r '.message.content // ""' <<< "$antwort" \
             | awk '/<think>/{skip=1} !skip{print} /<\/think>/{skip=0}')
      if [[ "$grund" == "stop" && ${#text} -ge 100 ]]; then
        printf '%s\n' "$text"
        return 0
      fi
      echo "    ! Antwort unbrauchbar (Grund: ${grund:-?}, ${#text} Zeichen), Versuch ${versuch}" >&2
    else
      echo "    ! Ollama nicht erreichbar, Versuch ${versuch}" >&2
    fi
  done
  return 1
}

# Geladene Ollama-Modelle aus dem Grafikspeicher werfen (Platz für Whisper)
ollama_entladen() {
  local modell
  for modell in $(curl -fsS "${OLLAMA_URL}/api/ps" 2>/dev/null | jq -r '.models[].name' 2>/dev/null); do
    echo "  Entlade Ollama-Modell ${modell}"
    curl -fsS -o /dev/null "${OLLAMA_URL}/api/generate" \
      -d "$(jq -n --arg m "$modell" '{model: $m, keep_alive: 0}')" || true
  done
}

# --- Phase 1: Aufnahmen transkribieren -------------------------------
echo
echo "===== Phase 1: Transkribieren ====="

mapfile -t aufnahmen < <(find "$EINGANG" -maxdepth 1 -type f -iname '*.mp3' \
                           -mmin +"$MIN_ALTER_MINUTEN" | sort)
echo "${#aufnahmen[@]} Aufnahme(n) im Eingang"
(( ${#aufnahmen[@]} > 0 )) && ollama_entladen
transkribiert=0

for datei in "${aufnahmen[@]}"; do
  name=$(basename "$datei")
  name="${name%.*}"                                    # Endung .mp3 abschneiden
  name="${name%"${name##*[![:space:]]}"}"              # Leerzeichen am Ende abschneiden
  echo "→ ${name}"

  # "Betriebssysteme 23.10.26" oder "BeSy 23.10.26 Übung" → Fachteil + Datum (+ optionaler Zusatz)
  if [[ ! "$name" =~ ^(.+)[[:space:]_-]+([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{2,4})([[:space:]_-]+.+)?$ ]]; then
    echo "  ✗ Name passt nicht zum Muster '<Fach> <TT.MM.JJ> [Zusatz]' – bleibt liegen" >&2
    fehler=$((fehler + 1)); continue
  fi
  fachteil="${BASH_REMATCH[1]}"

  if ! fach=$(fach_finden "$fachteil"); then
    echo "  ✗ Kein Fachordner für '${fachteil}' gefunden – bleibt liegen" >&2
    fehler=$((fehler + 1)); continue
  fi
  echo "  Fach: ${fach}"

  # Vorher prüfen, ob das Archiv frei ist – sonst würde die Datei jede Nacht neu transkribiert
  archiv_ziel="${ARCHIV}/${fach}/${name}.mp3"
  if [[ -e "$archiv_ziel" ]]; then
    echo "  ✗ Im Archiv existiert schon '${name}.mp3' – bitte umbenennen oder prüfen, bleibt liegen" >&2
    fehler=$((fehler + 1)); continue
  fi

  # Vor der langen Transkription prüfen, ob alle Ziele beschreibbar sind
  ohne_recht=""
  for ordner in "${SEMESTER}/${fach}/${TRANSKRIPT_ORDNER}" \
                "${SEMESTER}/${fach}/${ZUSAMMENFASSUNG_ORDNER}" \
                "${ARCHIV}/${fach}"; do
    beschreibbar "$ordner" || ohne_recht+=$'\n'"     ${ordner}"
  done
  if [[ -n "$ohne_recht" ]]; then
    echo "  ✗ Keine Schreibrechte für:${ohne_recht}"$'\n'"    – bleibt liegen" >&2
    fehler=$((fehler + 1)); continue
  fi

  ziel_txt="${SEMESTER}/${fach}/${TRANSKRIPT_ORDNER}/${name}.txt"
  start=$SECONDS
  if ! text=$(curl -fsS --max-time 7200 -F "audio_file=@${datei}" \
        "${WHISPER_URL}/asr?task=transcribe&language=de&output=txt&encode=true&vad_filter=true"); then
    echo "  ✗ Whisper-Fehler – bleibt liegen, nächste Nacht neuer Versuch" >&2
    fehler=$((fehler + 1)); continue
  fi
  if (( ${#text} < 200 )); then
    echo "  ✗ Transkript verdächtig kurz (${#text} Zeichen) – bleibt liegen" >&2
    fehler=$((fehler + 1)); continue
  fi

  if ! speichern "$ziel_txt" "$text"; then
    echo "  ✗ Transkript konnte nicht gespeichert werden – Aufnahme bleibt liegen" >&2
    fehler=$((fehler + 1)); continue
  fi
  echo "  ✓ Transkript: $(wc -w < "$ziel_txt") Wörter in $(( (SECONDS - start) / 60 )) Min."
  printf '%s\t%s\n' "$fach" "$name" >> "$WARTESCHLANGE"
  transkribiert=$((transkribiert + 1))

  # Original archivieren – erst NACH dem Speichern des Transkripts
  if mv -n "$datei" "$archiv_ziel" 2>/dev/null && [[ ! -e "$datei" ]]; then
    echo "  ✓ Archiviert"
  else
    echo "  ! Archivieren fehlgeschlagen – Original bleibt im Eingang" >&2
    fehler=$((fehler + 1))
  fi
done

# --- Phase 2: Zusammenfassen -----------------------------------------
echo
echo "===== Phase 2: Zusammenfassen ====="

if [[ ! -s "$WARTESCHLANGE" ]]; then
  echo "Nichts zu tun"
else
  if (( transkribiert > 0 )); then
    echo "Warte ${WHISPER_PAUSE} s, bis Whisper den Grafikspeicher freigibt …"
    sleep "$WHISPER_PAUSE"
  fi

  SYSTEM_ABSCHNITT=$(cat "${SKRIPT_DIR}/prompts/abschnitt.txt")
  SYSTEM_GESAMT=$(cat "${SKRIPT_DIR}/prompts/zusammenfassung.txt")
  offen=()

  while IFS=$'\t' read -r fach name; do
    [[ -z "$fach" ]] && continue
    quelle="${SEMESTER}/${fach}/${TRANSKRIPT_ORDNER}/${name}.txt"
    ziel_md="${SEMESTER}/${fach}/${ZUSAMMENFASSUNG_ORDNER}/${name}.md"
    echo "→ ${name}"

    if [[ ! -s "$quelle" ]]; then
      echo "  ✗ Transkript fehlt – aus der Warteschlange entfernt" >&2
      continue
    fi

    # Transkript in Abschnitte zu je N Wörtern teilen, jeden einzeln zusammenfassen
    read -r -d '' -a woerter < "$quelle"
    gesamt=${#woerter[@]}
    notizen="" ; teil=0 ; ok=1
    for (( i = 0; i < gesamt; i += WOERTER_PRO_ABSCHNITT )); do
      teil=$((teil + 1))
      abschnitt="${woerter[*]:i:WOERTER_PRO_ABSCHNITT}"
      echo "  Abschnitt ${teil} (ab Wort ${i} von ${gesamt})"
      if ! ergebnis=$(ollama_fragen "$SYSTEM_ABSCHNITT" "$abschnitt" 1200); then
        ok=0; break
      fi
      notizen+=$'\n\n'"### Abschnitt ${teil}"$'\n'"${ergebnis}"
    done

    # Aus allen Abschnitts-Notizen die eigentliche Zusammenfassung bauen
    if (( ok )) && zusammenfassung=$(ollama_fragen "$SYSTEM_GESAMT" "$notizen" 3000) &&
       speichern "$ziel_md" "# ${name}"$'\n\n'"${zusammenfassung}"$'\n\n'"---"$'\n'"*Automatisch erstellt aus der Vorlesungsaufnahme mit Whisper und ${MODELL}. Bei Unklarheiten das Transkript prüfen.*"; then
      echo "  ✓ Zusammenfassung gespeichert"
    else
      echo "  ✗ Zusammenfassung fehlgeschlagen – nächste Nacht neuer Versuch" >&2
      offen+=("$(printf '%s\t%s' "$fach" "$name")")
      fehler=$((fehler + 1))
    fi
  done < "$WARTESCHLANGE"

  # Nur die fehlgeschlagenen bleiben in der Warteschlange
  if (( ${#offen[@]} > 0 )); then
    printf '%s\n' "${offen[@]}" > "${WARTESCHLANGE}.tmp"
  else
    : > "${WARTESCHLANGE}.tmp"
  fi
  mv "${WARTESCHLANGE}.tmp" "$WARTESCHLANGE"
fi

# --- Abschluss -------------------------------------------------------
ls -1t "${LOG_DIR}"/transkript-*.log | tail -n +$(( LOGS_BEHALTEN + 1 )) | xargs -r rm -f
echo
echo "Ende: $(date '+%d.%m.%Y %H:%M:%S'), Dauer $(( SECONDS / 60 )) Min., Fehler: ${fehler}"
(( fehler == 0 ))
