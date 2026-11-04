# Anki Flashcards from Lecture Slides (Python + Claude API)

Every evening at 23:00 the server looks for new lecture slides (PDF), has an LLM write flashcards from them and saves one Anki package per lecture. The package lands on the Onyx Boox via Syncthing, where it is reviewed and imported into AnkiDroid.

```text
Semester2/Betriebssysteme/Folien/VL04 Prozesse.pdf      ← downloaded from the university platform
   │ 1. new or changed? (SHA-256 against daten/erledigt.json)
   │ 2. check write permissions of the target folder
   │ 3. pdftotext → text per slide, skip slides without text
   │ 4. Claude Sonnet via API, 6 slides per request, JSON schema enforced
   │ 5. validate, drop duplicates and empty cards
   ├──► Semester2/Betriebssysteme/Karteikarten/VL04 Prozesse.apkg   (import into AnkiDroid)
   └──► Semester2/Betriebssysteme/Karteikarten/VL04 Prozesse.md     (preview for reviewing)
```

> The script, its comments and the prompt are in German, as the course material is German.

## Why a Cloud Model Instead of Local AI

This is the one automation on the server that does **not** run on local AI, and that is a deliberate, tested decision rather than a default.

**What I tried first:** The pipeline was built local-first, like the transcription and the newspaper: `qwen3.5:9b` via Ollama on the GTX 1070. I tuned the prompt over five versions on the same 37-slide lecture and checked every single card against the PDF.

**Why the result was not good enough:**

| | Local model (best runs) | Claude Sonnet (API) |
| :--- | :--- | :--- |
| Factual errors per deck | 0–2, varying from run to run | 0 |
| Core definitions (e.g. best/worst/average case) | skipped in several runs | covered |
| Rules followed (no self-solved exercises, no "see slide 23") | inconsistently | yes |
| Review effort | every card must be checked | quick skim |

Each prompt fix for one weakness caused a new one elsewhere – a sign of the model's limit, not the prompt's. And wrong flashcards are worse than none: a student reviewing cards *before* learning the topic cannot reliably spot an error like "n^0.5678 grows faster than n log n".

**Why the cost is more than justifiable:** One lecture deck costs about **$0.09**. With four courses (the problem-solving course *Mathematik2* is excluded), that is roughly **$4.50 per semester** – far less than one textbook, for error-free cards from every lecture. The API account has no auto-recharge, so the prepaid credit is a hard cost cap.

**Trade-off:** The slide text (course material, no personal data) is sent to Anthropic. Everything personal – recordings, transcripts, notes, calendar, passwords – stays on the server. Switching back to local is one line in `geheim.env`.

---

## Usage

1. Save the slides of a lecture as PDF in `Semester2/<course>/Folien/`. The file name becomes the name of the sub-deck, e.g. `VL04 Prozesse.pdf` → deck `Semester2::Betriebssysteme::VL04 Prozesse`.
2. The next evening, `Karteikarten/` contains the `.apkg` and a Markdown preview.
3. On the Boox: open the `.apkg` from the synced folder with AnkiDroid (or *AnkiDroid → Import*). Wrong or weak cards are deleted or edited in AnkiDroid's card browser. Every card shows its source slide, so it can be checked against the PDF.

## Design Decisions

