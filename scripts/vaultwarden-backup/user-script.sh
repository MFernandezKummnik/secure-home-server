#!/bin/bash
# Inhalt für Unraid "User Scripts" -> Skript "vaultwarden-backup"
# Zeitplan: Custom -> 0 3 * * *   (jede Nacht um 03:00)

docker run --rm \
  --network none \
  --user 99:100 \
  -v /etc/localtime:/etc/localtime:ro \
  -v /mnt/user/appdata/vaultwarden:/data \
  -v /mnt/user/appdata/vw-backup:/app:ro \
  -v /mnt/user/Backups/vaultwarden:/backup \
  vw-backup /app/backup.sh
