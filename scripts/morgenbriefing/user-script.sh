#!/bin/bash
# Inhalt für Unraid "User Scripts" -> Skript "morgenbriefing"
# Zeitplan: Custom -> 0 5 * * *   (täglich um 05:00)
# Zugangsdaten stehen in briefing.env (root:root, chmod 600, nie im Repo).
# --network host: Radicale (5232) und continuwuity (8008) lauschen nur auf 127.0.0.1 des Servers.
# -v …/boox: Ordner, den Syncthing auf das Boox schiebt; nur lesend eingebunden,
#            damit das Briefing mittwochs prüfen kann, ob die neue Zeitung angekommen ist.

docker run --rm --name morgenbriefing \
  --network host \
  --env-file /mnt/user/appdata/morgenbriefing/briefing.env \
  -v /mnt/user/appdata/zeitung/boox:/zeitung:ro \
  morgenbriefing:latest
