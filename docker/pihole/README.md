# Pi-hole – Network-Wide DNS Filtering

Pi-hole answers the DNS queries of all devices in the home network. Domains on a blocklist (about 74,000 by default) resolve to `0.0.0.0`, so ads and trackers are never loaded; everything else is forwarded to **Quad9**.

```text
Home network devices ──(DHCP: DNS = server)──► Pi-hole :53 ──► Quad9 (DNSSEC, malware filter)
                                                    │
                                                    └── blocked domains → 0.0.0.0
```

---

## Setup

| Decision | Reasoning |
| :--- | :--- |
| **Web UI on `127.0.0.1` + `tailscale serve`** | Port 80 is used by the Unraid WebUI, and the admin interface should not be reachable for IoT devices in the LAN. |
| **Password in a `chmod 600` env file** | Keeps it out of the compose file, the shell history and `docker inspect`. |
| **Upstream set via `FTLCONF_dns_upstreams`** | Configuration as code; survives re-creation of the container. Quad9 *filtered, DNSSEC, without ECS*: blocks known malware domains, validates signatures, and does not forward parts of the client IP. |
| **No extra capabilities** | `NET_ADMIN` / `SYS_TIME` are only required if Pi-hole acts as DHCP or NTP server. |
| **Router: DNS via DHCP, no secondary server** | The Deco hands out Pi-hole directly, so queries are visible per device. A public secondary DNS would be used alternately by many clients and let ads through. |
| **Address reservation for the server** | The server's IP lies inside the router's DHCP range; the reservation prevents it from changing and taking the whole network's DNS down. |

Verification after setup: `nslookup doubleclick.net <server-ip>` → `0.0.0.0`, `nslookup google.de <server-ip>` → real address.

---

## What Did Not Work (and Why)

**1. IPv6 bypass.** The network has IPv6, and the router (TP-Link Deco in mobile-router mode) announces its own IPv6 DNS server to all clients. Clients use it alongside or instead of Pi-hole, so part of the traffic bypasses filtering. The Deco app offers no IPv6 setting in this mode. Possible fixes, not yet implemented:
* let Pi-hole announce itself as IPv6 DNS server via Router Advertisements (requires IPv6 for the container),
* switch the mobile connection to IPv4-only (risky with mobile providers that rely on IPv6).

**2. Streaming device banners.** The main goal was removing ad banners on a Fire TV stick. They remained. Streaming platforms load banners, recommendations and the regular UI from the same domains, and in-stream ads come from the same servers as the video itself. DNS filtering works per domain and cannot separate these. The same applies to Google TV; there, the built-in *apps-only mode* is the effective solution.

**3. Browsers.** No additional benefit on PC, laptop and phone: the browser (Brave) already blocks ads and trackers in the page itself, which is more precise than blocking whole domains.

## What It Is Still Used For

* **In-app ads on the smartphone:** after the switch, ads inside apps on the phone disappeared while it is connected to the home Wi-Fi. This is the clearest benefit, because the browser-based blocker cannot reach ads inside apps. On mobile data the phone uses other DNS servers, so the effect is limited to the home network (see *Possible Next Steps*).
* **Tracking outside the browser:** apps, smart plugs, smart lights and the streaming stick regularly contact vendor servers. Brave cannot see this traffic; Pi-hole blocks part of it (over IPv4).
* **Visibility:** the query log shows which device talks to which domain and how often – useful for spotting chatty or suspicious IoT devices.
* **Malware and phishing filter** for every device through Quad9.

## Known Trade-Off

If the server is down, DNS fails for the whole home network. Mitigation: the server runs 24/7 with `restart: unless-stopped`; in an emergency the router's DNS setting is switched back to automatic.

## Possible Next Steps

* Solve the IPv6 bypass (see above).
* Use Pi-hole as DNS server of the tailnet so mobile devices are filtered on the go, extending the in-app ad blocking to mobile data (requires port 53 in the Tailscale ACL for `tag:mobile`; adds some latency on mobile networks).
