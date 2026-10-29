# Self-Hosted Cloud-Free Home Server & Infrastructure

[ English ](README.md) | [ **Deutsch** ](README.de.md)

[![OS: Linux / Unraid](https://img.shields.io/badge/OS-Unraid_Linux-orange.svg)](https://unraid.net/)
[![Security: Zero Trust](https://img.shields.io/badge/Security-Zero_Trust-emerald.svg)]()
[![Stack: Docker](https://img.shields.io/badge/Stack-Docker_%7C_Jellyfin_%7C_Tdarr-brightgreen.svg)]()

Repository zur Dokumentation meines selbstgebauten, vollkommen cloud-freien Heimservers. Das System dient als zentrale Infrastruktur für Datenhaltung mit Ausfallschutz, Medien-Management, Hochschul-Organisation und automatisierte Hintergrund-Workflows nach dem Prinzip "Security by Design".

---

## 1. Warum ein eigener Heimserver? (Zweck & Motivationsmatrix)

* **Vollständige Datensouveränität & Datenschutz:** Ablösung kommerzieller Cloud-Anbieter. Meine vertraulichen Daten, Dokumente und Notizen verbleiben physisch auf eigenen Datenträgern - ohne Tracking, Datenanalyse oder Mitleserechte durch Dritte.
* **Unabhängigkeit von Streaming-Plattformen:** Keine Abhängigkeit von Abo-Modellen, Preiserhöhungen, Werbeeinblendungen, Geoblocking oder verschwindenden Inhalten aus Lizenzgründen.
* **Fokus & bewusster Medienkonsum:** Selbstgehostete Mediatheken frei von Empfehlungs-Algorithmen, Scroll-Spiralen und Werbeunterbrechungen.
* **Digitalisierung & Langzeitarchivierung:** Physische Medien (z. B. eigene CDs, DVDs, Fachbücher) verlustfrei digitalisieren, strukturieren und dauerhaft sichern.
* **Zentralisierung von Hochschul-Dokumenten:** Ein organisierter, gegen den Ausfall einer Platte geschützter Ort (Parity) für alle Vorlesungsunterlagen, Mitschriften und Skripte - von jedem Gerät aus erreichbar.
* **Finanzielle Kontrolle & Nachhaltigkeit (FinOps):** Vermeidung wiederkehrender monatlicher Cloud-Abonnements zugunsten einer einmaligen, energieeffizienten Hardware-Investition.
* **Praxisnahes IT-Labor:** Fundierte Vertiefung von Kenntnissen in Linux-Systemadministration, Container-Virtualisierung, Speichermanagement und IT-Sicherheit weit über das theoretische Studium hinaus.

---

## 2. Verbaute Hardware & Technische Begründung

| Komponente | Exaktes Modell | Architektonischer Grund & Vorteil |
| :--- | :--- | :--- |
| **CPU** | Intel Core i3-12100 | 4C/8T. UHD 730 iGPU mit **Intel QuickSync** für stromsparendes 4K-Hardware-Transcoding in Jellyfin; hohe Single-Core-Leistung & AVX2-Befehlssatz. |
| **GPU (KI / Beschleunigung)** | Nvidia GeForce GTX 1070 (8 GB) | Kosteneffiziente Budget-Wahl für lokale LLM-Inferenz (Ollama) und GPU-Beschleunigung von KI-Workflows (Faster-Whisper Sprach-zu-Text). |
| **Mainboard** | Gigabyte B760M DS3H DDR4 GEN5 | Micro-ATX mit Unterstützung für tiefe **C-States (C8/C10)** unter Linux (minimaler Idle-Verbrauch); nativer 2.5 GbE LAN-Port für schnelle Datenübertragung. |
| **RAM** | 32 GB Crucial Pro DDR4-3200 (2x16GB) | Dual-Channel (1.2V JEDEC-Standard) für 24/7-Stabilität; bietet ausreichend Puffer für parallele Docker-Container. |
| **System SSD** | 1 TB WD Blue SN580 NVMe M.2 | PCIe 4.0 HMB-NVMe für maximale I/O-Performance bei Docker-Containern, Appdata-Datenbanken und dem Unraid Inbound-Cache. |
| **HDDs (Array)** | 2x 10 TB HPE Enterprise HDDs (3,5", CMR) | Paritätsgeschützter Unraid-Storage-Pool (**1x Parity + 1x Data**). CMR-Technologie verhindert Leistungseinbrüche; XOR-Parität schützt vor Festplattenausfall. |
| **HDDs (Array, wiederverwendet)** | 1x 500 GB (aus einem Laptop von 2012) + 1x 250 GB (aus einem alten Receiver) | Zusätzliche Data-Platten im selben Array, aus vorhandener Hardware ergänzt. Jede Data-Platte hat ein eigenes Dateisystem; die Parity-Platte (10 TB) ist mindestens so groß wie die größte Data-Platte. Daten, auch die Uni-Dateien, verteilen sich auf die Data-Platten (High-water-Zuteilung). |
| **Opt. Laufwerk**| LG HLDS BU40N Ultra Slim UHD-Brenner | Slim-Laufwerk, per USB-Adapter angeschlossen; LibreDrive-Kompatibilität zum verlustfreien Auslesen eigener Medien. *Hinweis:* Auslesen rein im Rahmen geltender Urheberrechtsbestimmungen (§ 95a UrhG); kein Aufbrechen wirksamer Kopierschutzmechanismen. |
| **Bootmedium** | 64 GB Samsung BAR Plus (USB 3.1) | Schreibgeschützter Unraid-Boot-Stick; robustes Metallgehäuse für optimale Wärmeableitung im 24/7-Dauerbetrieb. |
| **CPU-Kühler** | Thermalright Assassin X 120 SE | Tower-Kühler mit leisem 120mm PWM-Lüfter; verhindert Thermal Throttling bei dauerhafter CPU-Volllast. |
| **Netzteil** | be quiet! System Power 11 450W (80+ Bronze) | Hocheffizientes Netzteil mit nativer C6/C7-State-Unterstützung für minimale Verlustleistung bei niedriger Idle-Last. |
| **Gehäuse** | Fractal Design Define R5 (Black) | ATX Midi-Tower mit Schalldämmung, entkoppelten Festplattenschächten (Vibrationsdämpfung) und großzügigen Staubfiltern. |

---

## 3. Software-Architektur & Medien-Stack

Das System nutzt **Unraid OS** als Host-Betriebssystem (stateless Boot-Konzept aus dem Arbeitsspeicher) und betreibt alle Anwendungen prozessisoliert in **Docker-Containern**.

```text
+-------------------------------------------------------------------+
|                     DOCKER APPLICATION STACK                      |
| +------------+---------------+------------------+---------------+ |
| | Jellyfin   | Navidrome     | Tdarr Engine     | Ollama        | |
| | (Video)    | (Hi-Fi Musik) | (Transcoding)    | (Lokale KI)   | |
| +------------+---------------+------------------+---------------+ |
| | Administrative Tools, Syncthing & Tailscale Mesh-VPN          | |
+---------------------------------------+---------------------------+
                                        | (Gesteuerter I/O-Zugriff)
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

### 3.1 Videostreams & Heimkino (Jellyfin)

**Direct Play & Hardware-Beschleunigung:** Reines, open-source Medienserver-Setup ohne externe Pass-Through-Server. Nutzt die Intel UHD 730 Grafikeinheit (QuickSync) für verzögerungsfreies Hardware-Transcoding im Bedarfsfall.

**Plattformunabhängig:** Streamt unkomprimierte Inhalte direkt an Endgeräte im Heimnetz (z. B. Apple TV 4K) sowie an mobile Clients unterwegs.

### 3.2 Hi-Fi Musikbibliothek (Navidrome)

**High-Performance Streaming:** Ressourcenschonender, in Go geschriebener Musikserver für eigene CD-Rips (FLAC/MP3).

**Universelle Schnittstelle:** Nutzt die Subsonic-API zur nahtlosen Anbindung mobiler Apps (iPhone/Android) im Auto oder unterwegs, ohne auf Drittanbieter-Abo-Dienste angewiesen zu sein.

### 3.3 Automatische Medienoptimierung (Tdarr Pipeline)

* **Auflösungsabhängige Transkodierungs-Logik:** 
  * **Geringe Auflösung (SD/DVD):** Verarbeitung über die **CPU (x265)** für maximale Bildgenauigkeit und zur Vermeidung von Qualitätsverlusten und Artefakten.
  * **Hohe Auflösung (1080p/4K):** Auslagerung an **Intel QuickSync (GPU)** für ein besonders schnelles und energieeffizientes H.265-Transcoding.
* **Automatisierte Flow-Pipeline:** Greift Rohdateien aus dem `/watch_folder` ab, prüft Codec/Bitrate/Auflösung, transkodiert selektiv und verschiebt die fertigen Medien direkt in die Jellyfin-Mediathek.

**Automatisierter Node-Workflow:** Reduziert die Dateigrößen bei gleichbleibender visueller Qualität drastisch, spart Speicherplatz auf den 10-TB-HDDs und schont die Netzwerk-Bandbreite.

### 3.4 Automatisierter E-Ink Workflow & Vorlesungs-Transkription (Syncthing, Whisper & Ollama)

* **Nahtlose Dokumenten-Synchronisation:** Bi-direktionale Hintergrund-Synchronisation zwischen dem Onyx Boox Go 10.3 Tablet und dem Unraid-Server mittels **Syncthing** über eine verschlüsselte **Tailscale-VPN**-Verbindung (ermöglicht sicheren Remote-Zugriff aus dem Campusnetz der HTWG Konstanz).
* **Lokale Audio-Transkription:** Vorlesungsaufnahmen vom Tablet werden jede Nacht von **Whisper `large-v3`** transkribiert (faster-whisper-Engine, GPU-beschleunigt auf der GTX 1070 mit `int8`), ganz ohne Cloud-Dienst.
* **Lern-Zusammenfassungen:** Ein lokales Sprachmodell (**Ollama**) erstellt aus jedem Transkript eine strukturierte Zusammenfassung; Transkript und Zusammenfassung werden automatisch im passenden Fachordner abgelegt, und die Aufnahme wird außerhalb des synchronisierten Ordners archiviert, damit sie auf dem Tablet keinen Platz mehr belegt.
* **Ansatz für Automatisierungen:** Die frühere Steuerung über n8n wurde entfernt, weil Wartungsaufwand und Ressourcenverbrauch in keinem Verhältnis zur Aufgabe standen. Automatisierungen laufen auf diesem Server inzwischen als schlanke Bash-Skripte; die Transkriptions-Pipeline läuft als nächtlicher Batch-Job (siehe [`scripts/transkript/`](scripts/transkript/)).

### 3.5 Lokale KI-Wochenzeitung (Bash & Ollama)

* **Komplett lokaler Nachrichtenüberblick:** Jeden Mittwoch um 04:00 Uhr sammelt eine Kette aus Bash-Skripten die Meldungen der vergangenen Woche aus RSS-/Atom-Feeds, lässt ein lokales Sprachmodell (**Ollama**, `qwen3.5:9b` auf der GTX 1070) daraus eine deutsche Wochenzeitung schreiben (Innen- & Außenpolitik mit Einordnung der Auswirkungen, Cybersecurity & Open Source, Märkte) und baut daraus eine eigenständige HTML-Seite mit Quellenlinks.
* **Zuverlässigkeit als Grundprinzip:** Eine geprüfte Modellanfrage pro Rubrik (Prüfung von `done_reason`, Wiederholungen), fest gesetztes Kontextfenster, atomares Schreiben, Sperre gegen Doppelstarts und Protokollierung pro Schritt.
* **Lesen auf dem E-Ink-Tablet:** Die neueste Ausgabe wird per Syncthing auf den Onyx Boox übertragen (*Nur senden* / *Nur empfangen*), ältere Ausgaben werden automatisch entfernt. Details in [`scripts/zeitung/`](scripts/zeitung/).

### 3.6 Eigener Kalender- & Chat-Bot (Radicale, Matrix & Ollama)

* **Eigener Kalender-Server:** **Radicale** (CalDAV) ersetzt Cloud-Kalender. Die Kalender-App des Smartphones synchronisiert direkt damit; der Stundenplan des Semesters wird als wiederkehrende Termine aus einer generierten `.ics`-Datei importiert.
* **Privater Chat-Server:** Ein **continuwuity**-Matrix-Homeserver ohne Federation, genutzt mit der App Element X.
* **Kalender-Bot:** Nachrichten wie *„nächste Woche Dienstag Abgabe ALDA“* zerlegt ein lokales Sprachmodell in feste Felder, das Datum berechnet der Code deterministisch, und nach ausdrücklicher Bestätigung wird der Termin per CalDAV eingetragen. Der Bot kann Termine außerdem anzeigen und löschen. Details in [`scripts/kalenderbot/`](scripts/kalenderbot/).
* **Keine Angriffsfläche nach außen:** Beide Dienste lauschen nur auf `127.0.0.1` und sind ausschließlich per HTTPS über `tailscale serve` erreichbar, mit Tag-basierten ACLs pro Gerät (siehe [`docs/security-concept.md`](docs/security-concept.md)).

### 3.7 Netzwerkweiter DNS-Filter (Pi-hole)

* **Pi-hole** beantwortet über die DHCP-Einstellungen des Routers die DNS-Anfragen im Heimnetz und leitet an **Quad9** weiter (DNSSEC, Schadsoftware-Filter). Die Verwaltungsoberfläche ist nur innerhalb des Tailnets erreichbar.
* **Ehrliches Ergebnis:** Werbebanner auf Streaming-Geräten entfernt es nicht, im Browser bringt es nichts zusätzlich (dort blockt bereits Brave), und ein Teil der Anfragen umgeht es über IPv6. Es entfernt aber **Werbung in Apps auf dem Smartphone**, solange es im WLAN zu Hause ist, und bleibt dafür im Einsatz, außerdem um Tracking von Apps und IoT-Geräten zu blocken und sichtbar zu machen, mit wem welches Gerät kommuniziert. Details und Erkenntnisse in [`docker/pihole/`](docker/pihole/).

### 3.8 Passwort-Manager & verschlüsselte Backups (Vaultwarden)

* **Eigener Tresor:** **Vaultwarden** (Bitwarden-kompatibel) ersetzt den Passwortspeicher des Browsers und wird mit den offiziellen Bitwarden-Apps auf Smartphone, Laptop und PC genutzt. Zero-Knowledge: Einträge werden auf dem Gerät verschlüsselt, der Server speichert nur Chiffretext. Nur innerhalb des Tailnets per HTTPS erreichbar; Registrierung und Admin-Bereich sind deaktiviert. Details in [`docker/vaultwarden/`](docker/vaultwarden/).
* **Geprüfte nächtliche Backups:** Ein konsistenter SQLite-Schnappschuss wird verschlüsselt (AES-256, eigenes Backup-Passwort), testweise entschlüsselt, auf dem HDD-Array abgelegt und auf den Laptop synchronisiert, wo eine Versionierung gelöschte Backups 180 Tage aufbewahrt. Details und Erkenntnisse in [`scripts/vaultwarden-backup/`](scripts/vaultwarden-backup/).

### 3.9 Offline-Backups (restic)

* **Zwei Stufen:** Jede Nacht hält das Plugin *Appdata Backup* jeden Container kurz an und archiviert seine Daten zusammen mit dem Unraid-Boot-Stick, damit Datenbanken konsistent gesichert werden. Einmal pro Woche holt ein PowerShell-Skript auf dem PC die Uni-Daten, die Musik und diese Archive mit **restic** auf eine externe HDD, die den Rest der Zeit abgesteckt ist.
* **Minimale Rechte:** Der PC liest über ein eigenes Unraid-Konto mit reinen Leserechten auf genau fünf Freigaben; die Backup-Freigabe ist für alle Benutzer schreibgeschützt, und `appdata` wird nicht mehr per SMB freigegeben.
* **Verschlüsselt, dedupliziert, geprüft:** AES-256-verschlüsseltes Repository, 8 Wochen- und 12 Monatsstände, eine Stichprobe von 5 % der Daten bei jedem Lauf und ein Wiederherstellungstest mit übereinstimmendem SHA-256-Hash. Der Test hat einen echten Fehler aufgedeckt (UNC-Pfade lassen sich unter Windows nicht wiederherstellen); Ursache und Lösung stehen in [`scripts/restic-backup/`](scripts/restic-backup/).

## 4. Roadmap & Geplante Erweiterungen

- [x] E-Ink-Pad Automatisierung: Einrichten der drahtlosen Dokumenten-Synchronisation (Syncthing / OPDS) für das Onyx Boox Schreibpad.

- [x] Lokale KI-Transkription: Nächtliche Pipeline mit Whisper (GPU) und Ollama, die Vorlesungsaufnahmen transkribiert, zusammenfasst, einsortiert und archiviert (siehe [`scripts/transkript/`](scripts/transkript/)).

- [x] Lokale KI-Zeitung: Wöchentlicher Nachrichtenüberblick, komplett auf eigener Hardware mit Bash und Ollama erzeugt (siehe [`scripts/zeitung/`](scripts/zeitung/)).

- [x] Eigener Kalender & Chat: Radicale, ein privater Matrix-Homeserver und ein Kalender-Bot mit lokaler KI (siehe [`scripts/kalenderbot/`](scripts/kalenderbot/)).

- [x] DNS-Filter: Pi-hole zum Blocken von Tracking und für Einblick in den Geräteverkehr (IPv6-Umgehung noch offen, siehe [`docker/pihole/`](docker/pihole/)).

- [x] Selbst gehosteter Passwort-Manager: Vaultwarden, nur innerhalb des Tailnets erreichbar (siehe [`docker/vaultwarden/`](docker/vaultwarden/)).

- [x] Verschlüsselte Backups für den Passwort-Manager: Nächtliche, geprüfte Backups auf das HDD-Array und den Laptop (siehe [`scripts/vaultwarden-backup/`](scripts/vaultwarden-backup/)).

- [x] Backups für die übrigen Daten: Nächtliche, konsistente Container-Archive auf dem Server und ein wöchentliches, verschlüsseltes Offline-Backup mit restic, bestätigt durch einen Wiederherstellungstest (siehe [`scripts/restic-backup/`](scripts/restic-backup/)).

- [x] Netzwerk-Härtung: Konfiguration von Zero-Trust Access Control Lists (Tailscale ACLs) zur Isolation mobiler Endgeräte (siehe [`docs/security-concept.md`](docs/security-concept.md)).

## 5. Repository-Struktur

In den Unterordnern befinden sich die spezifischen Konfigurationen und tiefgehende Dokumentationen:

* **[`docs/`](docs/):** Detaillierte Dokumentation zu Hardware-Architektur, Netzwerktopologie und Sicherheitskonzepten.

* **[`docker/`](docker/):** Modular gegliederte Docker-Compose-Dateien für Jellyfin, Navidrome, Tdarr, Whisper, Radicale, continuwuity (Matrix), Pi-hole, Vaultwarden und Admin-Tools.

* **[`scripts/`](scripts/):** Eigene Bash-Skripte und automatisierte Pipelines, inklusive der **lokalen KI-Wochenzeitung** (`scripts/zeitung/`) des **Kalender-Bots** (`scripts/kalenderbot/`), der **Vorlesungs-Transkription** (`scripts/transkript/`), des **Vaultwarden-Backups** (`scripts/vaultwarden-backup/`) und des **Offline-Backups mit restic** (`scripts/restic-backup/`).

---

## Autor

**Miguel**

Student der Wirtschaftsinformatik (HTWG Konstanz)

**Fachlicher Schwerpunkt:** IT-Sicherheitsarchitekturen, Systemadministration & Cloud-Free Homelabs

**Kontakt:** [LinkedIn](https://www.linkedin.com/in/miguel-angel-fernandez-kummnik) | [E-Mail](mailto:fernandezkummnikm@gmail.com)
