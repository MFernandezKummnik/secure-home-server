# Self-Hosted Cloud-Free Home Server & Infrastructure

[ English ](README.md) | [ **Deutsch** ](README.de.md)

[![OS: Linux / Unraid](https://img.shields.io/badge/OS-Unraid_Linux-orange.svg)](https://unraid.net/)
[![Security: Zero Trust](https://img.shields.io/badge/Security-Zero_Trust_%7C_LUKS-emerald.svg)]()
[![Stack: Docker](https://img.shields.io/badge/Stack-Docker_%7C_Jellyfin_%7C_Tdarr-brightgreen.svg)]()

Repository zur Dokumentation meines selbstgebauten, vollkommen cloud-freien Heimservers. Das System dient als zentrale Infrastruktur für Datensicherung, Medien-Management, Hochschul-Organisation und automatisierte Hintergrund-Workflows nach dem Prinzip "Security by Design".

---

## 1. Warum ein eigener Heimserver? (Zweck & Motivationsmatrix)

* **Vollständige Datensouveränität & Datenschutz:** Ablösung kommerzieller Cloud-Anbieter. Seine vertraulichen Daten, Dokumente und Notizen verbleiben physisch auf eigenen Datenträgern - ohne Tracking, Datenanalyse oder Mitleserechte durch Dritte.
* **Unabhängigkeit von Streaming-Plattformen:** Keine Abhängigkeit von Abo-Modellen, Preiserhöhungen, Werbeeinblendungen, Geoblocking oder verschwindenden Inhalten aus Lizenzgründen.
* **Fokus & bewusster Medienkonsum:** Selbstgehostete Mediatheken frei von Empfehlungs-Algorithmen, Scroll-Spiralen und Werbeunterbrechungen.
* **Digitalisierung & Langzeitarchivierung:** Physische Medien (z. B. eigene CDs, DVDs, Fachbücher) verlustfrei digitalisieren, strukturieren und dauerhaft sichern.
* **Zentralisierung von Hochschul-Dokumenten:** Ein organisierter, ausfallsicherer Ort für alle Vorlesungsunterlagen, Mitschriften und Skripte - von jedem Gerät aus erreichbar.
* **Finanzielle Kontrolle & Nachhaltigkeit (FinOps):** Vermeidung wiederkehrender monatlicher Cloud-Abonnements zugunsten einer einmaligen, energieeffizienten Hardware-Investition.
* **Praxisnahes IT-Labor:** Fundierte Vertiefung von Kenntnissen in Linux-Systemadministration, Container-Virtualisierung, Speichermanagement und IT-Sicherheit weit über das theoretische Studium hinaus.

---

## 2. Verbaute Hardware & Technische Begründung

| Komponente | Exaktes Modell | Architektonischer Grund & Vorteil |
| :--- | :--- | :--- |
| **CPU** | Intel Core i3-12100 | 4C/8T. UHD 730 iGPU mit **Intel QuickSync** für stromsparendes 4K-Hardware-Transcoding in Jellyfin; hohe Single-Core-Leistung & AVX2-Befehlssatz. |
| **Mainboard** | Gigabyte B760M DS3H DDR4 GEN5 | Micro-ATX mit Unterstützung für tiefe **C-States (C8/C10)** unter Linux (minimaler Idle-Verbrauch); nativer 2.5 GbE LAN-Port für schnelle Datenübertragung. |
| **RAM** | 32 GB Crucial Pro DDR4-3200 (2x16GB) | Dual-Channel (1.2V JEDEC-Standard) für 24/7-Stabilität; bietet ausreichend Puffer für parallele Docker-Container. |
| **System SSD** | 1 TB WD Blue SN580 NVMe M.2 | PCIe 4.0 HMB-NVMe für maximale I/O-Performance bei Docker-Containern, Appdata-Datenbanken und dem Unraid Inbound-Cache. |
| **HDDs (Array)** | 2x 10 TB HPE Enterprise HDDs (3,5", CMR) | Paritätsgeschützter Unraid-Storage-Pool (**1x Parity + 1x Data**). CMR-Technologie verhindert Leistungseinbrüche; XOR-Parität schützt vor Festplattenausfall. |
| **HDD (Uni)** | 1x 250 GB Seagate DB35.4 HDD | **Unassigned Device** (außerhalb des Parity-Arrays) für aktive Hochschul-Daten. Schützt die großen 10-TB-Festplatten vor ständigen Spin-ups. |
| **Opt. Laufwerk**| LG HLDS BU40N Ultra Slim UHD-Brenner | Internes Slim-Laufwerk via USB-Adapter; LibreDrive-Kompatibilität zum verlustfreien Auslesen eigener Medien. *Hinweis:* Auslösung rein im Rahmen geltender Urheberrechtsbestimmungen (§ 95a UrhG); kein Aufbrechen wirksamer Kopierschutzmechanismen. |
| **Bootmedium** | 32 GB Samsung BAR Plus (USB 3.1) | Schreibgeschützter Unraid-Boot-Stick; robustes Metallgehäuse für optimale Wärmeableitung im 24/7-Dauerbetrieb. |
| **CPU-Kühler** | Thermalright Assassin X 120 SE | Tower-Kühler mit leisem 120mm PWM-Lüfter; verhindert Thermal Throttling bei dauerhafter CPU-Volllast. |
| **Netzteil** | be quiet! System Power 11 450W (80+ Bronze) | Hocheffizientes Netzteil mit Nativ C6/C7-State-Unterstützung für minimale Verlustleistung bei niedriger Idle-Last. |
| **Gehäuse** | Fractal Design Define R5 (Black) | ATX Midi-Tower mit Schalldämmung, entkoppelten Festplattenschächten (Vibrationsdämpfung) und großzügigen Staubfiltern. |

---

## 3. Software-Architektur & Medien-Stack

Das System nutzt **Unraid OS** als Host-Betriebssystem (stateless Boot-Konzept aus dem Arbeitsspeicher) und betreibt alle Anwendungen prozessisoliert in **Docker-Containern**.

```text
+----------------------------------------------------------------------------+
|                          DOCKER APPLICATION STACK                          |
| +-----------------+-----------------+-----------------+------------------+ |
| | Jellyfin        | Navidrome       | Tdarr Engine    | Administrative   | |
| | (Video/Movie)   | (Hi-Fi Music)   | (Transcoding)   | Tools & VPN      | |
| +-----------------+-----------------+-----------------+------------------+ |
+-------------------------------------+--------------------------------------+
                                        | (Gesteuerter I/O-Zugriff)
                                        v
+----------------------------------------------------------------------------+
|                              STORAGE TIERING                               |
|  +--------------------------+   +-----------------------------------+      |
|  |  NVMe CACHE (1 TB)       |   |  PARITY ARRAY (10 TB + 10 TB)      |     |
|  |  Docker Appdata &        |-->|  Mediathek & Langzeit-             |     |
|  |  Inbound-Dateien         |   |  Archiv (XOR-Schutz)               |     |
|  +--------------------------+   +-----------------------------------+      |
|  +------------------------------------------------------------------+      |
|  |  UNASSIGNED DEVICE: 250 GB HDD (Aktive Uni-Daten)                 |     |
|  +------------------------------------------------------------------+      |
+----------------------------------------------------------------------------+
```
## 3.1 Videostreams & Heimkino (Jellyfin)
Direct Play & Hardware-Beschleunigung: Reines, open-source Medienserver-Setup ohne externe Pass-Through-Server. Nutzt die Intel UHD 730 Grafikeinheit (QuickSync) für verzögerungsfreies Hardware-Transcoding im Bedarfsfall.

Plattformunabhängig: Streamt unkomprimierte Inhalte direkt an Endgeräte im Heimnetz (z. B. Apple TV 4K) sowie an mobile Clients unterwegs.

## 3.2 Hi-Fi Musikbibliothek (Navidrome)
High-Performance Streaming: Ressourcenschonender, in Go geschriebener Musikserver für eigene CD-Rips (FLAC/MP3).

Universelle Schnittstelle: Nutzt die Subsonic-API zur nahtlosen Anbindung mobiler Apps (iPhone/Android) im Auto oder unterwegs, ohne auf Drittanbieter-Abo-Dienste angewiesen zu sein.

## 3.3 Automatische Medienoptimierung (Tdarr Pipeline)
Speichereffizienz via H.265/HEVC: Automatisierte Transkodierungs-Pipeline, die eingehende Videodateien analysiert und in das hocheffiziente H.265-Format konvertiert.

Automatisierter Node-Workflow: Reduziert die Dateigrößen bei gleichbleibender visueller Qualität drastisch, spart Speicherplatz auf den 10-TB-HDDs und schont die Netzwerk-Bandbreite.

## 4. Roadmap & Geplante Erweiterungen
- [ ] E-Ink-Pad Automatisierung: Einrichten der drahtlosen Dokumenten-Synchronisation (Syncthing / OPDS) für das Onyx Boox Schreibpad.

- [ ] Lokale KI-Transkription: Integration eines autarken Docker-Containers (faster-whisper) zur lokalen Aufbereitung von Vorlesungs-Audios.

- [ ] Erweiterte Skript-Automatisierung: Erstellung eigener Bash- und Watchdog-Skripte für automatisierte Backups und Ordner-Überwachungen.

- [ ] Netzwerk-Härtung: Umfassende Konfiguration von Zero-Trust Access Control Lists (Tailscale ACLs) zur Isolation mobiler Endgeräte.

## 5. Repository-Struktur
In den Unterordnern befinden sich die spezifischen Konfigurationen und tiefgehende Dokumentationen:

* **[`docs/`](docs/):** Detaillierte Dokumentation zu Hardware-Architektur, Netzwerktopologie und Sicherheitskonzepten.

* **[`docker/`](docker/):** Modular gegliederte Docker-Compose-Dateien für Jellyfin, Navidrome, Tdarr und Administrative Tools.

* **[`scripts/`](scripts/):** (In Entwicklung) Eigene Skripte für Automatisierung, Backup-Routinen und File-Management.

---

## Autor

**Miguel**

Student der Wirtschaftsinformatik (HTWG Konstanz)

**Fachlicher Schwerpunkt:** IT-Sicherheitsarchitekturen, Systemadministration & Cloud-Free Homelabs

**Kontakt:** - [LinkedIn](https://www.linkedin.com/in/miguel-angel-fernandez-kummnik) | - [E-Mail](mailto:mi451fer@htwg-konstanz.de)
