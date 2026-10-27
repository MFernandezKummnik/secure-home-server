# Local AI Weekly Newspaper (Bash + Ollama)

A fully local, cloud-free weekly newspaper. Every Wednesday at 04:00 the server collects news from RSS/Atom feeds, has a local LLM (Ollama on the GTX 1070) write a German-language edition, renders it as a self-contained HTML page and syncs the newest issue to the Onyx Boox E-Ink tablet via Syncthing.

**Sections**

| Section | Content | Approx. reading time |
| :--- | :--- | :--- |
| Innenpolitik | German domestic policy: the past week, with a *"What does this mean?"* assessment per topic | ~7 min |
| Außenpolitik | Foreign policy with a focus on Germany and Europe | ~5 min |
| Cybersecurity & Open Source | Vulnerabilities, incidents, releases and project decisions | ~4 min |
| Märkte & Investitionen | Economy and markets, plus opportunities and risks currently discussed (no buy/sell advice) | ~4 min |

> The scripts, comments and prompts are written in German, as the newspaper itself is German.

---

## Architecture & Data Flow

```text
[ Unraid User Scripts: cron "0 4 * * 3" ]
          │
          ▼
[ docker run zeitung ./zeitung.sh ]  (Alpine tool container, scripts mounted from appdata)
          │
          ├── 1. sammeln.sh ──────── RSS/Atom feeds (curl + xmlstarlet)
          │                          → daten/meldungen.tsv (last 7 days, deduplicated)
          │
          ├── 2. schreiben.sh ────── one Ollama request per section (qwen3.5:9b)
          │                          → daten/<section>.md
          │
          ├── 3. zusammensetzen.sh ─ Markdown → HTML (cmark), table of contents,
          │                          reading times, source links per section
          │                          → ausgabe/zeitung-<year>-KW<week>.html + index.html
          │
          └── 4. verteilen.sh ────── newest issue → boox/ (Syncthing "Send Only")
                                     → Onyx Boox Go 10.3 ("Receive Only")

[ nginx:alpine ] serves ausgabe/ read-only on the LAN / via Tailscale
```

## Why It Is Built This Way

This is a rewrite of an earlier Bash + Ollama version that produced truncated paragraphs and aborted runs. The redesign addresses the root causes directly:

| Problem in the old version | Solution |
| :--- | :--- |
| Ollama's small default context window silently cut off input | `num_ctx` set explicitly; input capped at 20 items × 600 characters per section |
| One giant request for the whole newspaper | One request per section; politics split into two sections |
| Truncated answers were accepted as finished | `done_reason` must be `stop`, plus a minimum length; otherwise up to 3 retries |
| Errors went unnoticed | `set -euo pipefail`, per-step exit codes, logs with step durations |
| A broken feed broke everything | Each feed fails independently and is reported |

**Further design decisions**

* **Tool container instead of host packages:** Unraid ships without `jq`, `xmlstarlet` or `cmark`. A small Alpine image keeps the host clean and survives OS updates.
* **Grounded writing:** The system prompt forbids facts, numbers or quotes that are not in the supplied items, asks for cautious wording in the assessments, and the source links are taken from the feed data, never from the model.
* **Atomic writes:** Pages and synced files are written to a temporary file and moved into place with `mv`, so readers and Syncthing never see a half-written file, and a crash leaves the previous issue intact.
* **Failure strategy per step:** No items → abort and keep the old issue. A section fails → the issue is still built and the gap is clearly marked. Boox sync fails → the issue is still available in the browser.
* **Single run lock:** An atomic `mkdir` lock prevents overlapping runs; stale locks from crashes are removed after 12 hours.
* **Safe rendering:** All feed text is HTML-escaped, only `http(s)` links are linked, and `cmark` drops raw HTML from model output.

---

## Files

| File | Purpose |
| :--- | :--- |
| `Dockerfile` | Alpine image with bash, curl, jq, xmlstarlet, coreutils, tzdata, cmark |
| `feeds.conf` | Feed list: `section\|source name\|url` |
| `sammeln.sh` | Step 1 – fetch, parse, filter and deduplicate feed items |
| `schreiben.sh` | Step 2 – one Ollama request per section with validation and retries |
| `zusammensetzen.sh` | Step 3 – build the HTML newspaper |
| `verteilen.sh` | Step 4 – copy the newest issue to the Boox folder, remove older issues |
| `zeitung.sh` | Runs all steps, logging, lock, timing |
| `prompts/` | System prompt and one prompt per section (editable without touching code) |
| `vorlage/stil.css` | Newspaper layout, light/dark mode, mobile |
| `user-script.sh` | Content for the Unraid *User Scripts* plugin |

## Setup

```bash
# 1. Copy this folder to the server
mkdir -p /mnt/user/appdata/zeitung        # copy the files into it
cd /mnt/user/appdata/zeitung
chmod +x *.sh

# 2. Build the tool container
docker build -t zeitung .

# 3. Folder for the Boox (owned by the Syncthing container user)
mkdir -p boox && chown nobody:users boox

# 4. Test run
docker run --rm -v /mnt/user/appdata/zeitung:/app zeitung ./zeitung.sh

# 5. Web server for reading in the browser
docker run -d --name zeitung-web --restart unless-stopped \
  -p 8099:80 \
  -v /mnt/user/appdata/zeitung/ausgabe:/usr/share/nginx/html:ro \
  nginx:alpine
```

**Schedule:** Unraid → Settings → User Scripts → new script with the content of `user-script.sh`, schedule *Custom* `0 4 * * 3` (Wednesdays at 04:00, server time zone).

**Syncthing:** Map `/mnt/user/appdata/zeitung/boox` into the Syncthing container, share it as *Send Only* on the server and *Receive Only* on the Boox.

**Settings via environment variables** (defaults in brackets): `MODELL` (`qwen3.5:9b`), `KONTEXT` (`8192`), `OLLAMA_URL` (`http://172.17.0.1:11434`, the Docker host), `TAGE_ZURUECK` (`7`), `BOOX_DIR` (`./boox`).

---

## Transparency Note

The scripts in this folder were written with the help of an AI assistant (Claude by Anthropic). I worked through every step together with it, tested each component on my own server, and can explain what every part of the code does and why it is built this way. The newspaper content itself is generated entirely locally by an open-weight model running on my own hardware.
