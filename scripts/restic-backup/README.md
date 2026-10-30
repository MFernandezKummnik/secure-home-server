# Offline Backup with restic (Server → External Drive)

Parity is not a backup and a sync is not a backup. This setup adds the missing piece: a versioned, encrypted copy of everything that cannot be replaced, on a drive that is **disconnected most of the time**. Ransomware, a broken container or a wrong `rm` on the server cannot reach a drive that is not plugged in.

```text
SERVER (Unraid)                                   PC (Windows)                      EXTERNAL DRIVE
──────────────                                    ────────────                      ──────────────
appdata + boot stick
   │ "Appdata Backup" plugin, daily 03:00:
   │ stop container → tar → verify → start
   ▼
Backups share ──┐                                 backup.ps1 (weekly, by hand)
Semester1/2   ──┤   SMB, user "backup",           maps shares as Q: … U:
Vorlesungs-   ──┼── read-only ──────────────────► restic backup  ───── USB ──────► 335 GB HDD "BACKUP"
 archiv         │                                 restic forget --prune             restic repository
musikRey      ──┘                                 restic check (5 % sample)         (AES-256, deduplicated)
```

> The script and its comments are in German.

---

## What Is Backed Up

| Data | Size | Backed up | Reasoning |
| :--- | ---: | :---: | :--- |
| University data (Semester1, Semester2, lecture archive) | ~3 GB | ✅ | Irreplaceable |
| Own music (`musikRey`) | ~5 GB | ✅ | Small, partly irreplaceable |
| Container data (appdata archives) and Unraid boot stick | ~3 GB | ✅ | Configuration, databases, chats, watch status |
| Vaultwarden backups | < 1 MB | ✅ | Third copy, already encrypted |
| Media library | > 2 TB | ❌ | Can be re-acquired; too large for the drive |
| Steam backups, `docker.img`, AI models (Ollama, Whisper) | ~250 GB | ❌ | Re-downloadable or regenerated |

## Design Decisions

| Decision | Reasoning |
| :--- | :--- |
| **Two stages: server archives, PC copies** | Several containers write to databases (Vaultwarden, Jellyfin, Radicale, open-webui). Copying a live database can capture it mid-write. Only the server can stop a container, so the *Appdata Backup* plugin creates consistent archives first; the PC only copies finished files. |
| **Pull instead of push, read-only account** | The PC fetches the data with a dedicated Unraid user `backup` that has **read-only** access to exactly five shares and **no access** to everything else. Even malware on the PC cannot delete or encrypt anything on the server through it. Tested: listing works, writing returns *Access denied*, other shares return *Access denied*. |
| **Backups share read-only for everyone** | The share is exported (hidden), but my own SMB user also has read-only access. Only the server itself writes backups, so ransomware on a client cannot encrypt them. |
| **`appdata` not exported via SMB** | It held the raw data of every container, including the password vault, and nothing needed SMB access to it. Configs are edited via SSH / the Unraid terminal. |
| **restic** | Encrypted (AES-256), deduplicated (only changed blocks are stored), snapshots that can be browsed and restored individually, built-in integrity check, single binary. |
| **Only the newest appdata archive** | The server keeps 7 daily archives; restic builds the weekly history itself. |
| **No compression in the plugin** | restic deduplicates by content blocks. A gzip archive looks completely different after a small change, so nothing could be reused; an uncompressed tar can. restic compresses on its own. |
| **Retention: 8 weekly + 12 monthly snapshots** | `forget --group-by host` evaluates all snapshots of the PC together (see lessons learned). |
| **Integrity check every run** | `check --read-data-subset=5%` reads a random 5 % of the stored data, so over time the whole drive is read and a failing disk shows up early. |
| **Passwords never in plain text** | SMB credentials are stored in the Windows Credential Manager (`cmdkey`); the restic password is encrypted with Windows DPAPI (`Export-Clixml`) and only usable by my Windows account on this PC. The password is also stored in the password manager and on paper, because the password manager itself is part of the backup. |
| **Disk found by name, not drive letter** | `Get-Volume -FileSystemLabel BACKUP`; drive letters change with whatever else is plugged in. |
| **Parent snapshot by host and tag** | `backup --group-by host,tags`: restic compares each file with the previous week's snapshot and skips unchanged ones by size and modification time instead of reading them again over the network. |
| **Automatic eject at the end** | The script ejects the drive like *Safely Remove Hardware* (via `CM_Request_Device_Eject` in `cfgmgr32.dll`, which needs no admin rights), also after a failed run. If Windows refuses, the run still counts as successful and a warning names the reason. |
| **restic binary next to the script** | The script does not depend on how a package manager registers programs in `PATH`. |
| **Drive repurposed from old hardware** | A reused HDD from an old desktop PC (~360 GB), wiped (`diskpart clean`, GPT) and formatted with a **full** format so every sector is written and checked once before trusting it with backups. |

