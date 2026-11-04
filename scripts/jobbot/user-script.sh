#!/bin/bash
# Inhalt für Unraid "User Scripts" -> Skript "jobbot"
# Zeitplan: Custom -> */30 * * * *   (alle 30 Minuten)
# Zugangsdaten stehen in jobbot.env (root:root, chmod 600, nie im Repo).
# --network host: continuwuity lauscht nur auf 127.0.0.1:8008 des Servers.

docker run --rm \
  --network host \
  --env-file /mnt/user/appdata/jobbot/jobbot.env \
  -v /mnt/user/appdata/jobbot:/data \
  python:3.12-alpine python /data/jobbot.py
