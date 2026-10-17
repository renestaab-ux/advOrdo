"""Fristenrechner nach §§ 187, 188, 193 BGB (übernommen aus JuraBox Lite). Nur Vorwärtsfristen."""

from __future__ import annotations

from datetime import date, timedelta

from . import feiertage as ft
from .verzugszinsen import plus_monate

EINHEITEN = ("tage", "wochen", "monate", "jahre")
WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def berechne(bezugstag: date, anzahl: int, einheit: str, beginn: str = "ereignis", paragraf_193: bool = True,
             land: str = "BY", maria_himmelfahrt_bayern: bool = False) -> dict:
    """``beginn``: "ereignis" (§ 187 Abs. 1, Bezugstag zählt nicht mit) oder "tagesbeginn" (§ 187 Abs. 2)."""
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

    ende, gruende = rechnerisch, []
    if paragraf_193:
        while True:
            frei = ft.feiertage(ende.year, land, maria_himmelfahrt_bayern).get(ende)
            if ende.weekday() >= 5:
                gruende.append(WOCHENTAGE[ende.weekday()])
            elif frei:
                gruende.append(frei)
            else:
                break
            ende += timedelta(days=1)

    normen = ["§ 187 Abs. 1 BGB" if beginn == "ereignis" else "§ 187 Abs. 2 BGB",
              "§ 188 Abs. 1 BGB" if einheit == "tage" else "§ 188 Abs. 2 BGB"]
    if einheit in ("monate", "jahre") and voll.day != bezugstag.day:
        normen.append("§ 188 Abs. 3 BGB")
    if gruende:
        normen.append("§ 193 BGB")
    return {
        "fristbeginn": fristbeginn.isoformat(),
        "rechnerisches_ende": rechnerisch.isoformat(),
        "ende": ende.isoformat(),
        "wochentag": WOCHENTAGE[ende.weekday()],
        "verschoben": bool(gruende),
        "grund": ", ".join(gruende),
        "grundlagen": normen,
        "land": ft.LAENDER[land],
        "feiertage_stand": ft.STAND,
    }


def aus_params(p: dict) -> dict:
    return berechne(date.fromisoformat(p["bezugstag"]), int(p["anzahl"]), p.get("einheit", "tage"),
                    p.get("beginn", "ereignis"), bool(p.get("paragraf_193", True)), p.get("land", "BY"),
                    bool(p.get("maria_himmelfahrt_bayern", False)))
