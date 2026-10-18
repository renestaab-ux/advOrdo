"""Gesetzliche Feiertage je Bundesland, für § 193 BGB (übernommen aus JuraBox Lite, um Einführungsjahre ergänzt).

Nur landesweite Feiertage. Regionale Feiertage (Mariä Himmelfahrt in Teilen Bayerns, Augsburger Friedensfest,
Fronleichnam in Teilen Sachsens und Thüringens) sind nicht enthalten; Mariä Himmelfahrt in Bayern lässt sich zuschalten.
"""

from __future__ import annotations

from datetime import date, timedelta

LAENDER = {
    "BW": "Baden-Württemberg", "BY": "Bayern", "BE": "Berlin", "BB": "Brandenburg", "HB": "Bremen",
    "HH": "Hamburg", "HE": "Hessen", "MV": "Mecklenburg-Vorpommern", "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen", "RP": "Rheinland-Pfalz", "SL": "Saarland", "SN": "Sachsen",
    "ST": "Sachsen-Anhalt", "SH": "Schleswig-Holstein", "TH": "Thüringen",
}
STAND = "28.09.2026"


def ostersonntag(jahr: int) -> date:
    """Gaußsche Osterformel (gregorianisch, in der Fassung von Meeus/Jones/Butcher)."""
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    monat, tag = divmod(h + l_ - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


def _buss_und_bettag(jahr: int) -> date:
    """Mittwoch vor dem 23. November."""
    tag = date(jahr, 11, 22)
    while tag.weekday() != 2:
        tag -= timedelta(days=1)
    return tag


def feiertage(jahr: int, land: str, maria_himmelfahrt_bayern: bool = False) -> dict[date, str]:
    if land not in LAENDER:
        raise ValueError(f"Unbekanntes Bundesland: {land}")
    ostern = ostersonntag(jahr)
    t: dict[date, str] = {
        date(jahr, 1, 1): "Neujahr",
        ostern - timedelta(days=2): "Karfreitag",
        ostern + timedelta(days=1): "Ostermontag",
        date(jahr, 5, 1): "Tag der Arbeit",
        ostern + timedelta(days=39): "Christi Himmelfahrt",
        ostern + timedelta(days=50): "Pfingstmontag",
        date(jahr, 10, 3): "Tag der Deutschen Einheit",
        date(jahr, 12, 25): "1. Weihnachtstag",
        date(jahr, 12, 26): "2. Weihnachtstag",
    }

    def dazu(laender: str, tag: date, name: str, ab: int = 0):
        if land in laender.split() and jahr >= ab:
            t[tag] = name

    dazu("BW BY ST", date(jahr, 1, 6), "Heilige Drei Könige")
    dazu("BE", date(jahr, 3, 8), "Internationaler Frauentag", ab=2019)
    dazu("MV", date(jahr, 3, 8), "Internationaler Frauentag", ab=2023)
    dazu("BW BY HE NW RP SL", ostern + timedelta(days=60), "Fronleichnam")
    dazu("SL", date(jahr, 8, 15), "Mariä Himmelfahrt")
    if maria_himmelfahrt_bayern:
        dazu("BY", date(jahr, 8, 15), "Mariä Himmelfahrt")
    dazu("TH", date(jahr, 9, 20), "Weltkindertag", ab=2019)
    dazu("BB MV SN ST TH", date(jahr, 10, 31), "Reformationstag")
    dazu("HB HH NI SH", date(jahr, 10, 31), "Reformationstag", ab=2018)
    if jahr == 2017:
        t[date(jahr, 10, 31)] = "Reformationstag (500. Jahrestag)"
    dazu("BW BY NW RP SL", date(jahr, 11, 1), "Allerheiligen")
    dazu("SN", _buss_und_bettag(jahr), "Buß- und Bettag")
    return t
