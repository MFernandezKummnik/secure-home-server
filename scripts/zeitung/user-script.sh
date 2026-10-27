#!/bin/bash
# Inhalt für Unraid "User Scripts" -> Skript "zeitung"
# Zeitplan: Custom -> 0 4 * * 3   (jeden Mittwoch um 04:00)

docker run --rm \
  -v /mnt/user/appdata/zeitung:/app \
  zeitung ./zeitung.sh
