"""Akte aus Dokument anlegen: das erkannte Rubrum prüfen lassen und übernehmen.

Ablauf: ``vorschau`` liest das Rubrum (mit Fundstellen) und sucht zu jeder Partei vorhandene Einträge im
Beteiligtenverzeichnis, damit keine Dubletten entstehen. Die Oberfläche zeigt alles zur Prüfung; erst
``uebernehmen`` trägt die bestätigte Auswahl in eine neu angelegte Akte ein.
"""

from __future__ import annotations

import sqlite3

from . import beteiligte, rubrum, stammdaten, verfahren

_EIGENE_ROLLE = {
    ("aktiv", True): "Prozessbevollmächtigter des Klägers",
    ("passiv", True): "Prozessbevollmächtigter des Beklagten",
}


def _treffer(con: sqlite3.Connection, art: str, daten: dict) -> list[dict]:
    try:
        return [{"id": t["id"], "name": t["name"], "stufe": t["stufe"]} for t in
                beteiligte.aehnliche(con, art, daten)[:3]]
    except ValueError:
        return []


def _gleich(a: str, b: str) -> bool:
    return beteiligte.aehnlichkeit(beteiligte.schluessel(a), beteiligte.schluessel(b)) is not None


def vorschau(con: sqlite3.Connection, abschnitte: list[dict], eigene_namen: list[str] | None = None,
             konzerngesellschaften: list[dict] | None = None) -> dict:
    """Erkanntes Rubrum mit Treffern im Verzeichnis und einer Vermutung, welche Seite wir vertreten.

    ``eigene_namen``: Name der eigenen Kanzlei (und beauftragter Kanzleien); stehen sie als Prozessbevollmächtigte
    bei einer Partei, vertreten wir diese Seite. ``konzerngesellschaften`` (Rechtsabteilung): [{"id", "name"}];
    ist eine davon Partei, ist sie Mandantin.
    """
    r = rubrum.erkenne(abschnitte)
    eigene_namen = [n for n in (eigene_namen or []) if n]
    r["eigene_seite"] = None
    for i, p in enumerate(r["parteien"]):
        p["index"] = i
        p["treffer"] = _treffer(con, p["art"], p["daten"])
        p["eigene_organisation_id"] = None
        for k in konzerngesellschaften or []:
            if _gleich(p["name"], k["name"]):
                p["eigene_organisation_id"] = k["id"]
                r["eigene_seite"] = r["eigene_seite"] or {
                    "wert": p["seite"], "grund": f"{p['name']} ist eine Konzerngesellschaft aus „Eigene Daten“."}
        b = p.get("bevollmaechtigte")
        if b:
            b["treffer"] = _treffer(con, "organisation", b["daten"])
            b["eigene"] = any(_gleich(b["name"], n) for n in eigene_namen)
            if b["eigene"] and r["eigene_seite"] is None:
                r["eigene_seite"] = {"wert": p["seite"],
                                     "grund": f"{b['name']} ist als Prozessbevollmächtigte genannt."}
    r["aktenzeichen_vorschlag"] = stammdaten.vorschlag(con)["aktenzeichen"]
    return r


def _beteiligter(con: sqlite3.Connection, art: str, daten: dict, beteiligter_id: int | None,
                 vertreter: list[dict] | None = None) -> int:
    if beteiligter_id:
        beteiligte.eintrag(con, int(beteiligter_id))
        return int(beteiligter_id)
    vertreter = [{"funktion": v.get("funktion"), **v["daten"]} for v in (vertreter or []) if v.get("daten")]
    return beteiligte.speichern(con, art, daten, vertreter=vertreter if art == "organisation" else None)["id"]


def uebernehmen(con: sqlite3.Connection, akte_id: int, auswahl: dict) -> dict:
    """Trägt die bestätigte Auswahl in die (neue) Akte ein: Stammdaten, Parteien, gegnerische Bevollmächtigte,
    Verfahren mit Gericht. Partei auf der eigenen Seite = Mandant, sonst Gegner."""
    eigene_seite = auswahl.get("eigene_seite")
    if eigene_seite not in ("aktiv", "passiv"):
        raise ValueError("Bitte angeben, welche Seite wir vertreten.")
    v = auswahl.get("verfahren") or {}
    gerichtlich = bool(v.get("art")) and v.get("art") != "aussergerichtlich"
    daten = {k: auswahl[k] for k in ("gegenstand", "gegenstandswert") if auswahl.get(k)}
    daten["eigene_rolle"] = _EIGENE_ROLLE.get((eigene_seite, gerichtlich), "Außergerichtliche Vertretung")
    stammdaten.speichern(con, akte_id, daten)
    for p in auswahl.get("parteien", []):
        if not p.get("uebernehmen", True):
            continue
        eigen = p["seite"] == eigene_seite
        if eigen and p.get("eigene_organisation_id"):
            stammdaten.beteiligung_hinzufuegen(con, akte_id, "mandant",
                                               eigene_organisation_id=int(p["eigene_organisation_id"]))
        else:
            bid = _beteiligter(con, p["art"], p["daten"], p.get("beteiligter_id"), p.get("vertreter"))
            stammdaten.beteiligung_hinzufuegen(con, akte_id, "mandant" if eigen else "gegner", beteiligter_id=bid)
        b = p.get("bevollmaechtigte")
        if b and not eigen and b.get("uebernehmen", True):
            bid = _beteiligter(con, "organisation", b["daten"], b.get("beteiligter_id"))
            try:
                stammdaten.beteiligung_hinzufuegen(con, akte_id, "bevollmaechtigter_gegner", beteiligter_id=bid,
                                                   aktenzeichen=b.get("zeichen", ""))
            except ValueError:
                pass  # dieselbe Kanzlei vertritt mehrere Gegner: einmal genügt
    if v.get("art"):
        felder = ("art", "instanz", "gericht", "spruchkoerper", "aktenzeichen")
        verfahren.speichern(con, akte_id, {k: v[k] for k in felder if k in v}, gericht_daten=v.get("gericht_anschrift"))
    return stammdaten.stammdaten(con, akte_id)
