# Self-Hosted Cloud-Free Home Server & Infrastructure

[ **English** ](README.md) | [ Deutsch ](README.de.md)

[![OS: Linux / Unraid](https://img.shields.io/badge/OS-Unraid_Linux-orange.svg)](https://unraid.net/)
[![Security: Zero Trust](https://img.shields.io/badge/Security-Zero_Trust-emerald.svg)]()
[![Stack: Docker](https://img.shields.io/badge/Stack-Docker_%7C_Jellyfin_%7C_Tdarr-brightgreen.svg)]()

Repository documenting my self-built, fully cloud-free home server. The system serves as central infrastructure for data storage with drive-failure protection, media management, university organization, and automated background workflows following the principle of "Security by Design."

---

## 1. Why a Home Server of My Own? (Purpose & Motivation Matrix)

* **Complete Data Sovereignty & Privacy:** Replacing commercial cloud providers. My confidential data, documents, and notes remain physically on my own storage devices - without tracking, data analysis, or third-party access rights.
* **Independence from Streaming Platforms:** No dependency on subscription models, price increases, ads, geoblocking, or content disappearing due to licensing reasons.
* **Focus & Mindful Media Consumption:** Self-hosted media libraries free of recommendation algorithms, scroll spirals, and advertising interruptions.
* **Digitization & Long-Term Archiving:** Losslessly digitizing, organizing, and permanently preserving physical media (e.g., my own CDs, DVDs, textbooks).
* **Centralization of University Documents:** An organized place, protected against single-drive failure (parity), for all lecture materials, notes, and scripts - accessible from any device.
* **Financial Control & Sustainability (FinOps):** Avoiding recurring monthly cloud subscriptions in favor of a one-time, energy-efficient hardware investment.
* **Hands-On IT Lab:** Deepening practical knowledge of Linux system administration, container virtualization, storage management, and IT security well beyond theoretical coursework.

---

## 2. Hardware Used & Technical Rationale

| Component | Exact Model | Architectural Reasoning & Advantage |
| :--- | :--- | :--- |
| **CPU** | Intel Core i3-12100 | 4C/8T. UHD 730 iGPU with **Intel QuickSync** for power-efficient 4K hardware transcoding in Jellyfin; strong single-core performance & AVX2 instruction set. |
| **GPU (AI / Acceleration)** | Nvidia GeForce GTX 1070 (8 GB) | Cost-effective budget choice for local LLM inference (Ollama) and hardware acceleration for AI workloads (Faster-Whisper audio transcription) via GPU passthrough. |
| **Motherboard** | Gigabyte B760M DS3H DDR4 GEN5 | Micro-ATX with support for deep **C-states (C8/C10)** under Linux (minimal idle power draw); native 2.5 GbE LAN port for fast data transfer. |
| **RAM** | 32 GB Crucial Pro DDR4-3200 (2x16GB) | Dual-channel (1.2V JEDEC standard) for 24/7 stability; provides ample headroom for parallel Docker containers. |
| **System SSD** | 1 TB WD Blue SN580 NVMe M.2 | PCIe 4.0 HMB NVMe for maximum I/O performance for Docker containers, appdata databases, and the Unraid inbound cache. |
| **HDDs (Array)** | 2x 10 TB HPE Enterprise HDDs (3.5", CMR) | Parity-protected Unraid storage pool (**1x parity + 1x data**). CMR technology prevents performance drops; XOR parity protects against drive failure. |
| **HDDs (Array, reused)** | 1x 500 GB (from a 2012 laptop) + 1x 350 GB (from an older desktop PC) | Additional data drives in the same array, added from spare hardware. Each data drive has its own file system; the parity drive (10 TB) is at least as large as the largest data drive. Data, including university files, is spread across the data drives (High-water allocation). |
| **Optical Drive**| LG HLDS BU40N Ultra Slim UHD Burner | Slim drive connected via USB adapter; LibreDrive compatibility for lossless reading of my own media. *Note:* Reading is strictly within the bounds of applicable copyright law (§ 95a UrhG, German copyright act); no circumvention of effective copy-protection mechanisms. |
| **Boot Media** | 32 GB Samsung BAR Plus (USB 3.1) | Write-protected Unraid boot stick; sturdy metal housing for optimal heat dissipation in 24/7 operation. |
| **CPU Cooler** | Thermalright Assassin X 120 SE | Tower cooler with a quiet 120mm PWM fan; prevents thermal throttling under sustained full CPU load. |
| **Power Supply** | be quiet! System Power 11 450W (80+ Bronze) | Highly efficient power supply with native C6/C7-state support for minimal power loss under low idle load. |
| **Case** | Fractal Design Define R5 (Black) | ATX mid-tower with sound dampening, decoupled drive bays (vibration damping), and generous dust filters. |

---

## 3. Software Architecture & Media Stack

The system uses **Unraid OS** as its host operating system (stateless boot concept from RAM) and runs all applications process-isolated in **Docker containers**.

```text
+-------------------------------------------------------------------+
|                     DOCKER APPLICATION STACK                      |
| +------------+---------------+------------------+---------------+ |
| | Jellyfin   | Navidrome     | Tdarr Engine     | Ollama        | |
| | (Video)    | (Hi-Fi Music) | (Transcoding)    | (Local AI)    | |
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
|  |  Inbound Files           |   |  Data: 10 TB, 500 GB, 350 GB      |      |
|  +--------------------------+   +-----------------------------------+      |
+----------------------------------------------------------------------------+
```

### 3.1 Video Streaming & Home Theater (Jellyfin)

**Direct Play & Hardware Acceleration:** A pure, open-source media server setup without external pass-through servers. Uses the Intel UHD 730 graphics unit (QuickSync) for lag-free hardware transcoding when needed.

**Platform-Independent:** Streams uncompressed content directly to devices on the home network (e.g., Apple TV 4K) as well as to mobile clients on the go.

### 3.2 Hi-Fi Music Library (Navidrome)

**High-Performance Streaming:** A resource-efficient music server written in Go, for my own CD rips (FLAC/MP3).

**Universal Interface:** Uses the Subsonic API for seamless integration with mobile apps (iPhone/Android) in the car or on the go, without relying on third-party subscription services.

### 3.3 Automated Media Optimization (Tdarr Pipeline)

* **Resolution-Aware Transcoding Logic:** 
  * **Low-Resolution Content (SD/DVD):** Processed via **CPU (x265)** to maintain maximum visual accuracy, preventing block artifacts and quality degradation.
  * **High-Resolution Content (1080p/4K):** Offloaded to **Intel QuickSync (GPU)** for high-throughput, energy-efficient H.265 transcoding.
* **Automated Flow Pipeline:** Reads raw MKVs from `/watch_folder`, analyzes codec/bitrate/resolution, transcodes selectively, and automatically moves processed files to the final Jellyfin media library.

**Automated Node Workflow:** Drastically reduces file sizes while maintaining visual quality, saving storage space on the 10 TB HDDs and easing network bandwidth.

### 3.4 Automated E-Ink Workflow & AI Audio Processing (Syncthing & Faster-Whisper)

* **Seamless Document Sync:** Bidirectional background synchronization between the Onyx Boox Go 10.3 tablet and the Unraid server using **Syncthing**, ensuring lecture materials and handwritten notes are instantly backed up and accessible.
* **Local Audio Transcription:** Lecture recordings from the tablet are transcribed by a self-hosted **Faster-Whisper** container (GPU-accelerated via the Nvidia GTX 1070), without any cloud service.
* **Automation Approach:** The earlier n8n orchestration has been retired because its maintenance effort and resource usage were out of proportion to the task. Automations on this server are now implemented as lightweight Bash scripts (see [`scripts/zeitung/`](scripts/zeitung/)); the automatic folder watch for new audio files will be rebuilt the same way (see roadmap).

### 3.5 Local AI Weekly Newspaper (Bash & Ollama)

* **Fully Local News Digest:** Every Wednesday at 04:00, a chain of Bash scripts collects the past week's news from RSS/Atom feeds, has a local LLM (**Ollama**, `qwen3.5:9b` on the GTX 1070) write a German weekly newspaper (domestic & foreign policy with impact assessments, cybersecurity & open source, markets), and renders it as a self-contained HTML page with source links.
* **Reliability by Design:** One validated model request per section (`done_reason` check, retries), explicit context window, atomic writes, run lock and per-step logging.
* **E-Ink Delivery:** The newest issue is synced to the Onyx Boox via Syncthing (*Send Only* / *Receive Only*); older issues are removed automatically. Details in [`scripts/zeitung/`](scripts/zeitung/).

## 4. Roadmap & Planned Extensions

- [x] E-Ink Pad Automation: Setting up wireless document synchronization (Syncthing / OPDS) for the Onyx Boox writing tablet.

- [x] Local AI Transcription: Integrating a self-contained Docker container (faster-whisper) for locally processing lecture audio.

- [x] Local AI Newspaper: Weekly news digest generated entirely on my own hardware with Bash and Ollama (see [`scripts/zeitung/`](scripts/zeitung/)).

- [ ] Extended Scripting Automation: Creating custom Bash and watchdog scripts for automated backups and folder monitoring.

- [x] Network Hardening: Configuration of Zero-Trust access control lists (Tailscale ACLs) to isolate mobile devices (see [`docs/security-concept.md`](docs/security-concept.md)).

## 5. Repository Structure

The subfolders contain the specific configurations and in-depth documentation:

* **[`docs/`](docs/):** Detailed documentation on hardware architecture, network topology, and security concepts.

* **[`docker/`](docker/):** Modularly organized Docker Compose files for Jellyfin, Navidrome, Tdarr, Faster-Whisper, and administrative tools.

* **[`scripts/`](scripts/):** Custom Bash scripts and automated pipelines, including the **local AI weekly newspaper** (`scripts/zeitung/`).

---

## Author

**Miguel**

Student of Business Information Systems (HTWG Konstanz)

**Focus Areas:** IT Security Architecture, System Administration & Cloud-Free Homelabs

**Contact:** [LinkedIn](https://www.linkedin.com/in/miguel-angel-fernandez-kummnik) | [Email](mailto:fernandezkummnikm@gmail.com)
