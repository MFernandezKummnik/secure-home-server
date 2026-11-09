# Self-Hosted Cloud-Free Home Server & Infrastructure

[ **English** ](README.md) | [ Deutsch ](README.de.md)

[![OS: Linux / Unraid](https://img.shields.io/badge/OS-Unraid_Linux-orange.svg)](https://unraid.net/)
[![Stack: Docker](https://img.shields.io/badge/Stack-Docker_%7C_Jellyfin_%7C_Tdarr-brightgreen.svg)]()

Repository documenting my self-built, fully cloud-free home server. The system serves as central infrastructure for data storage with drive-failure protection, media management, university organization, and automated background workflows.

---

## 1. Why a Home Server of My Own?

* **Complete Data Sovereignty & Privacy:** Replacing commercial cloud providers. My confidential data, documents, and notes remain physically on my own storage devices - without tracking, data analysis, or third-party access rights.
* **Independence from Streaming Platforms:** No dependency on subscription models, price increases, ads, geoblocking, or content disappearing due to licensing reasons.
* **Focus & Mindful Media Consumption:** Self-hosted media libraries free of recommendation algorithms, scroll spirals, and advertising interruptions.
* **Digitization & Long-Term Archiving:** Losslessly digitizing, organizing, and permanently preserving physical media (e.g., my own CDs, DVDs, textbooks).
* **Centralization of University Documents:** An organized place, protected against single-drive failure (parity), for all lecture materials, notes, and scripts - accessible from any device.
* **Costs:** A one-time hardware purchase instead of recurring monthly cloud subscriptions.
* **Hands-On IT Lab:** Learning Linux administration, containers, storage and IT security by running a real system, alongside my studies.

---

## 2. Hardware Used & Technical Rationale

| Component | Model | Why |
| :--- | :--- | :--- |
| **CPU** | Intel Core i3-12100 | 4 cores / 8 threads. The UHD 730 iGPU has **Intel QuickSync** for hardware transcoding in Jellyfin and Tdarr. |
| **GPU (AI / Acceleration)** | Nvidia GeForce GTX 1070 (8 GB) | Inexpensive card with 8 GB VRAM for local AI: Ollama and Whisper transcription. Containers access it through the Nvidia driver plugin. |
| **Motherboard** | Gigabyte B760M DS3H DDR4 GEN5 | Micro-ATX board with enough SATA ports for the drives and an onboard 2.5 GbE LAN port. |
| **RAM** | 32 GB Crucial Pro DDR4-3200 (2x16GB) | Dual channel; enough headroom for many containers running at the same time. |
| **System SSD** | 1 TB WD Blue SN580 NVMe M.2 | Holds the container data (appdata) and serves as the write cache, so the HDDs can stay spun down more often. |
| **HDDs (Array)** | 2x 10 TB HPE Enterprise HDDs (3.5", CMR) | Bought used. One is the parity drive, one a data drive; parity protects against the failure of one drive. |
| **HDDs (Array, reused)** | 1x 500 GB (from a 2012 laptop) + 1x 250 GB (from an old receiver) | Additional data drives in the same array, added from spare hardware. Each data drive has its own file system; the parity drive (10 TB) is at least as large as the largest data drive. Data, including university files, is spread across the data drives (High-water allocation). |
| **Optical Drive**| LG HLDS BU40N Ultra Slim UHD Burner | Slim drive connected via USB adapter, used for reading my own Blu-ray discs. *Note:* Reading is strictly within the bounds of applicable copyright law (§ 95a UrhG, German copyright act); no circumvention of effective copy-protection mechanisms. |
| **Boot Media** | 64 GB Samsung BAR Plus (USB 3.1) | Unraid boots from a USB stick and runs from RAM. |
| **CPU Cooler** | Thermalright Assassin X 120 SE | Quiet tower cooler with a 120 mm fan. |
| **Power Supply** | be quiet! System Power 11 450W (80+ Bronze) | Enough for the current setup including the GTX 1070. Limitation: a more power-hungry GPU would need a bigger power supply. |
| **Case** | Fractal Design Define R5 (Black) | Sound-dampened case with room for several 3.5" drives and dust filters. |

---

## 3. Software Architecture & Media Stack

The system uses **Unraid OS** as its host operating system (stateless boot concept from RAM) and runs all applications in **Docker containers**.

```text
+-------------------------------------------------------------------+
|                     DOCKER APPLICATION STACK                      |
| +------------+---------------+------------------+---------------+ |
| | Jellyfin   | Navidrome     | Tdarr Engine     | Ollama        | |
| | (Video)    | (Music)      | (Transcoding)    | (Local AI)    | |
| +------------+---------------+------------------+---------------+ |
| | Administrative Tools, Syncthing & Tailscale Mesh-VPN          | |
+---------------------------------------+---------------------------+
                                        | (Controlled I/O access)
                                        v
+----------------------------------------------------------------------------+
|                              STORAGE TIERING                               |
|  +--------------------------+   +-----------------------------------+      |
|  |  NVMe CACHE (1 TB)       |   |  PARITY ARRAY (4 HDDs)            |      |
|  |  Docker Appdata &        |-->|  Parity: 10 TB                    |      |
|  |  Inbound Files           |   |  Data: 10 TB, 500 GB, 250 GB      |      |
|  +--------------------------+   +-----------------------------------+      |
+----------------------------------------------------------------------------+
```

### 3.1 Video Streaming & Home Theater (Jellyfin)

**Direct Play & Hardware Acceleration:** Open-source media server. If a device can play a file as it is, Jellyfin sends it unchanged (Direct Play); otherwise it transcodes it on the Intel UHD 730 (QuickSync).

**Clients:** Streaming sticks on the home network and the phone on the go (via Tailscale).

### 3.2 Music Library (Navidrome)

**Lightweight Music Server:** Written in Go, serves my own CD rips (FLAC/MP3).

**Subsonic API:** Works with common music apps on iPhone and Android, in the car or on the go, without a streaming subscription.

### 3.3 Automated Media Optimization (Tdarr Pipeline)

* **Resolution-Aware Transcoding Logic:** 
  * **Low-Resolution Content (SD/DVD):** Processed via **CPU (x265)** to maintain maximum visual accuracy, preventing block artifacts and quality degradation.
  * **High-Resolution Content (1080p/4K):** Offloaded to **Intel QuickSync (GPU)** for high-throughput, energy-efficient H.265 transcoding.
* **Automated Flow Pipeline:** Reads raw MKVs from `/watch_folder`, analyzes codec/bitrate/resolution, transcodes selectively, and automatically moves processed files to the final Jellyfin media library.

**Result:** Smaller files with little visible quality loss, which saves space on the HDDs and bandwidth when streaming.

### 3.4 Automated E-Ink Workflow & Lecture Transcription (Syncthing, Whisper & Ollama)

* **Document Sync:** Two-way synchronization between the Onyx Boox Go 10.3 tablet and the Unraid server using **Syncthing**, so lecture materials and handwritten notes end up on the server automatically.
* **Local Audio Transcription:** Lecture recordings from the tablet are transcribed every night by **Whisper `large-v3`** (faster-whisper engine, GPU-accelerated on the GTX 1070 with `int8`), without any cloud service.
* **Study Summaries:** A local LLM (**Ollama**) turns each transcript into a structured summary; transcript and summary are filed into the matching course folder automatically, and the audio is archived outside the synced share to free space on the tablet.
* **Automation Approach:** The earlier n8n orchestration has been retired because its maintenance effort and resource usage were out of proportion to the task. Automations on this server are now implemented as lightweight Bash scripts; the transcription pipeline runs as a nightly batch job (see [`scripts/transkript/`](scripts/transkript/)).

### 3.5 Local AI Weekly Newspaper (Bash & Ollama)

* **Fully Local News Digest:** Every Wednesday at 04:00, a chain of Bash scripts collects the past week's news from RSS/Atom feeds, has a local LLM (**Ollama**, `qwen3.5:9b` on the GTX 1070) write a German weekly newspaper (domestic & foreign policy with impact assessments, cybersecurity & open source, markets), and renders it as a self-contained HTML page with source links.
* **Reliability:** One validated model request per section (`done_reason` check, retries), explicit context window, atomic writes, run lock and per-step logging.
* **E-Ink Delivery:** The newest issue is synced to the Onyx Boox via Syncthing (*Send Only* / *Receive Only*); older issues are removed automatically. Details in [`scripts/zeitung/`](scripts/zeitung/).

### 3.6 Self-Hosted Calendar & Chat Bot (Radicale, Matrix & Ollama)

* **Own Calendar Server:** **Radicale** (CalDAV) replaces cloud calendars. The phone's native calendar app syncs directly with it; the semester schedule is imported as recurring events from a generated `.ics` file.
* **Private Chat Server:** A **continuwuity** Matrix homeserver with federation disabled, used with the Element X app.
* **Calendar Bot:** Messages like *"nächste Woche Dienstag Abgabe ALDA"* are parsed by a local LLM into structured fields, the date is calculated deterministically in code, and the event is written via CalDAV after an explicit confirmation. The bot can also list and delete events. Details in [`scripts/kalenderbot/`](scripts/kalenderbot/).
* **Zero Exposure:** Both services listen on `127.0.0.1` only and are reachable exclusively via HTTPS through `tailscale serve`, with tag-based ACLs per device (see [`docs/security-concept.md`](docs/security-concept.md)).

### 3.7 Network-Wide DNS Filtering (Pi-hole)

* **Pi-hole** answers the DNS queries of the home network via the router's DHCP settings and forwards to **Quad9** (DNSSEC, malware filter). The admin UI is only reachable inside the tailnet.
* **Honest result:** it does not remove ad banners on streaming devices and adds nothing in the browser (already covered by Brave); part of the traffic bypasses it via IPv6. It does remove **in-app ads on the smartphone** while on the home Wi-Fi, and is kept for that, for blocking tracking from apps and IoT devices, and for visibility into what each device contacts. Details and lessons learned in [`docker/pihole/`](docker/pihole/).

### 3.8 Password Manager & Encrypted Backups (Vaultwarden)

* **Self-Hosted Vault:** **Vaultwarden** (Bitwarden-compatible) replaces the browser's password storage and is used with the official Bitwarden apps on phone, laptop and PC. Zero-knowledge: entries are encrypted on the client, the server only stores ciphertext. Reachable only inside the tailnet via HTTPS; signups and the admin panel are disabled. Details in [`docker/vaultwarden/`](docker/vaultwarden/).
* **Verified Nightly Backups:** A consistent SQLite snapshot is encrypted (AES-256, separate passphrase), test-decrypted, stored on the HDD array and synced to the laptop, where versioning keeps deleted backups for 180 days. Details and lessons learned in [`scripts/vaultwarden-backup/`](scripts/vaultwarden-backup/).

### 3.9 Offline Backups (restic)

* **Two Stages:** Every night the *Appdata Backup* plugin stops each container briefly and archives its data together with the Unraid boot stick, so databases are captured consistently. Once a week a PowerShell script on the PC pulls the university data, music and these archives with **restic** onto an external HDD that stays disconnected the rest of the time.
* **Least Privilege:** The PC reads through a dedicated Unraid account with read-only access to exactly five shares; the backup share is read-only for every user, and `appdata` is no longer exported via SMB.
* **Encrypted, Deduplicated, Verified:** AES-256 encrypted repository, 8 weekly and 12 monthly snapshots, a 5 % data sample checked on every run, and a restore test with a matching SHA-256 hash. The restore test exposed a real bug (UNC paths cannot be restored on Windows), which is documented with the fix in [`scripts/restic-backup/`](scripts/restic-backup/).

### 3.10 Flashcards from Lecture Slides (Python & Claude API)

* **Slides to Anki:** Every evening the server turns new lecture slides (PDF) into one Anki package per lecture, which syncs to the Onyx Boox and is imported into AnkiDroid after a quick review. Stable card IDs mean an updated slide deck updates existing cards instead of duplicating them, so learning progress is kept.
* **The one deliberate cloud exception:** I first built it with local AI (`qwen3.5:9b` via Ollama) and tuned the prompt over five versions, checking every card against the slides. The results were not good enough: 0–2 factual errors per deck and core definitions randomly missing, which is risky when the cards are what you learn from. Claude Sonnet via the Anthropic API produced error-free, complete cards on the first try. At about **$0.09 per lecture, roughly $4.50 per semester**, the cost is more than justifiable. Only slide text (course material, no personal data) leaves the server; a prepaid API balance without auto-recharge caps the cost.
* **Reliability:** Enforced JSON schema, retries on truncated or refused responses, atomic writes, run lock, and a code-level filter for rules the model may ignore. Details, the full local-vs-cloud comparison and lessons learned in [`scripts/karteikarten/`](scripts/karteikarten/).

### 3.11 Job Alert Bot (Python, IMAP & Matrix)

* **Job Search Without Checking Portals:** LinkedIn job alerts for working-student positions are forwarded to a separate bot inbox. Every 30 minutes a short-lived Python container reads them via IMAP and posts each new position to a private Matrix room: one push per alert, one bubble per position with a clean link (tracking and login tokens removed).
* **Least Privilege:** The bot never gets access to my main inbox; a Gmail filter forwards only mails from the exact alert sender. No scraping: the portals' own e-mail alerts are used, which is reliable and within their terms of use.
* **Lessons learned:** The first version relied on "unread" mails and silently skipped a mail that had been opened by hand. It now looks at the last 3 days and deduplicates by job ID. Details in [`scripts/jobbot/`](scripts/jobbot/).

### 3.12 Morning Briefing (Python, CalDAV & Matrix)

* **One Message Before Getting Up:** Every morning at 05:00 a short-lived container reads today's events and the deadlines of the next 7 days from Radicale, adds the local weather forecast with a rain and frost hint (Open-Meteo, no account or key), and posts it to a private Matrix room. On Wednesdays it also checks that the new newspaper issue has reached the folder synced to the Boox.
* **Deliberately Simple:** A fixed template instead of an LLM, so nothing can be invented and nothing costs money. Each section fails on its own: if the weather API is down, the calendar still arrives.
* **Separate Credentials:** Sent as the calendar bot, but through its own login and token, so it can be revoked without affecting the bot. Details in [`scripts/morgenbriefing/`](scripts/morgenbriefing/).

## 4. Roadmap & Planned Extensions

- [x] E-Ink Pad Automation: Wireless document synchronization (Syncthing) for the Onyx Boox writing tablet.

- [ ] E-Book Server: Calibre-Web with OPDS for the Onyx Boox.

- [x] Local AI Transcription: Nightly pipeline with Whisper (GPU) and Ollama that transcribes, summarizes, files and archives lecture recordings (see [`scripts/transkript/`](scripts/transkript/)).

- [x] Local AI Newspaper: Weekly news digest generated entirely on my own hardware with Bash and Ollama (see [`scripts/zeitung/`](scripts/zeitung/)).

- [x] Self-Hosted Calendar & Chat: Radicale, a private Matrix homeserver and a local-AI calendar bot (see [`scripts/kalenderbot/`](scripts/kalenderbot/)).

- [x] DNS Filtering: Pi-hole for tracker blocking and device visibility (IPv6 bypass still open, see [`docker/pihole/`](docker/pihole/)).

- [x] Self-Hosted Password Manager: Vaultwarden, reachable only inside the tailnet (see [`docker/vaultwarden/`](docker/vaultwarden/)).

- [x] Encrypted Backups for the Password Manager: Nightly, verified backups to the HDD array and the laptop (see [`scripts/vaultwarden-backup/`](scripts/vaultwarden-backup/)).

- [x] Backups for the Remaining Data: Nightly consistent container archives on the server and a weekly encrypted offline backup with restic, verified by a restore test (see [`scripts/restic-backup/`](scripts/restic-backup/)).

- [x] Flashcards from Lecture Slides: Nightly Anki decks from lecture PDFs; local AI tested first, switched to the Claude API for card quality at about $4.50 per semester (see [`scripts/karteikarten/`](scripts/karteikarten/)).

- [x] Job Alert Bot: Job alerts from LinkedIn as Matrix messages on the phone, deduplicated and without tracking links (see [`scripts/jobbot/`](scripts/jobbot/)). Indeed parser still open.

- [x] Morning Briefing: Daily Matrix message with today's events, upcoming deadlines and the weather (see [`scripts/morgenbriefing/`](scripts/morgenbriefing/)).

- [x] Network Hardening: Tag-based Tailscale ACLs that limit each mobile device to the services it needs (see [`docs/security-concept.md`](docs/security-concept.md)).

## 5. Repository Structure

The subfolders contain the specific configurations and in-depth documentation:

* **[`docs/`](docs/):** Detailed documentation on hardware architecture, network topology, and security concepts.

* **[`docker/`](docker/):** Modularly organized Docker Compose files for Jellyfin, Navidrome, Tdarr, Whisper, Radicale, continuwuity (Matrix), Pi-hole, Vaultwarden, and administrative tools.

* **[`scripts/`](scripts/):** Custom Bash scripts and automated pipelines, including the **local AI weekly newspaper** (`scripts/zeitung/`) the **calendar bot** (`scripts/kalenderbot/`), the **lecture transcription** (`scripts/transkript/`), the **flashcards from lecture slides** (`scripts/karteikarten/`), the **job alert bot** (`scripts/jobbot/`), the **morning briefing** (`scripts/morgenbriefing/`), the **Vaultwarden backup** (`scripts/vaultwarden-backup/`) and the **offline backup with restic** (`scripts/restic-backup/`).

---

## Author

**Miguel**

Student of Business Information Systems (HTWG Konstanz)

**Focus Areas:** IT Security Architecture, System Administration & Cloud-Free Homelabs

**Contact:** [LinkedIn](https://www.linkedin.com/in/miguel-angel-fernandez-kummnik) | [Email](mailto:fernandezkummnikm@gmail.com)
