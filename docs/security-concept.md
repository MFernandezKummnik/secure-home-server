# Security Concept & Zero-Trust Architecture

This document outlines the security controls, network isolation strategies, and privacy principles implemented across the home server infrastructure. The design strictly follows the **Security-by-Design** and **Zero-Trust** paradigms.

---

## 1. Network Segmentation & Access Control

To minimize the attack surface, local services are not exposed directly to the public internet via open port forwarding.

* **No Open Inbound Ports:** The router/firewall blocks all unsolicited incoming IPv4/IPv6 traffic. Port forwarding (NAT) is completely disabled.
* **Encrypted Mesh VPN (Tailscale / WireGuard):** Remote management and access to services (Jellyfin, Navidrome, Unraid WebUI) occur exclusively through an encrypted peer-to-peer overlay network.
* **Access Control Lists (ACLs):** Tailscale grants segment endpoint access by device tag (anonymized policy: [`tailscale-acl.example.hujson`](tailscale-acl.example.hujson)):
  * The smartphone (`tag:mobile`) is restricted to media streaming (`8096`, `4533`), the calendar (`8443`, HTTPS), the Matrix chat (`8448`, HTTPS) and the password manager (`8444`, HTTPS).
  * The E-Ink tablet (`tag:eink`) is restricted to Syncthing (`22000`).
  * Administrative access (SSH, Unraid Management UI) is limited to untagged control devices of the owner.
  * **Policy tests** run on every save and reject any change that would open SSH, the management UIs or unencrypted service ports to tagged devices.
* **Localhost Binding & HTTPS via `tailscale serve`:** The calendar (Radicale), the chat server (Matrix) and the password manager (Vaultwarden) listen on `127.0.0.1` only. They are not reachable from the home LAN at all (including IoT devices) and are exposed exclusively inside the tailnet through `tailscale serve`, which terminates HTTPS with a valid `*.ts.net` certificate. Tailscale Funnel (public exposure) is not used.
* **DNS Filtering (Pi-hole):** All home network devices resolve through Pi-hole, which blocks known tracking domains and forwards to Quad9 with DNSSEC validation and malware filtering. Known gap: clients can bypass it via the router's IPv6 DNS (see [`docker/pihole/`](../docker/pihole/)).
* **IoT Device Isolation (Deco):** Cloud-dependent devices (two Echo speakers, four smart plugs) are isolated with the mesh router's *Device Isolation*: they keep internet access and can still reach each other, so voice control keeps working, but they cannot reach any device on the home network (server, PCs, router management). Every device on the network was identified first (MAC vendor lookup, Pi-hole query log) and given a clear name. Streaming sticks stay in the home network because they need direct access to Jellyfin. Tested after isolation: plugs switch via voice, isolated devices still resolve through Pi-hole, Jellyfin playback on the streaming sticks works.
* **SMB Shares by Least Privilege:** Shares with personal data use *Private* security (access only for listed users). The backup account `backup` has read-only access to exactly the five shares it backs up and no access to anything else. The `Backups` share is hidden and read-only for every user, so a compromised client cannot encrypt or delete backups. `appdata` (raw data of all containers, including the password vault) is not exported via SMB at all.
* **Application-Level Scoping (Syncthing):** The E-Ink tablet synchronizes exactly two shared folders via Syncthing; no other server data is shared with it. The Syncthing container only sees explicitly mapped folders and has no access to the password vault.

---

## 2. Storage Security & Data Privacy

