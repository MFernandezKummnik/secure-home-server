#!/bin/bash
# Inhalt für Unraid "User Scripts" -> Skript "transkript"
# Zeitplan: Custom -> 0 1 * * *   (jede Nacht um 01:00)

docker run --rm \
  --network host \
  --user 99:100 \
  -v /mnt/user/appdata/transkript:/app \
  -v /mnt/user/Semester2:/semester \
  -v /mnt/user/Vorlesungsarchiv:/archiv \
  zeitung ./transkript.sh
