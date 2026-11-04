#!/usr/bin/env python3
"""
jobbot: liest weitergeleitete LinkedIn-Job-Alerts aus dem Bot-Postfach
und schickt jede neue Stelle als Nachricht in den Matrix-Raum "Jobs".

Entstanden mit KI-Hilfe (Claude); Aufbau und Ablauf sind im Repo erklärt.

Aufruf im Container:
  python /data/jobbot.py                      -> normaler Lauf (Postfach -> Matrix)
  python /data/jobbot.py --test /data/x.eml    -> nur eine .eml auswerten und anzeigen,
                                                  nichts senden, nichts speichern
  python /data/jobbot.py --preview /data/x.eml -> wie --test, schickt das Ergebnis aber
                                                  als Vorschau in den Matrix-Raum
"""

import email
import html
import imaplib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from email import policy

# ---------------------------------------------------------------------------
# Einstellungen
# ---------------------------------------------------------------------------
DATA_DIR = "/data"                                   # im Container eingehängter appdata-Ordner
SEEN_FILE = os.path.join(DATA_DIR, "seen.json")      # bereits gemeldete Stellen-IDs
SEEN_DAYS = 90                                       # so lange merken wir uns eine Stelle
SENDERS = ["jobalerts-noreply@linkedin.com"]         # nur Mails von diesen Absendern
LOOKBACK_DAYS = 3                                    # so viele Tage zurück schaut der Bot ins Postfach

# Zeilen, die zwischen den Stellen stehen, aber weder Titel, Firma noch Ort sind
SKIP_LINES = re.compile(
    r"^(Ihre Jobbenachrichtigung|\d+\s+neue\s+(Stellenangebot|Job)|Dieses Unternehmen|"
    r"Aktiv auf Personalsuche|Einfach bewerben|Mit Lebenslauf|-{3,})"
)


# ---------------------------------------------------------------------------
# Mail auswerten
# ---------------------------------------------------------------------------
def parse_alert(msg):
    """Zieht aus einer LinkedIn-Alert-Mail den Alert-Namen und die Liste der Stellen."""
    body = msg.get_body(("plain",))
    if body is None:
        return "", []
    text = body.get_content()

    # Überschrift wie "Ihre Jobbenachrichtigung für Werkstudent IT in Stockach"
    head = re.search(r"Ihre Jobbenachrichtigung für (.+?)\s*$", text, re.M)
    alert = head.group(1).strip() if head else ""

    jobs = []
    # Jede Stelle endet mit einer Zeile "Jobangebot ansehen: <Link>".
    # Wir suchen alle diese Links; der Text zwischen dem vorigen Link und dem
    # aktuellen gehört zur aktuellen Stelle. So ist egal, ob LinkedIn die
    # Stellen mit Strichlinien trennt oder nicht.
    pos = 0
    for link in re.finditer(r"Jobangebot ansehen:\s*https://\S*/jobs/view/(\d+)\S*", text):
        block = text[pos:link.start()]
        pos = link.end()
        job_id = link.group(1)

        lines = [l.strip() for l in block.splitlines() if l.strip()]
        lines = [l for l in lines if not SKIP_LINES.match(l)]
        # Übrig bleiben in dieser Reihenfolge: Titel, Firma, Ort

        jobs.append({
            "id": job_id,
            "title": lines[0] if len(lines) > 0 else "(ohne Titel)",
            "company": lines[1] if len(lines) > 1 else "",
            "location": lines[2] if len(lines) > 2 else "",
            # Sauberer Link ohne Tracking-Kennungen und Anmelde-Token
            "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
        })
    return alert, jobs


# ---------------------------------------------------------------------------
# Gemerkte Stellen (gegen Doppelmeldungen)
# ---------------------------------------------------------------------------
def load_seen():
    try:
        with open(SEEN_FILE) as f:
            seen = json.load(f)
    except FileNotFoundError:
        seen = {}
    cutoff = time.time() - SEEN_DAYS * 86400
    return {k: v for k, v in seen.items() if v > cutoff}   # Alte Einträge verwerfen


def save_seen(seen):
    tmp = SEEN_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(seen, f)
    os.replace(tmp, SEEN_FILE)                               # erst fertig schreiben, dann tauschen


# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------
def matrix_send(text, html_text=None, notice=False):
    hs = os.environ["MATRIX_HS"].rstrip("/")
    room = urllib.parse.quote(os.environ["MATRIX_ROOM"], safe="")
    txn = f"jobbot{time.time_ns()}"
    content = {"msgtype": "m.notice" if notice else "m.text", "body": text}
    if html_text:
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = html_text
    req = urllib.request.Request(
        f"{hs}/_matrix/client/v3/rooms/{room}/send/m.room.message/{txn}",
        data=json.dumps(content).encode(),
        method="PUT",
        headers={
            "Authorization": f"Bearer {os.environ['MATRIX_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def format_header(alert, n):
    """Kopf-Nachricht: die einzige, die eine Push-Benachrichtigung auslöst."""
    title = f"{n} neue Stelle{'n' if n != 1 else ''}" + (f" für „{alert}“" if alert else "")
    return title, f"<b>{html.escape(title)}</b>"


def format_job(job):
    """Eine Stelle = eine eigene Sprechblase in Element."""
    where = " · ".join(x for x in (job["company"], job["location"]) if x)
    text = f"{job['title']}\n{where}\n{job['url']}"
    h = (f"<b>{html.escape(job['title'])}</b><br>"
         f"{html.escape(where)}<br>"
         f"<a href=\"{job['url']}\">Stelle öffnen</a>")
    return text, h


def send_alert(alert, jobs):
    """Schickt erst den Kopf (m.text, mit Push), dann jede Stelle als Notiz
    (m.notice, standardmäßig ohne Push), damit pro Alert nur ein Push kommt."""
    matrix_send(*format_header(alert, len(jobs)))
    for job in jobs:
        matrix_send(*format_job(job), notice=True)


# ---------------------------------------------------------------------------
# Hauptablauf
# ---------------------------------------------------------------------------
def run():
    seen = load_seen()
    sent = 0

    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    imap.login(os.environ["IMAP_USER"], os.environ["IMAP_PASS"])
    imap.select("INBOX")

    for sender in SENDERS:
        # Alle Mails der letzten Tage, egal ob gelesen oder nicht.
        # Was schon gemeldet wurde, erkennt seen.json.
        since = time.strftime("%d-%b-%Y", time.gmtime(time.time() - LOOKBACK_DAYS * 86400))
        status, data = imap.search(None, "SINCE", since, "FROM", f'"{sender}"')
        if status != "OK":
            raise RuntimeError(f"IMAP-Suche fehlgeschlagen: {status}")

        for num in data[0].split():
            # BODY.PEEK holt die Mail, ohne sie dabei schon als gelesen zu markieren
            status, parts = imap.fetch(num, "(BODY.PEEK[])")
            msg = email.message_from_bytes(parts[0][1], policy=policy.default)

            alert, jobs = parse_alert(msg)
            # Nur Stellen, die noch nie gemeldet wurden (auch nicht doppelt in derselben Mail)
            new_jobs = []
            for job in jobs:
                if job["id"] not in seen and job["id"] not in {j["id"] for j in new_jobs}:
                    new_jobs.append(job)

            if new_jobs:
                send_alert(alert, new_jobs)
                for job in new_jobs:
                    seen[job["id"]] = time.time()
                save_seen(seen)
                sent += len(new_jobs)


    imap.logout()
    print(f"{time.strftime('%Y-%m-%d %H:%M')} fertig, {sent} neue Stelle(n) gemeldet")


def test(path, send=False):
    """Wertet eine .eml-Datei aus. Mit send=True geht das Ergebnis als Vorschau
    in den Matrix-Raum; seen.json und das Postfach bleiben unberührt."""
    with open(path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=policy.default)
    alert, jobs = parse_alert(msg)
    print(format_header(alert, len(jobs))[0])
    for job in jobs:
        print("\n" + format_job(job)[0])
    if send:
        send_alert(alert, jobs)
        print("\nVorschau an Matrix gesendet.")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ("--test", "--preview"):
        test(sys.argv[2], send=(sys.argv[1] == "--preview"))
        sys.exit(0)
    try:
        run()
    except Exception as e:
        print(f"FEHLER: {e!r}", file=sys.stderr)
        try:
            matrix_send(f"jobbot-Fehler: {e!r}")
        except Exception:
            pass                                       # Matrix selbst nicht erreichbar
        sys.exit(1)
