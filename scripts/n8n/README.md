# Onyx Boox Lecture Transcription & Sync Workflow

Automated pipeline designed to sync handwritten notes and record audio files from the **Onyx Boox Go 10.3** tablet to the Unraid home server, transcribe lecture audio locally using **Faster-Whisper**, and attach the output transcriptions to the synced lecture folder.

---

## Architecture & Data Flow

```text
[ Onyx Boox Go 10.3 ]
          │
          │ (Tailscale Encrypted Mesh-VPN + Syncthing)
          ▼
[ Unraid Cache Drive: /mnt/user/documents/boox_sync ]
          │
          ├── Audio File Dropped (.m4a / .mp3 / .wav)
          │
          ▼
[ n8n Automation Engine ]
          │
          ├── 1. Trigger: Folder Watch / Webhook
          ├── 2. POST Audio Request to Faster-Whisper Server
          │
          ▼
[ Faster-Whisper Container (Nvidia GTX 1070 GPU) ]
          │
          ├── Generates Speech-to-Text Transcription (.txt / .md)
          │
          ▼
[ n8n Automation Engine ]
          │
          └── 3. Saves Transcribed Text to synced lecture folder
```
---

## Workflow Steps

1. **Ingestion & Sync:**
   - Notes and recorded audio from lectures on the Onyx Boox tablet are synced continuously in the background via **Syncthing** over a secure **Tailscale VPN** connection to `/mnt/user/documents/boox_sync/` (enabling seamless remote access from campus networks like HTWG Konstanz).
2. **Detection & Processing (n8n):**
   - An n8n workflow monitors the inbound target folder for new audio files.
   - Upon detection, the file is loaded into the workflow pipeline and sent via REST API (`POST /v1/audio/transcriptions`) to the self-hosted **Faster-Whisper** container.

3. **Inference & Execution:**
   - Faster-Whisper leverages GPU acceleration (**Nvidia GTX 1070**) to process lecture audio locally without third-party cloud tools or API fees.

4. **Storage & Output:**
   - The resulting text/markdown file containing the full transcription is automatically written back into the respective lecture directory on the server, triggering Syncthing to make it available on the Boox tablet.

---

## How to Import

1. Open your self-hosted **n8n** web interface.
2. Go to **Workflows** -> **Import from File**.
3. Select `boox_lecture_transcription.json` from this directory.
4. Update the path variables and host IP to match your Unraid environment.
