#!/bin/bash
# Nächtliches, verschlüsseltes Backup von Vaultwarden
# Läuft im Container "vw-backup":
#   /data   = /mnt/user/appdata/vaultwarden   (Quelle)
#   /app    = /mnt/user/appdata/vw-backup     (Skript + Passwortdatei, nur lesend)
#   /backup = /mnt/user/Backups/vaultwarden   (Ziel auf dem Array)
set -euo pipefail

QUELLE=/data
ZIEL=/backup
PASSDATEI=/app/backup.pass
BEHALTEN=30

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

# Arbeitsordner, wird am Ende immer gelöscht (auch bei Fehlern)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# gpg braucht ein beschreibbares Home-Verzeichnis
export GNUPGHOME="$TMP/gnupg"
mkdir -m 700 "$GNUPGHOME"

[ -r "$PASSDATEI" ] || { log "FEHLER: Passwortdatei fehlt oder nicht lesbar"; exit 1; }
[ -f "$QUELLE/db.sqlite3" ] || { log "FEHLER: Datenbank nicht gefunden"; exit 1; }

# 1. Konsistenter Schnappschuss der Datenbank (Vaultwarden läuft weiter)
mkdir "$TMP/vaultwarden"
sqlite3 "$QUELLE/db.sqlite3" ".backup '$TMP/vaultwarden/db.sqlite3'"

# 2. Schnappschuss prüfen
pruefung=$(sqlite3 "$TMP/vaultwarden/db.sqlite3" 'PRAGMA integrity_check;')
[ "$pruefung" = "ok" ] || { log "FEHLER: Integritätsprüfung: $pruefung"; exit 1; }

# 3. Restliche Dateien dazulegen (Schlüssel, Anhänge, Sends)
cp -a "$QUELLE"/rsa_key* "$TMP/vaultwarden/" 2>/dev/null || log "Hinweis: keine rsa_key-Dateien gefunden"
for ordner in attachments sends; do
  if [ -d "$QUELLE/$ordner" ]; then cp -a "$QUELLE/$ordner" "$TMP/vaultwarden/"; fi
done

# 4. Packen und verschlüsseln (AES-256, eigenes Backup-Passwort)
NAME="vaultwarden_$(date +%Y-%m-%d_%H%M).tar.gz.gpg"
tar -czf "$TMP/backup.tar.gz" -C "$TMP" vaultwarden
gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-file "$PASSDATEI" \
    --symmetric --cipher-algo AES256 \
    -o "$ZIEL/$NAME.tmp" "$TMP/backup.tar.gz"

# 5. Testweise entschlüsseln und Archiv lesen, erst dann gilt das Backup
#    Bewusst ohne Pipe: jeder Schritt einzeln, damit Fehler sichtbar werden
fehler() { rm -f "$ZIEL/$NAME.tmp"; log "FEHLER: $1"; exit 1; }

gpg --batch --quiet --pinentry-mode loopback --passphrase-file "$PASSDATEI" \
    --decrypt -o "$TMP/pruefung.tar.gz" "$ZIEL/$NAME.tmp" 2>"$TMP/gpg.log" \
  || fehler "Testentschlüsselung: $(cat "$TMP/gpg.log")"
inhalt=$(tar -tzf "$TMP/pruefung.tar.gz" 2>&1) \
  || fehler "Archiv nicht lesbar: $inhalt"
grep -qx 'vaultwarden/db.sqlite3' <<< "$inhalt" \
  || fehler "Datenbank fehlt im Archiv. Inhalt: $inhalt"
mv "$ZIEL/$NAME.tmp" "$ZIEL/$NAME"
log "Backup erstellt: $NAME ($(du -h "$ZIEL/$NAME" | cut -f1))"

# 6. Alte Backups löschen, nur die neuesten $BEHALTEN bleiben
mapfile -t alle < <(ls -1 "$ZIEL"/vaultwarden_*.tar.gz.gpg | sort -r)
for alt in "${alle[@]:$BEHALTEN}"; do
  rm -f -- "$alt"
  log "Gelöscht (älter als $BEHALTEN Backups): $(basename "$alt")"
done
log "Fertig. Vorhandene Backups: $(( ${#alle[@]} < BEHALTEN ? ${#alle[@]} : BEHALTEN ))"
