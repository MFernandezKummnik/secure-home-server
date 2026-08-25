# System & Hardware Architecture

## 1. Hardware Overview & Compute Tier

The server is engineered for maximum energy efficiency, silent 24/7 operation, and high I/O throughput.

* **CPU:** Intel Core i3-12100 (4 Cores / 8 Threads, 3.30 GHz base, 4.30 GHz boost).
  * **iGPU:** Intel UHD Graphics 730 featuring **Intel QuickSync Video** for hardware-accelerated H.264/HEVC/VP9/AV1 decoding and encoding.
* **Motherboard:** Gigabyte B760M DS3H DDR4 GEN5 (Micro-ATX, Intel B760 Express Chipset).
  * **Power Efficiency:** Configured for deep **C-States (C8/C10)** under Linux to minimize idle power draw (~15-20W idle).
  * **Networking:** Integrated Realtek 2.5 GbE LAN interface.
* **Memory:** 32 GB Crucial Pro DDR4-3200 (2x 16 GB, 1.2V JEDEC standard) operating in dual-channel mode.
* **Cooling & Chassis:** Thermalright Assassin X 120 SE mounted inside a sound-dampened **Fractal Design Define R5** Midi-Tower.

---

## 2. Storage Tiering & Array Design

The system utilizes Unraid OS's hybrid storage architecture to balance parity protection, high I/O speed, and HDD spin-down energy savings.

```text
+-------------------------------------------------------------------------+
|                              UNRAID STORAGE                             |
+-------------------------------------------------------------------------+
|  CACHE TIER (NVMe)                                                      |
|  1 TB WD Blue SN580 PCIe 4.0 NVMe                                       |
|  - Docker Appdata Databases                                             |
|  - Inbound Watch Folder / Temp Transcode Storage                        |
+-------------------------------------------------------------------------+
|  PARITY ARRAY (HDD Pool with Parity Protection)                         |
|  - Parity Drive:  1x 10 TB HPE Enterprise HDD (CMR)                     |
|  - Data Drive:    1x 10 TB HPE Enterprise HDD (CMR)                     |
|  - Protected Media Libraries (Jellyfin / Navidrome)                     |
+-------------------------------------------------------------------------+
|  UNASSIGNED DEVICES (Bypassing Parity Array)                            |
|  - 1x 250 GB Seagate DB35.4 HDD (Active University Data & Scratchpad)   |
|    -> Prevents unnecessary spin-ups of the primary 10 TB HDDs           |
+-------------------------------------------------------------------------+
```
---
3. Optical Ingestion Pipeline (Multi-Drive)
The ingestion pipeline uses a dedicated three-drive physical setup to extract media without cross-contaminating optical drive workloads or causing premature wear.

LG HLDS BU40N Ultra Slim UHD Burner:

Connected via USB adapter, flashed with LibreDrive firmware.

Dedicated exclusively to 4K UHD and standard Blu-ray discs.

Origbele DVD Drive:

Dedicated exclusively to standard DVD extraction.

Legacy PC Optical Drive:

Dedicated exclusively to Audio CD extraction.
```
[ Physical Media Inserted ]
          |
          v
[ MakeMKV Docker Container ]
          | (Raw Rip Extraction)
          v
[ NVMe Cache: /watch_folder ]
          |
          v
[ Tdarr Transcoding Flow ]
   |
   +---> [ Check Resolution ]
            |
            +---> Low Resolution (SD/DVD)  -> CPU Worker (x265) -> Quality Focus
            |
            +---> High Resolution (1080p/4K) -> QuickSync GPU    -> Speed & Efficiency
          |
          v
[ Move to Final Media Pool (/mnt/user/Media) ]
