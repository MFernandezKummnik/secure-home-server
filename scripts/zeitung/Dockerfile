# Kleiner Werkzeug-Container für die Zeitungsautomation.
# Unraid selbst bringt keine Tools wie jq oder xmlstarlet mit –
# deshalb laufen unsere Bash-Skripte in diesem Container.
FROM alpine:3.20

# bash      -> unsere Skripte sind Bash, Alpine hat standardmäßig nur "sh"
# curl      -> Feeds herunterladen und später Ollama ansprechen
# jq        -> JSON verarbeiten (brauchen wir in Schritt 2 für Ollama)
# xmlstarlet-> RSS/Atom-Feeds (XML) auslesen
# coreutils -> vollwertiges "date", das Datumsangaben aus Feeds versteht
# tzdata    -> deutsche Zeitzone
# cmark     -> wandelt Markdown in HTML um (Schritt 3)
RUN apk add --no-cache bash curl jq xmlstarlet coreutils tzdata cmark

ENV TZ=Europe/Berlin
WORKDIR /app
CMD ["bash"]
