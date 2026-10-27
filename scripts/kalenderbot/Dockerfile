# Kalenderbot: Matrix-Chat → lokale KI → Radicale-Kalender
FROM python:3.12-slim

# Pakete zuerst installieren: Diese Schicht bleibt beim Neubau im Cache,
# solange sich requirements.txt nicht ändert.
# Zeitzonen-Daten, damit "heute" wirklich deutsche Zeit ist (auch kurz nach Mitternacht)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

ENV TZ=Europe/Berlin \
    PYTHONUNBUFFERED=1

# Nicht als root laufen (99:100 = nobody:users wie bei allen Containern auf dem Server)
USER 99:100
CMD ["python", "bot.py"]
