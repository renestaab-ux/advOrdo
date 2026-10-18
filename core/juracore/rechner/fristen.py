"""Fristenrechner nach §§ 187, 188, 193 BGB (übernommen aus JuraBox Lite). Nur Vorwärtsfristen."""

from __future__ import annotations

from datetime import date, timedelta

from . import feiertage as ft
from .verzugszinsen import plus_monate

EINHEITEN = ("tage", "wochen", "monate", "jahre")
WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def berechne(bezugstag: date, anzahl: int, einheit: str, beginn: str = "ereignis", paragraf_193: bool = True,
             land: str = "BY", maria_himmelfahrt_bayern: bool = True) -> dict:
    """``beginn``: "ereignis" (§ 187 Abs. 1, Bezugstag zählt nicht mit) oder "tagesbeginn" (§ 187 Abs. 2).

    ``maria_himmelfahrt_bayern``: Der 15. August ist in Bayern nur in Gemeinden mit überwiegend katholischer
    Bevölkerung Feiertag (das ist die Mehrzahl der Gemeinden); hängt das Fristende davon ab, nennt ein Hinweis beide
    Ergebnisse."""
    if einheit not in EINHEITEN:
        raise ValueError(f"Unbekannte Einheit: {einheit}")
    if beginn not in ("ereignis", "tagesbeginn"):
        raise ValueError(f"Unbekannte Beginnart: {beginn}")
    if anzahl < 1:
        raise ValueError("Die Frist muss mindestens 1 betragen.")

    fristbeginn = bezugstag + timedelta(days=1) if beginn == "ereignis" else bezugstag
    if einheit == "tage":
        voll = bezugstag + timedelta(days=anzahl)
    elif einheit == "wochen":
        voll = bezugstag + timedelta(weeks=anzahl)
    else:
        voll = plus_monate(bezugstag, anzahl * (12 if einheit == "jahre" else 1))
    rechnerisch = voll if beginn == "ereignis" else voll - timedelta(days=1)

    ende, gruende = _verschiebe(rechnerisch, land, maria_himmelfahrt_bayern) if paragraf_193 else (rechnerisch, [])
    hinweise = []
    if paragraf_193 and land == "BY":
        anders, _ = _verschiebe(rechnerisch, land, not maria_himmelfahrt_bayern)
        if anders != ende:
            wo = ("in Gemeinden ohne überwiegend katholische Bevölkerung" if maria_himmelfahrt_bayern
                  else "in Gemeinden mit überwiegend katholischer Bevölkerung (15. August Feiertag)")
            hinweise.append(f"Achtung: {wo} endet die Frist am {WOCHENTAGE[anders.weekday()]}, {anders:%d.%m.%Y}. "
                            "Maßgeblich ist der Ort, an dem die Leistung zu bewirken bzw. die Erklärung abzugeben ist.")

    normen = ["§ 187 Abs. 1 BGB" if beginn == "ereignis" else "§ 187 Abs. 2 BGB",
              "§ 188 Abs. 1 BGB" if einheit == "tage" else "§ 188 Abs. 2 BGB"]
    if einheit in ("monate", "jahre") and voll.day != bezugstag.day:
        normen.append("§ 188 Abs. 3 BGB")
    if gruende:
        normen.append("§ 193 BGB")
    return {
        "bezugstag": bezugstag.isoformat(),
        "wochentag_bezugstag": WOCHENTAGE[bezugstag.weekday()],
        "fristbeginn": fristbeginn.isoformat(),
        "wochentag_fristbeginn": WOCHENTAGE[fristbeginn.weekday()],
        "rechnerisches_ende": rechnerisch.isoformat(),
        "wochentag_rechnerisch": WOCHENTAGE[rechnerisch.weekday()],
        "ende": ende.isoformat(),
        "wochentag": WOCHENTAGE[ende.weekday()],
        "hinweise": hinweise,
        "verschoben": bool(gruende),
        "grund": ", ".join(gruende),
        "grundlagen": normen,
        "land": ft.LAENDER[land],
        "feiertage_stand": ft.STAND,
    }


def _verschiebe(ende: date, land: str, maria: bool) -> tuple[date, list[str]]:
    """§ 193 BGB: vom Samstag, Sonntag oder Feiertag auf den nächsten Werktag."""
    gruende = []
    while True:
        frei = ft.feiertage(ende.year, land, maria).get(ende)
        if ende.weekday() >= 5:
            gruende.append(WOCHENTAGE[ende.weekday()])
        elif frei:
            gruende.append(frei)
        else:
            return ende, gruende
        ende += timedelta(days=1)


def aus_params(p: dict) -> dict:
    return berechne(date.fromisoformat(p["bezugstag"]), int(p["anzahl"]), p.get("einheit", "tage"),
                    p.get("beginn", "ereignis"), bool(p.get("paragraf_193", True)), p.get("land", "BY"),
                    bool(p.get("maria_himmelfahrt_bayern", True)))
