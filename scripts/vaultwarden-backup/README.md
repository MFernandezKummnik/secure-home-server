# Encrypted Vaultwarden Backup

Every night at 03:00 the server takes a consistent snapshot of the password vault, encrypts it, verifies that it can be decrypted again, stores it on the HDD array and syncs it to the laptop. The vault lives on the NVMe SSD; the copies live on different hardware.

```text
appdata/vaultwarden (NVMe SSD)
   │ 1. sqlite3 .backup        consistent snapshot while Vaultwarden keeps running
   │ 2. PRAGMA integrity_check
   │ 3. + rsa_key*, attachments/, sends/
   │ 4. tar + gpg (AES-256, separate backup passphrase)
   │ 5. test decryption → only then the file counts as a backup
   ▼
Backups/vaultwarden (HDD array, last 30)  ──Syncthing──►  laptop (Receive Only + versioning)
```

> The script and its comments are in German.

---

## Design Decisions

| Decision | Reasoning |
| :--- | :--- |
| **`sqlite3 .backup` instead of copying the file** | Vaultwarden writes continuously (WAL mode). A plain file copy during a write can be inconsistent; the SQLite backup API produces a consistent snapshot without stopping the service. |
| **Integrity check of the snapshot** | A damaged snapshot is never stored as a backup. |
| **Second layer of encryption** | Vault entries are already encrypted by the clients, but the archive also contains the server's signing key and metadata. With `gpg --symmetric` (AES-256) the file can safely leave the server. The passphrase is separate from the master password and is also kept offline. |
| **Verified before it counts** | The archive is decrypted again and must contain the database; only then is it renamed from `.tmp` to its final name. A failed run leaves no half-written file. |
| **Retention: last 30 backups** | File names start with the date, so a reverse sort lists the newest first; everything after position 30 is removed. |
| **No network, minimal mounts** | The container runs with `--network none` as `99:100`; script and passphrase file are mounted read-only. |
| **Share on the array only** | The `Backups` share has no cache pool, so backups never land on the same SSD as the vault. It is not exported via SMB. |
| **Off-server copy with versioning** | Syncthing shares the folder *Send Only* → *Receive Only* to the laptop. Sync alone is not a backup: deletions and changes would be mirrored. *Trash can* versioning on the laptop keeps every file removed on the server in `.stversions` for 180 days, and that folder is never synced back. |

Result: three copies (SSD, HDD, laptop) on different hardware, one of them on a separate device.

## Lessons Learned

* **`pipefail` and `grep -q` do not mix.** The first version verified the backup in a single pipe (`gpg | tar | grep -q`). `grep -q` stops reading at the first match; when `tar` or `gpg` write afterwards they receive `SIGPIPE` and exit with an error, without any message, so the check failed depending on timing. The verification now runs in separate steps without a pipe and reports the actual error.
* **Containers only see what is mapped.** Syncthing reported `mkdir /data3: permission denied`: the folder path existed in the Syncthing config, but the container path mapping was empty. Container paths must be mapped explicitly; as a side effect Syncthing cannot reach the vault itself.
* **Containers run in UTC by default.** Mounting `/etc/localtime` read-only makes log times and file names match the server's time zone.

## Files

| File | Purpose |
| :--- | :--- |
| `backup.sh` | Snapshot, check, encrypt, verify, rotate |
| `Dockerfile` | Small Alpine image with `sqlite`, `gnupg`, `tar` |
| `user-script.sh` | Unraid *User Scripts* entry, schedule `0 3 * * *` |

## Setup

```bash
# Share "Backups": primary storage Array, no secondary storage, SMB export off
mkdir -p /mnt/user/appdata/vw-backup /mnt/user/Backups/vaultwarden
# copy backup.sh, Dockerfile, user-script.sh to /mnt/user/appdata/vw-backup
cd /mnt/user/appdata/vw-backup && docker build -t vw-backup .

# Passphrase: typed hidden, never visible on screen, in the shell history or in a file listing
read -rs -p "Backup passphrase: " P && printf '%s' "$P" > /mnt/user/appdata/vw-backup/backup.pass && unset P; echo

chown -R 99:100 /mnt/user/appdata/vw-backup /mnt/user/Backups/vaultwarden
chmod 600 /mnt/user/appdata/vw-backup/backup.pass
chmod +x /mnt/user/appdata/vw-backup/backup.sh

bash /mnt/user/appdata/vw-backup/user-script.sh   # test run
```

**Syncthing:** map `/mnt/user/Backups/vaultwarden` into the Syncthing container, share it *Send Only* with ignore pattern `*.tmp`; on the laptop *Receive Only* with *Trash can* versioning (180 days).

## Restore

```bash
gpg -d vaultwarden_<date>.tar.gz.gpg | tar -xz      # → folder vaultwarden/
docker stop vaultwarden
# copy the contents into /mnt/user/appdata/vaultwarden (remove old db.sqlite3-wal / -shm first)
docker start vaultwarden
```
A full restore test with a separate test container (without touching the live vault) is still open; so far each nightly run verifies that its archive decrypts and contains the database.

---

## Transparency Note

The scripts in this folder were written with the help of an AI assistant (Claude by Anthropic). I worked through every part together with it, tested it on my own server, and can explain what each part does and why.
