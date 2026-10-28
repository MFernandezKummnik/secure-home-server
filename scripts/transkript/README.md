# Lecture Transcription & Summaries (Whisper + Ollama)

Every night at 01:00 the server picks up lecture recordings that arrived from the E-Ink tablet, transcribes them locally on the GPU, writes a structured study summary with a local LLM, files both into the right course folder and archives the audio. Everything runs on my own hardware; no audio or text leaves the server.

```text
Semester2/mp3Dateien/BeSy 23.10.26.mp3          ← synced from the tablet (Syncthing)
   │ 1. parse name: course "BeSy" (alias → Betriebssysteme), date 23.10.26
   │ 2. check write permissions of all targets
   │ 3. Whisper large-v3 (GPU, int8)
   ├──► Semester2/Betriebssysteme/vorlesungstranskripte/BeSy 23.10.26.txt
   │ 4. Ollama qwen3.5:9b, map-reduce over sections
   ├──► Semester2/Betriebssysteme/ZusammenfassungVorlesung/BeSy 23.10.26.md
   │ 5. archive original (outside the synced share → frees space on the tablet)
   └──► Vorlesungsarchiv/Betriebssysteme/BeSy 23.10.26.mp3
```

> The script, its comments and the prompts are in German, as the course material is German.

---

## Naming Convention

`<course> <DD.MM.YY> [suffix].mp3` – e.g. `Betriebssysteme 23.10.26.mp3` or `BeSy 01.10.26 Übung.mp3`.

* The course part is matched against the folder names in `Semester2` ignoring case, spaces, `_` and `-` (`Algorithmen und Datenstrukturen` → `AlgorithmenUndDatenstrukturen`).
* Short names are defined in [`aliase.conf`](aliase.conf) (`BeSy = Betriebssysteme`).
* The optional suffix allows several recordings per course and day.
* Files that match no course, or whose name cannot be parsed, stay in the inbox and are reported in the log instead of being guessed.

## Design Decisions

| Decision | Reasoning |
| :--- | :--- |
| **Nightly batch instead of a folder watcher** | The 8 GB GPU is shared with Ollama (newspaper, calendar bot). At night nothing competes, and next-morning results are fast enough for lectures. Starting at 01:00 leaves three hours before the weekly newspaper (Wednesdays 04:00) needs the same GPU. |
| **Whisper `large-v3` with `int8`** | The GTX 1070 (Pascal) has no efficient `float16`. `int8` runs the most accurate model in ~3.4 GB VRAM. |
| **VRAM hand-over** | Before transcribing, all loaded Ollama models are unloaded (`keep_alive: 0`); before summarizing, the script waits until Whisper has released its model (`MODEL_IDLE_TIMEOUT`). |
| **Map-reduce summaries** | A 90-minute lecture (~12,000 words) does not fit into the model's context. Each 2,000-word section is condensed to notes first, then all notes are merged into the final summary. Responses are only accepted with `done_reason: stop` (no truncated text), with up to 3 retries. |
| **Safe ordering** | Permissions are checked *before* the long transcription; the audio is archived only *after* the transcript was saved and verified. A failure at any point leaves the recording in the inbox for the next night. |
| **Summary queue** | Successful transcripts are queued for summarizing; failed summaries stay queued and are retried without re-transcribing. Existing older transcripts are never touched. |
| **Minimum file age (10 min)** | Recordings still being synced from the tablet are skipped until complete. |
| **Least privilege** | Runs as `99:100` in the existing Alpine tool container of the newspaper; Whisper and Ollama are only reachable on `127.0.0.1`. |

## Reworked Components

* **Automation:** the previous approach – an n8n workflow watching the folder – was replaced by this Bash script run nightly via Unraid *User Scripts*, in line with the decision to retire n8n.
* **Whisper container:** the standalone `faster-whisper-server` container was replaced by [`docker/whisper/`](../../docker/whisper/) (`whisper-asr-webservice` with the same faster-whisper engine). The previous container ended up running the CPU image with a `float16` setting the GPU cannot use efficiently; the new one runs on the GPU with `int8`, and its model unloads when idle so it does not block VRAM.
* **Summaries:** now generated locally by Ollama instead of a cloud API.

## Lessons Learned

* **Verify every write before deleting or moving the source.** The first real test transcribed successfully but could not save the transcript (one target folder was not writable for the container user). The script did not check the result of the save step and archived the audio anyway. Fixed by checking all target permissions up front and verifying the saved file before archiving – found in testing, no recording was lost.
* **Real file names are messier than planned:** typos in dates, abbreviations, two recordings per day, trailing spaces. Strict parsing plus aliases and an optional suffix covers these without guessing.

## Files

| File | Purpose |
| :--- | :--- |
| `transkript.sh` | The pipeline (inbox → transcript → summary → archive), with lock and log |
| `aliase.conf` | Short names for courses |
| `prompts/abschnitt.txt` | Prompt: condense one section into notes |
| `prompts/zusammenfassung.txt` | Prompt: merge notes into the study summary |
| `user-script.sh` | Unraid *User Scripts* entry, schedule `0 1 * * *` |

## Setup

```bash
mkdir -p /mnt/user/appdata/transkript/prompts   # copy the files from this folder
chmod +x /mnt/user/appdata/transkript/transkript.sh
chown -R 99:100 /mnt/user/appdata/transkript
```
Whisper: see [`docker/whisper/`](../../docker/whisper/). The script reuses the `zeitung` tool image (bash, curl, jq) from [`scripts/zeitung/`](../zeitung/).

Manual test run (skips the minimum file age and the VRAM wait):
```bash
docker run --rm --network host --user 99:100 \
  -e MIN_ALTER_MINUTEN=0 -e WHISPER_PAUSE=10 \
  -v /mnt/user/appdata/transkript:/app \
  -v /mnt/user/Semester2:/semester \
  -v /mnt/user/Vorlesungsarchiv:/archiv \
  zeitung ./transkript.sh
```

---

## Transparency Note

The scripts in this folder were written with the help of an AI assistant (Claude by Anthropic). I worked through every part together with it, tested it on my own server with real recordings, and can explain what each part does and why. Transcription and summaries are produced entirely by open-weight models running locally on my hardware.
