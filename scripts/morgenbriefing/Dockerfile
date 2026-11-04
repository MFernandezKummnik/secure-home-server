# Eigenes kleines Image, damit die Bibliotheken nicht jeden Morgen neu installiert werden
FROM python:3.12-alpine

ENV TZ=Europe/Berlin \
    PYTHONUNBUFFERED=1
RUN apk add --no-cache tzdata

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY briefing.py .

# Nicht als root laufen
USER nobody
ENTRYPOINT ["python", "/app/briefing.py"]
