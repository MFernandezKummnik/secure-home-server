# Self-Hosted Cloud-Free Home Server & Infrastructure

[ **English** ](README.md) | [ Deutsch ](README.de.md)

[![OS: Linux / Unraid](https://img.shields.io/badge/OS-Unraid_Linux-orange.svg)](https://unraid.net/)
[![Security: Zero Trust](https://img.shields.io/badge/Security-Zero_Trust_%7C_LUKS-emerald.svg)]()
[![Stack: Docker](https://img.shields.io/badge/Stack-Docker_%7C_Jellyfin_%7C_Tdarr-brightgreen.svg)]()

Repository documenting my self-built, fully cloud-free home server. The system serves as central infrastructure for data backup, media management, university organization, and automated background workflows following the principle of "Security by Design."

---

## 1. Why a Home Server of My Own? (Purpose & Motivation Matrix)

* **Complete Data Sovereignty & Privacy:** Replacing commercial cloud providers. My confidential data, documents, and notes remain physically on my own storage devices - without tracking, data analysis, or third-party access rights.
* **Independence from Streaming Platforms:** No dependency on subscription models, price increases, ads, geoblocking, or content disappearing due to licensing reasons.
* **Focus & Mindful Media Consumption:** Self-hosted media libraries free of recommendation algorithms, scroll spirals, and advertising interruptions.
* **Digitization & Long-Term Archiving:** Losslessly digitizing, organizing, and permanently preserving physical media (e.g., my own CDs, DVDs, textbooks).
* **Centralization of University Documents:** An organized, fail-safe place for all lecture materials, notes, and scripts - accessible from any device.
* **Financial Control & Sustainability (FinOps):** Avoiding recurring monthly cloud subscriptions in favor of a one-time, energy-efficient hardware investment.
* **Hands-On IT Lab:** Deepening practical knowledge of Linux system administration, container virtualization, storage management, and IT security well beyond theoretical coursework.

---

## 2. Hardware Used & Technical Rationale

| Component | Exact Model | Architectural Reasoning & Advantage |
| :--- | :--- | :--- |
| **CPU** | Intel Core i3-12100 | 4C/8T. UHD 730 iGPU with **Intel QuickSync** for power-efficient 4K hardware transcoding in Jellyfin; strong single-core performance & AVX2 instruction set. |
| **Motherboard** | Gigabyte B760M DS3H DDR4 GEN5 | Micro-ATX with support for deep **C-states (C8/C10)** under Linux (minimal idle power draw); native 2.5 GbE LAN port for fast data transfer. |
| **RAM** | 32 GB Crucial Pro DDR4-3200 (2x16GB) | Dual-channel (1.2V JEDEC standard) for 24/7 stability; provides ample headroom for parallel Docker containers. |
| **System SSD** | 1 TB WD Blue SN580 NVMe M.2 | PCIe 4.0 HMB NVMe for maximum I/O performance for Docker containers, appdata databases, and the Unraid inbound cache. |
| **HDDs (Array)** | 2x 10 TB HPE Enterprise HDDs (3.5", CMR) | Parity-protected Unraid storage pool (**1x parity + 1x data**). CMR technology prevents performance drops; XOR parity protects against drive failure. |
| **HDD (University)** | 1x 250 GB Seagate DB35.4 HDD | **Unassigned device** (outside the parity array) for active university data. Protects the large 10 TB drives from constant spin-ups. |
| **Optical Drive**| LG HLDS BU40N Ultra Slim UHD Burner | Internal slim drive via USB adapter; LibreDrive compatibility for lossless reading of his own media. *Note:* Reading is strictly within the bounds of applicable copyright law (§ 95a UrhG, German copyright act); no circumvention of effective copy-protection mechanisms. |
| **Boot Media** | 32 GB Samsung BAR Plus (USB 3.1) | Write-protected Unraid boot stick; sturdy metal housing for optimal heat dissipation in 24/7 operation. |
| **CPU Cooler** | Thermalright Assassin X 120 SE | Tower cooler with a quiet 120mm PWM fan; prevents thermal throttling under sustained full CPU load. |
| **Power Supply** | be quiet! System Power 11 450W (80+ Bronze) | Highly efficient power supply with native C6/C7-state support for minimal power loss under low idle load. |
| **Case** | Fractal Design Define R5 (Black) | ATX mid-tower with sound dampening, decoupled drive bays (vibration damping), and generous dust filters. |

---

## 3. Software Architecture & Media Stack

The system uses **Unraid OS** as its host operating system (stateless boot concept from RAM) and runs all applications process-isolated in **Docker containers**.

```text
+----------------------------------------------------------------------------+
|                          DOCKER APPLICATION STACK                          |
| +-----------------+-----------------+-----------------+------------------+ |
| | Jellyfin        | Navidrome       | Tdarr Engine    | Administrative   | |
| | (Video/Movie)   | (Hi-Fi Music)   | (Transcoding)   | Tools & VPN      | |
| +-----------------+-----------------+-----------------+------------------+ |
+-------------------------------------+--------------------------------------+
                                        | (Controlled I/O access)
                                        v
+----------------------------------------------------------------------------+
|                              STORAGE TIERING                               |
|  +--------------------------+   +-----------------------------------+      |
|  |  NVMe CACHE (1 TB)       |   |  PARITY ARRAY (10 TB + 10 TB)      |     |
|  |  Docker Appdata &        |-->|  Media Library & Long-Term         |     |
|  |  Inbound Files           |   |  Archive (XOR protection)          |     |
|  +--------------------------+   +-----------------------------------+      |
|  +------------------------------------------------------------------+      |
|  |  UNASSIGNED DEVICE: 250 GB HDD (Active University Data)           |     |
|  +------------------------------------------------------------------+      |
+----------------------------------------------------------------------------+
```
## 3.1 Video Streaming & Home Theater (Jellyfin)
Direct Play & Hardware Acceleration: A pure, open-source media server setup without external pass-through servers. Uses the Intel UHD 730 graphics unit (QuickSync) for lag-free hardware transcoding when needed.

Platform-Independent: Streams uncompressed content directly to devices on the home network (e.g., Apple TV 4K) as well as to mobile clients on the go.

## 3.2 Hi-Fi Music Library (Navidrome)
High-Performance Streaming: A resource-efficient music server written in Go, for his own CD rips (FLAC/MP3).

Universal Interface: Uses the Subsonic API for seamless integration with mobile apps (iPhone/Android) in the car or on the go, without relying on third-party subscription services.

## 3.3 Automated Media Optimization (Tdarr Pipeline)
Storage Efficiency via H.265/HEVC: An automated transcoding pipeline that analyzes incoming video files and converts them to the highly efficient H.265 format.

Automated Node Workflow: Drastically reduces file sizes while maintaining visual quality, saving storage space on the 10 TB HDDs and easing network bandwidth.

## 4. Roadmap & Planned Extensions
- [ ] E-Ink Pad Automation: Setting up wireless document synchronization (Syncthing / OPDS) for the Onyx Boox writing tablet.

- [ ] Local AI Transcription: Integrating a self-contained Docker container (faster-whisper) for locally processing lecture audio.

- [ ] Extended Scripting Automation: Creating custom Bash and watchdog scripts for automated backups and folder monitoring.

- [ ] Network Hardening: Comprehensive configuration of Zero-Trust access control lists (Tailscale ACLs) to isolate mobile devices.

## 5. Repository Structure
The subfolders contain the specific configurations and in-depth documentation:

* **[`docs/`](docs/):** Detailed documentation on hardware architecture, network topology, and security concepts.

* **[`docker/`](docker/):** Modularly organized Docker Compose files for Jellyfin, Navidrome, Tdarr, and administrative tools.

* **[`scripts/`](scripts/):** (In development) Custom scripts for automation, backup routines, and file management.

---

## Author

**Miguel**

Student of Business Information Systems (HTWG Konstanz)

**Focus Areas:** IT Security Architecture, System Administration & Cloud-Free Homelabs

**Contact:** - [LinkedIn](https://www.linkedin.com/in/miguel-angel-fernandez-kummnik) | - [Email](mailto:mi451fer@htwg-konstanz.de)