* **Data Protection (Academic Data):** University documents and personal files reside on the array data drives and are protected against the failure of a single drive by Unraid parity. Parity is redundancy, not a backup: a weekly, encrypted and versioned restic backup to an external drive that stays disconnected between runs covers deletion, corruption and ransomware (see [`scripts/restic-backup/`](../scripts/restic-backup/)).
* **Password Manager (Vaultwarden):** Credentials are stored in a self-hosted, zero-knowledge vault: clients encrypt locally, the server only holds ciphertext. Signups and the admin panel are disabled. Unique generated passwords replace reused ones (see [`docker/vaultwarden/`](../docker/vaultwarden/)).
* **Encrypted, Verified Backups (Vaultwarden):** Nightly consistent snapshot, encrypted with AES-256 under a separate passphrase, test-decrypted before it counts, stored on the HDD array (not the SSD holding the vault) and synced to the laptop with versioning (see [`scripts/vaultwarden-backup/`](../scripts/vaultwarden-backup/)).
* **Consistent Container Backups:** A nightly job stops each container briefly and archives its data and the Unraid boot stick, so databases are never copied mid-write; these archives are part of the offline backup.
* **Minimal Container Mounts:** Containers only get the paths they need. During a backup audit, three leftover mounts that gave open-webui read-write access to the university shares (from a paused RAG experiment) were removed.
* **Read-Only Container Mounts:** Containers serving static content (e.g., Navidrome accessing music libraries) are mounted with read-only flags (`:ro`). This prevents potential container escape exploits or software bugs from modifying or encrypting media files.
* **Least Privilege Execution:** All Docker containers run with non-root user/group mappings (`PUID=99`, `PGID=100`) to enforce strict permission boundaries on the host file system.

---

## 3. Threat Mitigation Matrix

| Security Threat | Implemented Control / Defense Mechanism |
| :--- | :--- |
| **Unauthorized External Access** | Zero open WAN ports; mandatory encrypted WireGuard/Tailscale VPN tunnel. |
| **Ransomware / Malicious Container Writes** | Immutable read-only mounts (`:ro`) for media assets. Password vault: versioned off-server copy on the laptop that the server cannot delete via sync. Remaining irreplaceable data: weekly encrypted restic snapshots on an external drive that is disconnected between runs; the backup account and the backup share are read-only. |
| **SSD Failure / Loss of the Password Vault** | Nightly encrypted backups on the HDD array and on the laptop; backup passphrase and master password are also kept offline. |
| **Credential Stuffing (Leaked, Reused Passwords)** | Unique generated passwords per account via Vaultwarden; reports for reused and exposed passwords. |
| **Accidental Deletion / Corrupted Files** | Versioned restic snapshots (8 weekly, 12 monthly) and 7 daily container archives on the server; restore verified by hash comparison. |
| **Single Drive Failure** | Unraid XOR parity (1x 10 TB parity drive) allows recovery of one failed data drive. |
| **Privilege Escalation** | Execution of containers under restricted non-root Unraid system accounts (`nobody:users`). |
| **Credential Sniffing on the Home Network** | Calendar, chat and password manager bound to localhost; access only via HTTPS through `tailscale serve`. |
| **Lost or Compromised Smartphone** | Tag-based ACL limits it to five service ports; the vault app is locked by Face ID / master password; the device can be removed from the tailnet instantly. |
| **Password Brute Force (Calendar)** | bcrypt-hashed credentials, 1 s delay after failed logins, connection limit in Radicale. |
| **Compromised IoT / Cloud Device** | Device isolation: always-listening speakers and smart plugs can reach the internet and each other, but nothing on the home network. |
| **Tracking by Apps & IoT Devices** | Network-wide DNS blocklists (Pi-hole); query log for visibility. Partial coverage due to IPv6. |
| **Malware / Phishing Domains** | Quad9 filtered upstream with DNSSEC for all devices. |
| **Data Leakage in Public Docs** | Zero-trust documentation standard: strict exclusion of internal IP addresses, MAC addresses, or credentials from public git repositories. |

---

## 4. Legal Compliance & Ethical Standards

* **Copyright Compliance (§ 95a UrhG):** Digital media extraction using MakeMKV and LibreDrive is conducted exclusively for private archiving and format shifting of legitimately owned physical media. No effective technological copy protection mechanisms are unlawfully bypassed.
