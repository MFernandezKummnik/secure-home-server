# Morning Briefing (Python, CalDAV & Matrix)

Every morning at 05:00 the server sends one Matrix message to my phone: today's events, deadlines coming up in the next 7 days, the weather in Stockach with a rain and frost hint, and on Wednesdays whether the new issue of the [local AI newspaper](../zeitung/) has arrived on the Boox.

```text
05:00  User Script starts a short-lived container (--rm)
   │ 1. Radicale (CalDAV, 127.0.0.1:5232) → events today … +7 days, recurring events expanded
   │ 2. Open-Meteo → daily forecast + hourly rain probability (no account, no API key)
   │ 3. Wednesdays: newest file in zeitung/boox younger than 6 h?
   │ 4. plain-text template, no LLM
   └──► Matrix (continuwuity, 127.0.0.1:8008) → room "Morgenbriefing", sent by @kalenderbot
```

Example (test data):

```text
☀️ Guten Morgen! Mittwoch, 4. November

🌤 Stockach: leichter Regen, 1 bis 8 °C
☂️ Schirm einpacken: Regen wahrscheinlich etwa 14–18 Uhr
🧊 Frostig: Glätte möglich

📅 Heute
• 08:00 BeSy Vorlesung (F 033)
• 23:59 ❗ Abgabe ALDA Blatt 4

📝 Abgaben bis Mi 11.11.
• Do 05.11. – Klausur BWL2 (in 1 Tag)
• Di 10.11., 12:00 – Abgabe SyMo Modell (in 6 Tagen)

📰 Neue Wochenzeitung liegt bereit (zeitung-2026-KW45.html).
```

> The script, its comments and the message are in German.

## Design Decisions

| Decision | Reasoning |
| :--- | :--- |
| **No LLM** | The message is a fixed template filled with structured data. A model would add cost, latency and the risk of invented appointments, with nothing to gain. |
| **Python instead of Bash** | iCalendar data with recurrence rules, all-day events and time zones is fragile to parse by hand; `caldav` with `expand=True` turns a weekly lecture into the single occurrences of each day. |
| **Same account as the calendar bot, separate device** | The briefing is sent as `@kalenderbot`, but with its own login (device "Morgenbriefing") and its own access token. It can be revoked on its own without touching the calendar bot, which is a separate program. |
| **Separate room** | The daily briefing does not clutter the chat in which events are sent to the calendar bot. |
| **Open-Meteo** | Free, no registration and no key to store; the request contains only the coordinates of the town. |
| **Each section fails on its own** | If the weather API or Radicale is unreachable, the message is still sent with a short note instead of nothing. Only a failed Matrix request ends the run with an error, which shows up in the User Scripts log. |
| **Deadlines by keyword** | An event counts as a deadline if its title contains one of `ABGABE_WORTE` (default: Abgabe, Deadline, Frist, Klausur, Prüfung). Empty list = show all events of the next 7 days. |
| **Newspaper check instead of a fixed hint** | The newspaper runs at 04:00 on Wednesdays. The briefing checks the folder Syncthing delivers to the Boox, so a failed run is noticed at breakfast rather than when opening the Boox. |
| **05:00** | Before getting up, and after the newspaper run has finished. |
| **Least privilege** | Container runs as `nobody`, the newspaper folder is mounted read-only, credentials live in `briefing.env` (`chmod 600`) and are passed via `--env-file`. |
| **`--network host`** | Radicale and continuwuity listen on `127.0.0.1` only (reachable from outside solely via `tailscale serve`); host networking lets the container reach them without exposing either service further. |

## Files

| File | Purpose |
| :--- | :--- |
| `briefing.py` | Fetch calendar and weather, build the message, send it to Matrix (`--test` prints instead of sending) |
| `Dockerfile` | `python:3.12-alpine` with `tzdata`, `caldav` and `requests`, runs as `nobody` |
| `requirements.txt` | Python dependencies, pinned below the next major version |
| `briefing.env.example` | Template for settings and credentials |
| `user-script.sh` | Unraid *User Scripts* entry, schedule `0 5 * * *` |

## Setup

```bash
# 1. Copy this folder to the server
mkdir -p /mnt/user/appdata/morgenbriefing          # copy the files into it
cd /mnt/user/appdata/morgenbriefing
cp briefing.env.example briefing.env && chmod 600 briefing.env   # fill in the Radicale password

# 2. Own login for the bot account (password is read without echo and not stored in the history)
HS="http://127.0.0.1:8008"
read -s -p "Passwort kalenderbot: " PW; echo
curl -s -X POST "$HS/_matrix/client/v3/login" -H "Content-Type: application/json" \
  -d "{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"kalenderbot\"},\"password\":\"$PW\",\"initial_device_display_name\":\"Morgenbriefing\"}"
unset PW
# → access_token into MATRIX_TOKEN

# 3. Room, created by the bot, with an invite for my account
read -s -p "Token: " TOKEN; echo
curl -s -X POST "$HS/_matrix/client/v3/createRoom" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Morgenbriefing","preset":"private_chat","invite":["@rey:<servername>"]}'
unset TOKEN
# → room_id into MATRIX_RAUM_ID, accept the invite in the app

# 4. Build and test (prints the message, sends nothing)
docker build -t morgenbriefing .
docker run --rm --network host --env-file briefing.env \
  -v /mnt/user/appdata/zeitung/boox:/zeitung:ro morgenbriefing --test
```

**Schedule:** Unraid → Settings → User Scripts → new script with the content of `user-script.sh`, schedule *Custom* `0 5 * * *`. After changes to `briefing.py`, rebuild the image; changes to `briefing.env` apply on the next run.

## Lessons Learned

* **`127.0.0.1` inside a container is the container.** Both services are bound to the host's loopback interface on purpose, so a container on the default bridge network cannot reach them. `--network host` solves this without publishing the ports.
* **A placeholder in an invite is not harmless text.** Inviting `@rey:XXXX` made the homeserver treat `XXXX` as a remote server and fail with a federation error. The server name is now read from `/account/whoami` instead of typed by hand.
* **"Aufgabe" is deliberately not a deadline.** The first real run listed "Besy Aufgabe" only under today, not in the deadline preview. That is intended: an *Aufgabe* is something to work on, an *Abgabe* is something to hand in. Only hand-ins are announced days ahead; the keyword list stays configurable for other naming habits.

## Transparency Note

The script in this folder was written with the help of an AI assistant (Claude by Anthropic). I worked through every part together with it, tested it, and can explain what each part does and why.
