# Self-Hosted Calendar Bot (Matrix + Local AI + CalDAV)

A chat bot that manages my calendar in plain German, running entirely on my own server. I write to it in a self-hosted Matrix chat, a local LLM (Ollama on the GTX 1070) understands the message, and the bot adds, lists or deletes events in my self-hosted Radicale calendar, which syncs to my phone via CalDAV.

```text
Me:  "nächste Woche Dienstag Abgabe ALDA"
Bot: 📅 Abgabe ALDA · Tue 03.11.2026 · all day · Calendar Uni
     Add it? Reply yes or no.
Me:  "ja"
Bot: ✅ Added
```

**Features**

| Action | Example | Safety |
| :--- | :--- | :--- |
| Add | "morgen 18 Uhr Schicht im Restaurant bis 23 Uhr" | Always asks for confirmation |
| List | "was habe ich nächste Woche?" | Read-only, recurring events expanded |
| Delete | "lösche Abgabe ALDA" | Numbered selection, single events only |

> Code comments, prompts and bot replies are in German, as the bot is used in German.

---

## Architecture

```text
[ Phone: Element X ]
        │  HTTPS via Tailscale (tailscale serve :8448)
        ▼
[ continuwuity ]  private Matrix homeserver, federation disabled, 127.0.0.1:8008
        │
        ▼
[ kalenderbot ]  Python container, host network
        │
        ├── verstehen.py ── Ollama (qwen3.5:4b), JSON schema output
        │                   "what is meant" → fixed fields
        ├── datum.py ────── deterministic date calculation
        │                   "next week, Tuesday" → 2026-11-03
        └── kalender.py ─── CalDAV (PROPFIND / REPORT / PUT / DELETE)
                │
                ▼
        [ Radicale ]  127.0.0.1:5232
                │  HTTPS via Tailscale (tailscale serve :8443)
                ▼
        [ Phone: native calendar app ]
```

Nothing is exposed to the internet: all services listen on `127.0.0.1` only and are reachable exclusively through `tailscale serve` (HTTPS with a valid `*.ts.net` certificate) inside the tailnet. The bot polls Matrix itself, so no inbound port is needed.

## Design Decisions

| Decision | Reasoning |
| :--- | :--- |
| **The AI understands, the code calculates** | Small LLMs are unreliable at date arithmetic. The model only extracts *what* was said (`weekday: dienstag, next_week: true`); `datum.py` computes the actual date. Covered by tests for week boundaries, year rollover and invalid dates. |
| **Structured output** | Ollama's `format` parameter forces the model into a JSON schema with enums (e.g. only existing calendar names), so the code always receives valid fields. |
| **Confirmation before every write** | A wrongly entered deadline is worse than none. Adding requires "ja", deleting requires picking a number. Pending proposals expire after 10 minutes. |
| **Recurring events are never deleted by the bot** | Deleting one lecture vs. the whole semester series is a decision better made in the calendar app with its explicit prompt. |
| **ETag check on delete** | `If-Match` ensures an event is only deleted if it has not been changed since the search. `If-None-Match: *` ensures adding never overwrites an existing event. |
| **Allow-list** | The bot only reacts to one Matrix user, only in its own room, and only to messages sent after it started. |
| **Unencrypted bot room** | End-to-end encryption in bots requires additional crypto libraries with a deprecated upstream. The room is created by the bot without E2EE; transport is still HTTPS inside the WireGuard tunnel, and messages are stored only on my own server. |
| **Least privilege** | Containers run as `99:100`, configs are mounted read-only, secrets live in a `chmod 600` env file, the bot's session token in a `chmod 600` file. |
| **Matrix instead of Telegram** | Telegram bot chats are not end-to-end encrypted and pass through Telegram's cloud. A private homeserver keeps the whole chain on my hardware. |

---

## Files

| File | Purpose |
| :--- | :--- |
| `bot.py` | Matrix connection, conversation flow, confirmation state |
| `verstehen.py` | Prompt, JSON schema and Ollama request |
| `datum.py` | Date and date-range calculation |
| `kalender.py` | CalDAV client: find calendars, search (with recurrence expansion), add, delete |
| `Dockerfile` | `python:3.12-slim` + tzdata, runs as `99:100` |
| `docker-compose.yml` | Container definition (host network, env file, data volume) |
| `geheim.env.example` | Template for the two passwords |

Related configuration: [`docker/radicale/`](../../docker/radicale/), [`docker/continuwuity/`](../../docker/continuwuity/), Tailscale policy in [`docs/tailscale-acl.example.hujson`](../../docs/tailscale-acl.example.hujson).

## Setup (short)

1. Run Radicale and continuwuity (see their compose files), expose them with `tailscale serve`.
2. Register the first Matrix account with the one-time token, then create the bot account in the admin room: `!admin users create-user kalenderbot`.
3. Copy this folder to `/mnt/user/appdata/kalenderbot/`, create `geheim.env` from the template (`chmod 600`), create `daten/` owned by `99:100`.
4. `docker build -t kalenderbot .` and start the container. On first start the bot creates a room and invites the allowed user.

## Lessons Learned

* **iOS refuses to send credentials over plain HTTP** – the calendar only worked after putting Radicale behind `tailscale serve` with a real certificate.
* **Element X requires `.well-known/matrix/client`** before it even asks for a password; serving it from continuwuity on the same HTTPS port solved the login.
* **Copy & paste of password hashes from a web terminal can silently drop characters** – letting `htpasswd` write the file directly avoided this.

---

## Transparency Note

The code in this folder was written with the help of an AI assistant (Claude by Anthropic). I worked through every component together with it, debugged the setup on my own server step by step, and can explain what each part of the code does and why it is built this way. The bot itself uses only an open-weight model running locally on my own hardware.
