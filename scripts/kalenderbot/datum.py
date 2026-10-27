"""datum.py – rechnet aus dem, was die KI verstanden hat, ein echtes Datum aus.

Grundsatz: Die KI sagt nur, WAS gemeint ist ("nächste Woche, Dienstag").
Das Rechnen übernimmt dieser Code, weil Sprachmodelle beim Datumsrechnen
unzuverlässig sind.
"""

from datetime import date, timedelta

WOCHENTAGE = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]
KUERZEL = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def datum_berechnen(angaben: dict, heute: date) -> date | None:
    """Gibt das gemeinte Datum zurück oder None, wenn es nicht eindeutig ist."""
    art = angaben.get("tag", "unklar")

    if art == "heute":
        return heute
    if art == "morgen":
        return heute + timedelta(days=1)
    if art == "uebermorgen":
        return heute + timedelta(days=2)

    if art == "in_tagen":
        n = angaben.get("in_tagen", 0)
        return heute + timedelta(days=n) if isinstance(n, int) and n > 0 else None

    if art == "wochentag":
        name = angaben.get("wochentag", "")
        if name not in WOCHENTAGE:
            return None
        ziel = WOCHENTAGE.index(name)          # 0 = Montag ... 6 = Sonntag

        if angaben.get("naechste_woche"):
            # Montag der nächsten Kalenderwoche, dann den Wochentag dazu
            montag_naechste = heute + timedelta(days=7 - heute.weekday())
            return montag_naechste + timedelta(days=ziel)

        # Ohne "nächste Woche": der nächste kommende Tag mit diesem Namen.
        # Heute zählt nicht mit – dafür sagt man "heute".
        abstand = (ziel - heute.weekday()) % 7
        return heute + timedelta(days=abstand or 7)

    if art == "datum":
        return _datum_lesen(angaben.get("datum", ""), heute)

    return None


def _datum_lesen(text: str, heute: date) -> date | None:
    """Liest 'TT.MM.' oder 'TT.MM.JJJJ'. Ohne Jahr: das nächste passende Datum."""
    teile = [t for t in text.strip().split(".") if t]
    try:
        tag, monat = int(teile[0]), int(teile[1])
        if len(teile) >= 3:
            jahr = int(teile[2])
            jahr = jahr + 2000 if jahr < 100 else jahr
            return date(jahr, monat, tag)
        kandidat = date(heute.year, monat, tag)
        return kandidat if kandidat >= heute else date(heute.year + 1, monat, tag)
    except (ValueError, IndexError):
        return None


def zeitraum_berechnen(angaben: dict, heute: date) -> tuple[date, date] | None:
    """Für Abfragen: (erster Tag, Tag NACH dem letzten Tag). None, wenn unklar."""
    art = angaben.get("zeitraum", "tag")
    montag = heute - timedelta(days=heute.weekday())

    if art == "diese_woche":
        return heute, montag + timedelta(days=7)          # ab heute bis Sonntag
    if art == "naechste_woche":
        return montag + timedelta(days=7), montag + timedelta(days=14)

    # Ein einzelner Tag; ohne Angabe ist "heute" gemeint
    tag = datum_berechnen(angaben, heute) if angaben.get("tag") != "unklar" else heute
    return (tag, tag + timedelta(days=1)) if tag else None


def datum_anzeigen(d: date) -> str:
    """z. B. 'Di 03.11.2026'"""
    return f"{KUERZEL[d.weekday()]} {d:%d.%m.%Y}"
