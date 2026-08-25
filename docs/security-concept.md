# Security Concept & Zero-Trust Architecture

This document outlines the security controls, network isolation strategies, and privacy principles implemented across the home server infrastructure. The design strictly follows the **Security-by-Design** and **Zero-Trust** paradigms.

---

## 1. Network Segmentation & Access Control

To minimize the attack surface, local services are not exposed directly to the public internet via open port forwarding.

* **No Open Inbound Ports:** The router/firewall blocks all unsolicited incoming IPv4/IPv6 traffic. Port forwarding (NAT) is completely disabled.
* **Encrypted Mesh VPN (Tailscale / WireGuard):** Remote management and access to services (Jellyfin, Navidrome, Unraid WebUI) occur exclusively through an encrypted peer-to-peer overlay network.
* **Access Control Lists (ACLs):** Tailscale ACL rules strictly segment endpoint access:
  * Mobile devices (iPhones, Apple TV) are restricted to media streaming ports (`8096`, `4533`).
  * Administrative access (SSH, Unraid Management UI) is limited to authenticated control devices.

---

## 2. Storage Security & Data Privacy

* **Data Isolation (Air-Gapped Academic Data):** University documents and personal files reside on a dedicated Unassigned Device drive (`/dev/disk/by-id/...`), completely separated from the public media pool.
* **Read-Only Container Mounts:** Containers serving static content (e.g., Navidrome accessing music libraries) are mounted with read-only flags (`:ro`). This prevents potential container escape exploits or software bugs from modifying or encrypting media files.
* **Least Privilege Execution:** All Docker containers run with non-root user/group mappings (`PUID=99`, `PGID=100`) to enforce strict permission boundaries on the host file system.

---

## 3. Threat Mitigation Matrix

| Security Threat | Implemented Control / Defense Mechanism |
| :--- | :--- |
| **Unauthorized External Access** | Zero open WAN ports; mandatory encrypted WireGuard/Tailscale VPN tunnel. |
| **Ransomware / Malicious Container Writes** | Immutable read-only mounts (`:ro`) for media assets; isolated storage tiers. |
| **Privilege Escalation** | Execution of containers under restricted non-root Unraid system accounts (`nobody:users`). |
| **Data Leakage in Public Docs** | Zero-trust documentation standard: strict exclusion of internal IP addresses, MAC addresses, or credentials from public git repositories. |

---

## 4. Legal Compliance & Ethical Standards

* **Copyright Compliance (§ 95a UrhG):** Digital media extraction using MakeMKV and LibreDrive is conducted exclusively for private archiving and format shifting of legitimately owned physical media. No effective technological copy protection mechanisms are unlawfully bypassed.
---

## 4. Legal Compliance & Ethical Standards

* **Copyright Compliance (§ 95a UrhG):** Digital media extraction using MakeMKV and LibreDrive is conducted exclusively for private archiving and format shifting of legitimately owned physical media. No effective technological copy protection mechanisms are unlawfully bypassed.
