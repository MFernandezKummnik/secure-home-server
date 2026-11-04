#!/bin/bash
# Inhalt für Unraid "User Scripts" -> Skript "karteikarten"
# Zeitplan: Custom -> 0 23 * * *   (jeden Abend um 23:00)
# Modell und API-Schlüssel stehen in geheim.env (root:root, chmod 600, nie im Repo).
# Mathematik2 ist ein Übungsfach und bekommt keine Karteikarten.

docker run --rm \
  --network host \
  --user 99:100 \
  --env-file /mnt/user/appdata/karteikarten/geheim.env \
  -e AUSLASSEN="Mathematik2" \
  -v /mnt/user/appdata/karteikarten:/app \
  -v /mnt/user/Semester2:/semester \
  karteikarten
