"""verstehen.py – lässt die lokale KI (Ollama) eine Nachricht in feste Felder zerlegen."""

import json
from datetime import date

import requests

from datum import KUERZEL

KALENDER = ["Uni", "Arbeit", "Privat", "Gym"]

# Ollama zwingt die Antwort in genau diese Struktur ("structured output").
# Statt null nutzen wir leere Werte ("" bzw. 0) – das verkraften kleine Modelle besser.
SCHEMA = {
    "type": "object",
    "properties": {
        "aktion":         {"type": "string", "enum": ["eintragen", "loeschen", "abfragen"]},
        "titel":          {"type": "string"},
        "kalender":       {"type": "string", "enum": KALENDER + ["unklar"]},
        "tag":            {"type": "string",
                           "enum": ["heute", "morgen", "uebermorgen", "wochentag",
                                    "datum", "in_tagen", "unklar"]},
        "wochentag":      {"type": "string",
                           "enum": ["", "montag", "dienstag", "mittwoch", "donnerstag",
                                    "freitag", "samstag", "sonntag"]},
        "naechste_woche": {"type": "boolean"},
        "datum":          {"type": "string"},
        "in_tagen":       {"type": "integer"},
        "start":          {"type": "string"},
        "ende":           {"type": "string"},
        "zeitraum":       {"type": "string", "enum": ["tag", "diese_woche", "naechste_woche"]},
    },
    "required": ["aktion", "titel", "kalender", "tag", "wochentag", "naechste_woche",
                 "datum", "in_tagen", "start", "ende", "zeitraum"],
}

ANWEISUNG = """Du zerlegst eine kurze Nachricht auf Deutsch in Felder für einen Kalender.
Du rechnest KEIN Datum aus, du gibst nur wieder, was in der Nachricht steht.

Felder:
- aktion: "eintragen" (neuer Termin), "loeschen" (Wörter wie lösche, entferne, streiche),
  "abfragen" (Fragen wie "was steht an", "was habe ich", "welche Termine").
- titel: bei eintragen der kurze Titel des Termins, bei loeschen der Suchbegriff,
  bei abfragen "". Ohne Datum und Uhrzeit, ohne Wörter wie "eintragen" oder "lösche".
  Abkürzungen beibehalten (z. B. "ALDA", "BeSy").
- kalender: Uni (Vorlesung, Übung, Abgabe, Prüfung, Lernen, Modulnamen),
  Arbeit (Schicht, Kellnern, Werkstudent), Gym (Training, Fitness, Sport),
  Privat (alles andere). Bei loeschen und abfragen "unklar".
- tag: "heute", "morgen", "uebermorgen", "wochentag" (ein Wochentag wird genannt),
  "datum" (ein Datum wie 12.11. wird genannt), "in_tagen" (z. B. "in 3 Tagen", "in 2 Wochen"),
  sonst "unklar".
- wochentag: nur bei tag="wochentag", kleingeschrieben, sonst "".
- naechste_woche: true, wenn ausdrücklich "nächste Woche" gesagt wird, sonst false.
- datum: nur bei tag="datum", im Format TT.MM. oder TT.MM.JJJJ, sonst "".
- in_tagen: nur bei tag="in_tagen", Anzahl Tage (Wochen mal 7), sonst 0.
- start / ende: Uhrzeit im Format HH:MM, sonst "". Ohne Uhrzeit ist es ganztägig.
- zeitraum: nur für abfragen wichtig. "diese_woche" bei "diese Woche",
  "naechste_woche" bei "nächste Woche" ohne bestimmten Tag, sonst "tag".

Beispiele:
"nächste woche dienstag abgabe alda eintragen" →
{"aktion":"eintragen","titel":"Abgabe ALDA","kalender":"Uni","tag":"wochentag","wochentag":"dienstag","naechste_woche":true,"datum":"","in_tagen":0,"start":"","ende":"","zeitraum":"tag"}
"morgen 18 uhr schicht im restaurant bis 23 uhr" →
{"aktion":"eintragen","titel":"Schicht im Restaurant","kalender":"Arbeit","tag":"morgen","wochentag":"","naechste_woche":false,"datum":"","in_tagen":0,"start":"18:00","ende":"23:00","zeitraum":"tag"}
"lösche abgabe alda" →
{"aktion":"loeschen","titel":"Abgabe ALDA","kalender":"unklar","tag":"unklar","wochentag":"","naechste_woche":false,"datum":"","in_tagen":0,"start":"","ende":"","zeitraum":"tag"}
"lösch den zahnarzt am freitag" →
{"aktion":"loeschen","titel":"Zahnarzt","kalender":"unklar","tag":"wochentag","wochentag":"freitag","naechste_woche":false,"datum":"","in_tagen":0,"start":"","ende":"","zeitraum":"tag"}
"was steht morgen an?" →
{"aktion":"abfragen","titel":"","kalender":"unklar","tag":"morgen","wochentag":"","naechste_woche":false,"datum":"","in_tagen":0,"start":"","ende":"","zeitraum":"tag"}
"was habe ich nächste woche?" →
{"aktion":"abfragen","titel":"","kalender":"unklar","tag":"unklar","wochentag":"","naechste_woche":true,"datum":"","in_tagen":0,"start":"","ende":"","zeitraum":"naechste_woche"}
"was ist diese woche los" →
{"aktion":"abfragen","titel":"","kalender":"unklar","tag":"unklar","wochentag":"","naechste_woche":false,"datum":"","in_tagen":0,"start":"","ende":"","zeitraum":"diese_woche"}
"""


def nachricht_verstehen(text: str, heute: date, ollama_url: str, modell: str) -> dict:
    """Schickt die Nachricht an Ollama und gibt die erkannten Felder zurück."""
    anfrage = {
        "model": modell,
        "stream": False,
        "think": False,
        "format": SCHEMA,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": ANWEISUNG},
            {"role": "user",
             "content": f"Heute ist {KUERZEL[heute.weekday()]} {heute:%d.%m.%Y}.\nNachricht: {text}"},
        ],
    }
    antwort = requests.post(f"{ollama_url}/api/chat", json=anfrage, timeout=120)
    antwort.raise_for_status()
    return json.loads(antwort.json()["message"]["content"])