Result, together with the Unraid parity and the Vaultwarden laptop copy: for the irreplaceable data there are **three copies on different hardware, one of them offline** (3-2-1 rule, without a cloud).

## Lessons Learned

* **The restore test found a real bug.** The first version backed up UNC paths (`\\REYDESERVER\Semester2`) directly. The backup and `restic check` reported no errors, but restore failed with `invalid child node name \\REYDESERVER\Semester2`: restic on Windows stores the whole UNC root as a *single folder name containing backslashes*, which Windows cannot create. The script now maps the shares as drive letters (`Q:` … `U:`, `net use /persistent:no`) for the duration of the run; restic stores them as plain folders (`/Q`, `/R`, …). **A backup is only proven by a restore.**
* **Restored files carry the original ACLs.** The files came back with the server's permissions (read-only for my account), so restic could not even set their timestamps, and they could not be deleted. After a restore, `icacls <target> /reset /T` replaces them with normal inherited permissions.
* **Windows allows one SMB user per server name.** I already use the server's IP for my own account; the backup account therefore uses the host name. Windows treats them as two servers, which avoids error 1219.
* **Path changes break retention and change detection.** restic groups snapshots by their paths, both for `forget` and for choosing the parent snapshot during `backup`. The appdata folder is named differently every day (`ab_<date>_<time>`), so the path list never repeats: without `--group-by host` no snapshot would ever be deleted, and without `--group-by host,tags` on `backup` every run reported `no parent snapshot found` and re-read every file. Deduplication still kept the repository small, so this only showed up as slow runs – noticed on the second weekly run.
* **Ejecting without admin rights.** `Set-Disk -IsOffline` needs an elevated shell, which would break the per-user credentials (`cmdkey`) and the DPAPI-encrypted password. The Configuration Manager API that Explorer uses works for a normal user; the script ejects the USB-SATA adapter (the disk's parent device) first and falls back to the disk itself.
* **The backup audit found unrelated problems.** Measuring what to back up revealed 140 GB of duplicate uploads in open-webui (a broken sync job had re-uploaded the same lecture files for two weeks) and three mounts that still gave open-webui read-write access to my university shares. Both were cleaned up before the first backup.

## Files

| File | Purpose |
| :--- | :--- |
| `backup.ps1` | Map shares, back up, apply retention, check a sample, unmap shares, eject the drive, log |
| `Backup starten.cmd` | Double-click launcher (`-ExecutionPolicy Bypass` for this one call only) |
| `.gitignore` | Keeps the encrypted password file, the restic binary and logs out of git |

## Setup

**Unraid**
1. *Appdata Backup* plugin: destination `/mnt/user/Backups/appdata`, daily at 03:00, keep 7, back up the flash drive, compression off. Skip containers that only hold re-downloadable models (Ollama, Whisper); exclude `cache` / `vector_db` folders where present.
2. Create user `backup` (no shell or web UI login on Unraid). Give it *Read-only* on `Semester1`, `Semester2`, `Vorlesungsarchiv`, `musikRey`, `Backups` and *No Access* on all other shares.
3. Share `Backups`: SMB export *Yes (hidden)*, security *Private*, read-only for every user.

**Windows PC** (folder `C:\Backup`)
```powershell
winget install restic.restic          # then copy restic*.exe from %LOCALAPPDATA%\Microsoft\WinGet\Packages to C:\Backup\restic.exe
cmdkey /add:REYDESERVER /user:backup /pass                                              # SMB credentials, prompted
Read-Host "restic-Passwort" -AsSecureString | Export-Clixml C:\Backup\restic-passwort.xml # DPAPI-encrypted

# external drive: NTFS, volume label "BACKUP", fixed drive letter
$env:RESTIC_REPOSITORY = "G:\restic-repo"
C:\Backup\restic.exe init
```
Then run `Backup starten.cmd` once a week; when it reports that the drive was ejected, switch it off and unplug it.

## Restore

```powershell
$env:RESTIC_REPOSITORY = "G:\restic-repo"
C:\Backup\restic.exe snapshots                                   # list snapshots
C:\Backup\restic.exe ls latest | Select-String "<file name>"     # find the path inside the snapshot
C:\Backup\restic.exe restore latest --target C:\RestoreTest --include "/R/<path>"
icacls C:\RestoreTest /reset /T                                  # normal permissions for the restored files
```
Shares appear in the snapshot as `/Q` (Semester1), `/R` (Semester2), `/S` (lecture archive), `/T` (music), `/U` (Backups).

**Restore test (29.10.2026):** a PDF from `Semester2` was restored from the snapshot, entering the password manually from the password manager; its SHA-256 hash matched the original on the server.

---

## Transparency Note

The scripts in this folder were written with the help of an AI assistant (Claude by Anthropic). I worked through every part together with it, tested it on my own server and PC (including a restore test), and can explain what each part does and why.
