"""Akte oder weiteres Verfahren aus Dokument: das erkannte Rubrum prüfen lassen und übernehmen.

Ablauf: ``vorschau`` liest das Rubrum (mit Fundstellen) und sucht zu jeder Partei vorhandene Einträge im
Beteiligtenverzeichnis, damit keine Dubletten entstehen. Die Oberfläche zeigt alles zur Prüfung; erst
``uebernehmen`` trägt die bestätigte Auswahl in eine neu angelegte Akte ein.

Für eine bestehende Akte (etwa das Klageverfahren nach dem Mahnverfahren) gleicht ``mit_akte_abgleichen`` die
Vorschau mit den Beteiligten der Akte ab; ``verfahren_uebernehmen`` trägt das Verfahren und nur die neuen
Beteiligten ein.
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
    _parteien_eintragen(con, akte_id, auswahl.get("parteien", []), eigene_seite)
    if v.get("art"):
        felder = ("art", "instanz", "gericht", "spruchkoerper", "aktenzeichen")
        verfahren.speichern(con, akte_id, {k: v[k] for k in felder if k in v}, gericht_daten=v.get("gericht_anschrift"))
    return stammdaten.stammdaten(con, akte_id)


def _parteien_eintragen(con: sqlite3.Connection, akte_id: int, parteien: list[dict], eigene_seite: str) -> None:
    """Partei auf der eigenen Seite = Mandant, sonst Gegner; dazu die gegnerischen Bevollmächtigten. Was laut
    Vorschau schon in der Akte steht (``in_akte``), wird nicht noch einmal eingetragen."""
    for p in parteien:
        if not p.get("uebernehmen", True) and not p.get("in_akte"):
            continue  # abgewählt; bei Parteien, die schon in der Akte stehen, zählen noch die Bevollmächtigten
        eigen = p["seite"] == eigene_seite
        if p.get("uebernehmen", True) and not p.get("in_akte"):
            if eigen and p.get("eigene_organisation_id"):
                stammdaten.beteiligung_hinzufuegen(con, akte_id, "mandant",
                                                   eigene_organisation_id=int(p["eigene_organisation_id"]))
            else:
                bid = _beteiligter(con, p["art"], p["daten"], p.get("beteiligter_id"), p.get("vertreter"))
                try:
                    stammdaten.beteiligung_hinzufuegen(con, akte_id, "mandant" if eigen else "gegner",
                                                       beteiligter_id=bid)
                except ValueError:
                    pass  # im Verzeichnis gewählter Eintrag steht in dieser Rolle schon in der Akte
        b = p.get("bevollmaechtigte")
        if b and not eigen and b.get("uebernehmen", True) and not b.get("in_akte"):
            bid = _beteiligter(con, "organisation", b["daten"], b.get("beteiligter_id"))
            try:
                stammdaten.beteiligung_hinzufuegen(con, akte_id, "bevollmaechtigter_gegner", beteiligter_id=bid,
                                                   aktenzeichen=b.get("zeichen", ""))
            except ValueError:
                pass  # dieselbe Kanzlei vertritt mehrere Gegner: einmal genügt


_GEGENSEITE = {"aktiv": "passiv", "passiv": "aktiv"}


def _in_akte(akte_beteiligte: list[dict], name: str, rollen: tuple[str, ...]) -> dict | None:
    return next(({"rolle": b["rolle"], "rolle_text": b["rolle_text"], "name": b["name"]} for b in akte_beteiligte
                 if b["rolle"] in rollen and _gleich(name, b["name"])), None)


def mit_akte_abgleichen(con: sqlite3.Connection, akte_id: int, r: dict) -> dict:
    """Ergänzt eine ``vorschau`` um den Stand der Akte: welche Parteien und Bevollmächtigten schon eingetragen sind,
    welche Seite wir laut Akte vertreten, ob das erkannte Verfahren schon in der Akte steht und welche Verfahren noch
    laufen (zum Abschließen, etwa das Mahnverfahren nach der Abgabe)."""
    akte_beteiligte = stammdaten.beteiligungen(con, akte_id)
    seite_laut_akte = None
    for p in r["parteien"]:
        p["in_akte"] = _in_akte(akte_beteiligte, p["name"], ("mandant", "gegner"))
        if p["in_akte"] and seite_laut_akte is None:
            mandant = p["in_akte"]["rolle"] == "mandant"
            seite_laut_akte = {"wert": p["seite"] if mandant else _GEGENSEITE[p["seite"]],
                               "grund": f"{p['in_akte']['name']} ist in dieser Akte "
                                        f"{'Mandant' if mandant else 'Gegner'}."}
        b = p.get("bevollmaechtigte")
        if b:
            b["in_akte"] = _in_akte(akte_beteiligte, b["name"], ("bevollmaechtigter_gegner",))
    # Die Akte weiß es sicherer als die Namen der Bevollmächtigten.
    r["eigene_seite"] = seite_laut_akte or r["eigene_seite"]
    # Gegenstand und Streitwert gehören zur Akte, nicht zum Verfahren.
    # Fehlende Anschriften zählen nur bei neuen Parteien.
    bekannt = r["parteien"] and all(p["in_akte"] for p in r["parteien"])
    r["hinweise"] = [h for h in r["hinweise"] if not h.startswith(("Kein Gegenstand", "Kein Streitwert"))
                     and not (bekannt and h.startswith("Nur das Kurzrubrum"))]
    alle = verfahren.liste(con, akte_id)
    az = beteiligte.schluessel((r.get("aktenzeichen") or {}).get("wert", ""))
    r["verfahren_vorhanden"] = next(({"id": v["id"], "bezeichnung": v["bezeichnung"]} for v in alle
                                     if az and beteiligte.schluessel(v.get("aktenzeichen") or "") == az), None)
    r["laufende_verfahren"] = [{"id": v["id"], "bezeichnung": v["bezeichnung"], "art": v["art"]}
                               for v in alle if v["status"] == "laufend"]
    return r


def verfahren_uebernehmen(con: sqlite3.Connection, akte_id: int, auswahl: dict) -> list[dict]:
    """Trägt ein weiteres Verfahren aus der bestätigten Auswahl in eine bestehende Akte ein: das Verfahren mit Gericht,
    dazu die angehakten Parteien und gegnerischen Bevollmächtigten, die noch nicht in der Akte stehen. Auf Wunsch
    werden bisherige Verfahren als abgeschlossen markiert (Ende = Beginn des neuen, sonst leer).

    Mit ``verfahren_id`` wird stattdessen ein vorhandenes Verfahren ergänzt (etwa um den Spruchkörper aus einer
    späteren Verfügung); leere Felder der Auswahl lassen dabei Vorhandenes stehen."""
    v = auswahl.get("verfahren") or {}
    if v.get("art") not in verfahren.ARTEN:
        raise ValueError("Bitte die Art des Verfahrens wählen.")
    parteien = [p for p in auswahl.get("parteien", []) if p.get("uebernehmen", True)
                or (p.get("bevollmaechtigte") or {}).get("uebernehmen")]
    if parteien and auswahl.get("eigene_seite") not in ("aktiv", "passiv"):
        raise ValueError("Bitte angeben, welche Seite wir vertreten.")
    _parteien_eintragen(con, akte_id, parteien, auswahl.get("eigene_seite", ""))
    felder = ("art", "instanz", "gericht", "spruchkoerper", "aktenzeichen", "beginn")
    ergaenzen = auswahl.get("verfahren_id")
    daten = {k: v[k] for k in felder if k in v and (v[k] or not ergaenzen)}
    verfahren.speichern(con, akte_id, daten, int(ergaenzen) if ergaenzen else None,
                        gericht_daten=v.get("gericht_anschrift"))
    laufend = {x["id"] for x in verfahren.liste(con, akte_id) if x["status"] == "laufend"}
    for vid in auswahl.get("abschliessen", []):
        if int(vid) in laufend and int(vid) != ergaenzen:
            verfahren.speichern(con, akte_id, {"status": "abgeschlossen", "ende": v.get("beginn") or ""}, int(vid))
    return verfahren.liste(con, akte_id)
