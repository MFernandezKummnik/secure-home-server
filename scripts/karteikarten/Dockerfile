# Werkzeug-Container für die Karteikarten-Automation.
# Enthält nur Python, die Bibliotheken und pdftotext – das Skript selbst und
# die Prompts liegen in appdata und werden beim Start eingebunden (wie beim Transkript).
# Änderungen am Prompt brauchen deshalb keinen Neubau.
FROM python:3.12-slim

# poppler-utils -> pdftotext: liest den Text aus den Folien-PDFs
# tzdata        -> deutsche Zeit in Logs und Vorschau
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

ENV TZ=Europe/Berlin \
    PYTHONUNBUFFERED=1
WORKDIR /app

# Nicht als root laufen (99:100 = nobody:users wie bei allen Containern auf dem Server)
USER 99:100
CMD ["python", "karteikarten.py"]
