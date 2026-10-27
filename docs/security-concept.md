# Security Concept & Zero-Trust Architecture

This document outlines the security controls, network isolation strategies, and privacy principles implemented across the home server infrastructure. The design strictly follows the **Security-by-Design** and **Zero-Trust** paradigms.

---

## 1. Network Segmentation & Access Control

To minimize the attack surface, local services are not exposed directly to the public internet via open port forwarding.

* **No Open Inbound Ports:** The router/firewall blocks all unsolicited incoming IPv4/IPv6 traffic. Port forwarding (NAT) is completely disabled.
* **Encrypted Mesh VPN (Tailscale / WireGuard):** Remote management and access to services (Jellyfin, Navidrome, Unraid WebUI) occur exclusively through an encrypted peer-to-peer overlay network.
* **Access Control Lists (ACLs):** Tailscale grants segment endpoint access by device tag (anonymized policy: [`tailscale-acl.example.hujson`](tailscale-acl.example.hujson)):
  * The smartphone (`tag:mobile`) is restricted to media streaming (`8096`, `4533`), the calendar (`8443`, HTTPS) and the Matrix chat (`8448`, HTTPS).
  * The E-Ink tablet (`tag:eink`) is restricted to Syncthing (`22000`).
  * Administrative access (SSH, Unraid Management UI) is limited to untagged control devices of the owner.
  * **Policy tests** run on every save and reject any change that would open SSH, the management UIs or unencrypted service ports to tagged devices.
* **Localhost Binding & HTTPS via `tailscale serve`:** The calendar (Radicale) and the chat server (Matrix) listen on `127.0.0.1` only. They are not reachable from the home LAN at all (including IoT devices) and are exposed exclusively inside the tailnet through `tailscale serve`, which terminates HTTPS with a valid `*.ts.net` certificate. Tailscale Funnel (public exposure) is not used.
* **DNS Filtering (Pi-hole):** All home network devices resolve through Pi-hole, which blocks known tracking domains and forwards to Quad9 with DNSSEC validation and malware filtering. Known gap: clients can bypass it via the router's IPv6 DNS (see [`docker/pihole/`](../docker/pihole/)).
* **Application-Level Scoping (Syncthing):** The E-Ink tablet synchronizes exactly two shared folders via Syncthing; no other server data is shared with it.

---

## 2. Storage Security & Data Privacy

* **Data Protection (Academic Data):** University documents and personal files reside on the array data drives and are protected against the failure of a single drive by Unraid parity. Parity is redundancy, not a backup; a separate backup is planned.
* **Read-Only Container Mounts:** Containers serving static content (e.g., Navidrome accessing music libraries) are mounted with read-only flags (`:ro`). This prevents potential container escape exploits or software bugs from modifying or encrypting media files.
* **Least Privilege Execution:** All Docker containers run with non-root user/group mappings (`PUID=99`, `PGID=100`) to enforce strict permission boundaries on the host file system.

---

## 3. Threat Mitigation Matrix

| Security Threat | Implemented Control / Defense Mechanism |
| :--- | :--- |
| **Unauthorized External Access** | Zero open WAN ports; mandatory encrypted WireGuard/Tailscale VPN tunnel. |
| **Ransomware / Malicious Container Writes** | Immutable read-only mounts (`:ro`) for media assets. A separate, versioned backup is planned. |
| **Single Drive Failure** | Unraid XOR parity (1x 10 TB parity drive) allows recovery of one failed data drive. |
| **Privilege Escalation** | Execution of containers under restricted non-root Unraid system accounts (`nobody:users`). |
| **Credential Sniffing on the Home Network** | Calendar and chat bound to localhost; access only via HTTPS through `tailscale serve`. |
| **Lost or Compromised Smartphone** | Tag-based ACL limits it to four service ports; the device can be removed from the tailnet instantly. |
| **Password Brute Force (Calendar)** | bcrypt-hashed credentials, 1 s delay after failed logins, connection limit in Radicale. |
| **Tracking by Apps & IoT Devices** | Network-wide DNS blocklists (Pi-hole); query log for visibility. Partial coverage due to IPv6. |
| **Malware / Phishing Domains** | Quad9 filtered upstream with DNSSEC for all devices. |
| **Data Leakage in Public Docs** | Zero-trust documentation standard: strict exclusion of internal IP addresses, MAC addresses, or credentials from public git repositories. |

---

## 4. Legal Compliance & Ethical Standards

* **Copyright Compliance (§ 95a UrhG):** Digital media extraction using MakeMKV and LibreDrive is conducted exclusively for private archiving and format shifting of legitimately owned physical media. No effective technological copy protection mechanisms are unlawfully bypassed.
