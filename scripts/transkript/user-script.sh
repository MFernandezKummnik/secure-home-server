#!/bin/bash
# Inhalt für Unraid "User Scripts" -> Skript "transkript"
# Zeitplan: Custom -> 0 2 * * *   (jede Nacht um 02:00)

docker run --rm \
  --network host \
  --user 99:100 \
  -v /mnt/user/appdata/transkript:/app \
  -v /mnt/user/Semester2:/semester \
  -v /mnt/user/Vorlesungsarchiv:/archiv \
  zeitung ./transkript.sh
