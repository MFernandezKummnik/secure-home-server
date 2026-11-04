# Job Alert Bot (Python, IMAP & Matrix)

I am looking for a working-student position in IT around Stockach. Instead of checking job portals by hand, the portals send their job alerts by e-mail, a small script on the server reads them every 30 minutes and posts every new position to a private Matrix room on my phone. From there I decide which positions I apply for.

```text
LinkedIn job alert ──► main Gmail inbox
                          │ Gmail filter: only from jobalerts-noreply@linkedin.com
                          ▼
                       separate bot inbox (Gmail, app password, IMAP)
                          │ every 30 min: Unraid User Scripts → docker run python:3.12-alpine
                          ▼
                       jobbot.py
                          │ 1. fetch LinkedIn mails of the last 3 days
                          │ 2. extract title, company, location, job ID
                          │ 3. drop jobs already reported (seen.json, 90 days)
                          ▼
                       Matrix room "Jobs" (continuwuity, 127.0.0.1:8008)
                          │ one header message with push, one bubble per job
                          ▼
                       Element X on the iPhone
```

> The script and its comments are in German, like the job alerts it reads.

## Design Decisions

| Decision | Reasoning |
| :--- | :--- |
| **E-mail alerts instead of scraping** | LinkedIn, Indeed and StepStone actively block automated requests and forbid scraping in their terms of use. Their own job alerts are free, reliable and already filtered (keywords, radius). The bot only reads mails that were sent to me anyway. |
| **Separate bot inbox** | A Gmail app password grants access to the *whole* mailbox. So the bot does not get access to my main inbox (bank, password resets), but to a dedicated Gmail account. My main account forwards only the job alerts there via a filter on the exact sender address; general forwarding stays disabled. |
| **No dependency on "unread"** | The first version searched for unread mails and marked them as read afterwards. A mail that was opened by hand before the bot ran was silently skipped and a new job never arrived. Now the bot looks at all alert mails of the last 3 days and decides only by `seen.json` what is new. |
| **Deduplication by job ID** | Two alerts (around Stockach and around Friedrichshafen) overlap. The LinkedIn job ID is the key in `seen.json`; entries expire after 90 days, which is much longer than the 3-day lookback, so nothing is reported twice. |
| **Clean links** | The links in the alert mail contain tracking parameters and a one-time login token. The bot rebuilds the link from the job ID only (`linkedin.com/jobs/view/<ID>/`). |
| **Parser tested on real mails** | Jobs are found by every `Jobangebot ansehen: <link>` line; the text between two of these lines belongs to one job. Lines that are not job data ("2 neue Jobs …", "Aktiv auf Personalsuche", …) are skipped. One real mail separated the count from the text with a non-breaking space, so the pattern uses `\s+` instead of a plain space. |
| **One push per alert** | The header ("2 neue Stellen für …") is sent as `m.text` and triggers a push notification. Each job follows as its own bubble with `m.notice`, which Matrix clients do not push by default (`.m.rule.suppress_notices`). Element X merged several quote blocks in one message into a single block, so separate bubbles are the readable way to show one box per job. |
| **Matrix over localhost** | continuwuity listens on `127.0.0.1:8008` only. The script runs with `--network host` and talks to it directly, without DNS or Tailscale. The bot user `jobbot` logs in with an access token for its own device, which can be revoked without changing the password. |
| **Short-lived container** | `docker run --rm python:3.12-alpine` starts for a few seconds every 30 minutes and is deleted afterwards. Only the standard library is used, so there is no image to build. Script, secrets and `seen.json` live in `appdata` and are covered by the nightly Appdata Backup. |
| **Failure notice** | If a run fails (login, network, parser), the error is posted to the same Matrix room, so a silently broken bot does not go unnoticed. |

## Limitations

* Only LinkedIn alerts are parsed so far. Indeed alerts already arrive in the bot inbox; their parser follows once a real alert mail is available to test against.
* The parser depends on LinkedIn's plain-text mail layout. If LinkedIn changes it, `--test` with a fresh `.eml` shows the problem immediately.
* The portals filter by radius in km, not by travel time. Whether a position is reachable by bus and train is checked by hand per position.
* The room is not end-to-end encrypted, because the bot sends plain HTTP requests without an encryption library. The server is only reachable inside the tailnet.

## Files

| File | Purpose |
| :--- | :--- |
| `jobbot.py` | Fetch alert mails via IMAP, parse jobs, deduplicate, post to Matrix |
| `jobbot.env.example` | Template for the secrets file (never committed) |
| `user-script.sh` | Unraid *User Scripts* entry, schedule `*/30 * * * *` |

## Setup

**1. Bot inbox:** Create a separate Gmail account, enable 2-step verification and create an app password (`myaccount.google.com/apppasswords`). In the **main** account: add the bot address as forwarding address, keep general forwarding *disabled*, and create a filter `from:(jobalerts-noreply@linkedin.com)` → *Forward to* the bot address.

**2. Matrix user and room:** Create the user `jobbot` (continuwuity admin room: `!admin users create-user jobbot`), get an access token via `POST /_matrix/client/v3/login` and let the bot create the room and invite me:

```bash
curl -sS -X POST "http://127.0.0.1:8008/_matrix/client/v3/createRoom" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Jobs","preset":"trusted_private_chat","invite":["@<me>:<server>"]}'
```

The room created this way is unencrypted, which the bot needs.

**3. Secrets:**

```bash
mkdir -p /mnt/user/appdata/jobbot && chmod 700 /mnt/user/appdata/jobbot
cp jobbot.py /mnt/user/appdata/jobbot/
nano /mnt/user/appdata/jobbot/jobbot.env      # see jobbot.env.example
chmod 600 /mnt/user/appdata/jobbot/jobbot.env
```

**4. Test:** Download an alert mail as `.eml` and check the parser without sending anything, then send a preview to the room (`seen.json` and the inbox stay untouched in both modes):

```bash
docker run --rm --network host \
  --env-file /mnt/user/appdata/jobbot/jobbot.env \
  -v /mnt/user/appdata/jobbot:/data \
  python:3.12-alpine python /data/jobbot.py --test /data/beispiel.eml   # or --preview
```

**5. Schedule:** Unraid → Settings → User Scripts → new script `jobbot` with the content of `user-script.sh`, schedule *Custom* `*/30 * * * *`. The log is shown under *Show Log*.

---

## Transparency Note

The script in this folder was written with the help of an AI assistant (Claude by Anthropic). I worked through every part together with it, tested it against real alert mails, and can explain what each part does and why.
