# Password Manager (Vaultwarden)

Self-hosted, Bitwarden-compatible password manager. It replaces the passwords previously stored in the browser and is used with the official Bitwarden apps on the smartphone, the laptop and the desktop PC. The vault is only reachable inside the tailnet.

```text
Bitwarden app (iPhone) / browser extension (laptop, PC)
   │  encrypts and decrypts locally with the master password
   │  HTTPS, inside the tailnet only
   ▼
tailscale serve :8444  ──►  127.0.0.1:8085  ──►  Vaultwarden (stores encrypted data only)
                                                   │ nightly 03:00
                                                   ▼
                              encrypted backup → array HDD → laptop (Syncthing)
```

---

## Design Decisions

| Decision | Reasoning |
| :--- | :--- |
| **Vaultwarden instead of the official Bitwarden server** | A single lightweight container with SQLite instead of a multi-container stack with MSSQL; fully compatible with the official clients. |
| **Zero-knowledge storage** | Clients encrypt every entry locally with a key derived from the master password. The server only ever stores ciphertext and never sees the master password, not even during an import. |
| **Localhost binding + `tailscale serve`** | Not reachable from the home LAN or the internet. HTTPS is mandatory anyway: the web vault uses the browser's Web Crypto API, which only works in a secure context. |
| **Signups closed** | Registration was enabled only to create the owner account and then disabled (`SIGNUPS_ALLOWED=false`), verified by trying to register a second account. |
| **Admin panel disabled** | No `ADMIN_TOKEN` is set, so `/admin` does not exist. All settings are code in the compose file; one less login to attack. |
| **Device access via ACL** | The smartphone (`tag:mobile`) is granted `tcp:8444` only; the owner's untagged laptop and PC reach it like the other services. See [`docs/tailscale-acl.example.hujson`](../../docs/tailscale-acl.example.hujson). |
| **Offline copy on clients** | The apps cache the encrypted vault, so passwords can still be read when the server is briefly unreachable. This is *not* a backup – see below. |

## Client Configuration

* **Server URL:** before logging in, switch the client from *bitwarden.com* to *self-hosted* and enter `https://<server>.<tailnet>.ts.net:8444`.
* **Browser extension:** unlock with PIN, master password required after a browser restart, vault locks after 15 minutes. *Autofill on page load* stays **off**, so a manipulated page cannot have hidden fields filled without a click. The browser's built-in password manager is disabled to avoid duplicate, outdated entries.
* **Smartphone:** Face ID unlock; Bitwarden set as the system AutoFill provider.

## Migration

Passwords were exported from the browser as CSV, imported through the web vault (encrypted in the browser before upload) and the plaintext CSV was deleted right after verifying the import. Afterwards, the vault's *reused* and *exposed passwords* reports (the latter uses the k-anonymity range API of Have I Been Pwned, so neither the password nor its full hash leaves the device) were used to prioritize which passwords to replace first.

## Backup

Nightly, verified and encrypted backups to the array and an off-server device: [`scripts/vaultwarden-backup/`](../../scripts/vaultwarden-backup/).

## Setup

```bash
mkdir -p /mnt/user/appdata/vaultwarden && chown 99:100 /mnt/user/appdata/vaultwarden
# 1. Start once with SIGNUPS_ALLOWED=true and create the account in the web vault
# 2. Recreate the container with SIGNUPS_ALLOWED=false (data stays in /data)
docker compose up -d
tailscale serve --bg --https=8444 http://127.0.0.1:8085
```

Check that the running container really uses the intended settings:
```bash
docker inspect vaultwarden --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'SIGNUPS|DOMAIN'
```