| Decision | Reasoning |
| :--- | :--- |
| **Slides instead of transcripts** | Not every lecture is recorded, but slides exist for every lecture. They are also already structured and contain the exact terms used in the exam. |
| **Review before import** | Generated cards are a draft. One package per lecture plus a readable preview keeps the human in the loop; nothing is written into the Anki collection automatically. |
| **Python instead of Bash** | An `.apkg` is a ZIP with an SQLite database. `genanki` builds it reliably; doing this by hand in Bash would be fragile. |
| **Structured output** | The JSON schema is passed to the model (`output_config` for Claude, `format` for Ollama, `response_format` for OpenAI-compatible APIs). Truncated or refused responses and invalid JSON are rejected, with up to 3 retries. |
| **Stable IDs** | Note IDs are derived from course + question, deck IDs from the deck name. Re-importing an updated package updates existing cards instead of duplicating them, so review progress is kept. |
| **Small batches (6 slides)** | Keeps each request well inside the 8,192-token context of the local model (which caused truncated output in the first newspaper version) and keeps cloud responses short and focused. |
| **Batches know each other** | Each request also receives the last 40 questions already generated, so content repeated across slides (e.g. "binary search halves the search space") is not asked twice. |
| **Header/footer removal** | Lines of 15+ characters that appear on at least half of the slides (author, copyright) are removed before prompting. Saves context and noise. |
| **Prompt tuned on real slides** | The first real run (37 slides, 45 cards) was checked card by card against the PDF: ~30 good, but also cards on measured timings, code-example details, questions referring to "the given code", near-duplicates and one mixed-up example. The prompt rules address each of these. |
| **Swappable model** | `KI_ANBIETER=anthropic` (Claude API), `ollama` (local, script default) or `openai` (any OpenAI-compatible API). Switching is one line in `geheim.env`, no code change. |
| **Cloud instead of local** | See [Why a Cloud Model Instead of Local AI](#why-a-cloud-model-instead-of-local-ai). |
| **23:00, nightly batch** | New slides are usually downloaded during the day. With the local model this time also keeps the GPU free for Whisper at 01:00. |
| **Safe ordering** | Permissions are checked *before* the model runs; files are written atomically (temp file + rename) so Syncthing never sees a half-written package; a PDF is only marked as done after both files were saved. Failed PDFs are retried the next evening. |
| **Untrusted model output** | Card text is HTML-escaped before it goes into Anki; slide numbers the model invents are corrected to the batch's first slide. |
| **E-Ink friendly cards** | Plain black-on-white card template with large font, readable on the Boox display. |

## Limitations

* Superscripts are lost in text extraction (`2n2` instead of 2n²). The prompt tells the model to infer exponents from context, which works most of the time but caused one wrong card in testing; formula-heavy courses need a closer review.
* Slides that consist only of images or diagrams are skipped (no text to extract); scanned PDFs are reported and not processed.
* Handouts with several slides per page are treated as one "slide" per page, so the slide number on a card refers to the PDF page.
* If a professor uploads a revised PDF, it is processed again. Unchanged questions update the existing cards; reworded questions appear as new cards.

## Files

| File | Purpose |
| :--- | :--- |
| `karteikarten.py` | The pipeline (find PDFs → extract → generate → validate → package), with lock and log |
| `prompts/karten.txt` | Prompt with the rules for good cards (editable without rebuilding) |
| `Dockerfile` | Python 3.12 slim with `poppler-utils` (pdftotext) and `genanki` |
| `requirements.txt` | Python dependencies |
| `user-script.sh` | Unraid *User Scripts* entry, schedule `0 23 * * *` |

## Setup

```bash
# 1. Copy this folder to the server
mkdir -p /mnt/user/appdata/karteikarten        # copy the files into it
cd /mnt/user/appdata/karteikarten

# 2. Build the tool image (contains only Python, libraries and pdftotext;
#    the script itself is mounted from appdata)
docker build -t karteikarten .
chown -R 99:100 /mnt/user/appdata/karteikarten

# 3. API key (see below), then a test run on one lecture
docker run --rm --network host --user 99:100 \
  --env-file /mnt/user/appdata/karteikarten/geheim.env \
  -e MIN_ALTER_MINUTEN=0 -e NUR="<part of a PDF name>" \
  -v /mnt/user/appdata/karteikarten:/app \
  -v /mnt/user/Semester2:/semester \
  karteikarten
```

**Schedule:** Unraid → Settings → User Scripts → new script with the content of `user-script.sh`, schedule *Custom* `0 23 * * *`.

**Settings via environment variables** (defaults in brackets): `MODELL` (`qwen3.5:9b`), `KONTEXT` (`8192`), `OLLAMA_URL` (`http://127.0.0.1:11434`), `FOLIEN_ORDNER` (`Folien`), `KARTEN_ORDNER` (`Karteikarten`), `STAPEL_OBEN` (`Semester2`), `FOLIEN_PRO_ABSCHNITT` (`6`), `MAX_KARTEN_PRO_ABSCHNITT` (`8`), `MIN_ALTER_MINUTEN` (`10`), `ERZWINGEN` (`0`; `1` regenerates all packages), `AUSLASSEN` (empty; comma-separated course folders without flashcards, set to `Mathematik2` in `user-script.sh` because it is a problem-solving course), `NUR` (empty; only process PDFs whose path contains this text, e.g. for testing a prompt on one lecture).

**Model and API key** live in `/mnt/user/appdata/karteikarten/geheim.env` (never committed), passed with `--env-file`. Without it the script falls back to local Ollama.

```bash
# root:root, chmod 600 – read by Docker on the host, never by the container itself
KI_ANBIETER=anthropic
API_SCHLUESSEL=sk-ant-...
MODELL=claude-sonnet-5-5
```

For an OpenAI-compatible provider use `KI_ANBIETER=openai`, `API_URL=https://api.openai.com/v1` and that provider's model name.

With a cloud provider the slide text leaves the server. A monthly spend limit and no auto-recharge on the API account cap the cost.

---

## Transparency Note

The script in this folder was written with the help of an AI assistant (Claude by Anthropic). I worked through every part together with it, tested it, and can explain what each part does and why. The flashcards themselves are generated by Claude Sonnet via the Anthropic API; the comparison with the local model is described above.
