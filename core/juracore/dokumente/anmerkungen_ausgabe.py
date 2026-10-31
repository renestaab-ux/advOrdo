"""Markierungen, Kommentare und Lesezeichen einer Akte ausgeben: Word, PDF, Excel, Markdown, Text und Drucken.

Ausgegeben wird, was die App im Reiter „Anmerkungen“ gerade zeigt: Die App schickt die sichtbaren Einträge in
ihrer Ordnung (Ordner und Reihenfolge wie dort), dazu in Worten, wie gefiltert ist. Jeder Eintrag nennt seine
Fundstelle (Dokument, Seite, Rn.). Stellen, die nach einer Änderung des Dokuments nicht mehr im Text stehen,
bleiben drin und heißen so, damit der Ausdruck nicht belastbarer wirkt als die Anmerkung in der App.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from .. import ausgabe
from ..ausgabe import Absatz, Beleg, Bericht, Eintrag, Tabelle, Ueberschrift
from ..ki import export as ki_export
from . import anmerkungen, lesezeichen

GLIEDERUNGEN = {"ordner": "nach Ordnern", "dokumente": "nach Dokumenten"}
STIL_TEXT = {"unterstrichen": "unterstrichen", "durchgestrichen": "durchgestrichen"}
VERLOREN = "Stelle nicht mehr im Text"

HINWEIS = (
    "Fundstellen nach dem heutigen Stand der Dokumente in der Akte. „Stelle nicht mehr im Text“ heißt: Der "
    "markierte Wortlaut steht nach einer Änderung des Dokuments nicht mehr dort; Wortlaut und Kommentar sind "
    "wie angelegt wiedergegeben."
)


def _ort(e: dict) -> str:
    """„Klageschrift, S. 3, Rn. 12“; bei verlorenen Stellen die zuletzt bekannte Seite."""
    if e["status"] == "nicht_gefunden":
        return f"{e['dokument']} – {VERLOREN}" + (f" (zuletzt S. {e['seite']})" if e.get("seite") else "")
    teile = []
    if e.get("seite") is not None:
        teile.append(f"S. {e['seite']}")
    if e.get("rn") is not None:
        teile.append(f"Rn. {e['rn']}")
    if not teile and e.get("abschnitt") is not None:
        teile.append(f"Abschn. {e['abschnitt']}")
    return ", ".join([e["dokument"], *teile])


def _kommentar(text: str | None) -> list[str]:
    """Kommentar (Markdown) als Zeilen: Fett- und Kursivzeichen weg, Leerzeilen zusammengefasst."""
    if not text:
        return []
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    return [" ".join(z.split()) for z in text.splitlines() if z.strip()]


def _zitat(text: str | None) -> str:
    return " ".join((text or "").split())


def _eintraege(con: sqlite3.Connection, akte_id: int, ordner: list[dict]) -> list[tuple[int | None, str, dict]]:
    """Die gewünschten Einträge als (Ordner, Art, Daten), in der übergebenen Ordnung; Fremdes wird abgelehnt."""
    markierungen = {a["id"]: a for a in anmerkungen.liste(con, akte_id=akte_id) if a["art"] == "markierung"}
    lz = {z["id"]: z for z in lesezeichen.liste(con, akte_id=akte_id)["lesezeichen"]}
    aus = []
    for g in ordner:
        for e in g.get("eintraege", []):
            quelle = markierungen if e["art"] == "markierung" else lz if e["art"] == "lesezeichen" else None
            if quelle is None:
                raise ValueError(f"Unbekannte Art: {e['art']!r}")
            if e["id"] not in quelle:
                raise LookupError(f"Eintrag {e['art']} {e['id']} gehört nicht zu dieser Akte.")
            aus.append((g.get("id"), e["art"], quelle[e["id"]]))
    return aus


def _eintrag(art: str, e: dict, bedeutungen: dict[str, str], nummer: str, mit_dokument: bool) -> Eintrag:
    ort = _ort(e) if mit_dokument else _ort({**e, "dokument": ""}).lstrip(", –").strip() or "ohne Seitenangabe"
    if art == "lesezeichen":
        return Eintrag(f"Lesezeichen: {e['titel']}", nummer, ["nicht mehr im Text"] if e["status"] ==
                       "nicht_gefunden" else [], [], [Beleg(ort)], kompakt=True)
    marken = [bedeutungen.get(e["farbe"], e["farbe"])]
    if e["stil"] in STIL_TEXT:
        marken.append(STIL_TEXT[e["stil"]])
    if e["status"] == "nicht_gefunden":
        marken.append("nicht mehr im Text")
    zeilen = _kommentar(e.get("kommentar"))
    if zeilen:
        zeilen[0] = f"Kommentar: {zeilen[0]}"
    return Eintrag(f"„{_zitat(e['zitat'])}“", nummer, marken, zeilen, [Beleg(ort)], kompakt=True)


def _zeile(nr: int, ordner: str, art: str, e: dict, bedeutungen: dict[str, str]) -> list:
    lesezeichen_ = art == "lesezeichen"
    return [
        nr, "Lesezeichen" if lesezeichen_ else "Markierung", ordner, e["dokument"],
        e.get("seite"), e.get("rn") if e["status"] == "gefunden" else None,
        "" if lesezeichen_ else bedeutungen.get(e["farbe"], e["farbe"]),
        "" if lesezeichen_ else STIL_TEXT.get(e["stil"], "Fläche"),
        e["titel"] if lesezeichen_ else "", _zitat(e.get("zitat")),
        "" if lesezeichen_ else "\n".join(_kommentar(e.get("kommentar"))),
        "gefunden" if e["status"] == "gefunden" else VERLOREN,
    ]


_SPALTEN = ["Nr.", "Art", "Ordner", "Dokument", "Seite", "Rn.", "Bedeutung", "Darstellung", "Titel",
            "Wortlaut", "Kommentar", "Stelle"]
_BREITEN = [5, 12, 20, 32, 7, 7, 12, 14, 30, 70, 60, 22]


def _lesereihenfolge(con: sqlite3.Connection, akte_id: int) -> dict[int, int]:
    """Dokumente wie in der Akte geordnet (Datum, dann Anlage)."""
    return {z["id"]: i for i, z in enumerate(con.execute(
        "SELECT id FROM dokument WHERE akte_id = ? ORDER BY datum, id", (akte_id,)))}


def bericht(con: sqlite3.Connection, akte_id: int, ordner: list[dict], gliederung: str = "ordner",
            auswahl: str | None = None, jetzt: datetime | None = None) -> Bericht:
    """``ordner`` wie ``lesezeichen.anordnen`` ([{id, eintraege: [{art, id}]}]), nur die auszugebenden Einträge."""
    if gliederung not in GLIEDERUNGEN:
        raise ValueError(f"Unbekannte Gliederung: {gliederung!r}")
    eintraege = _eintraege(con, akte_id, ordner)
    if not eintraege:
        raise ValueError("Es ist nichts ausgewählt, was ausgegeben werden könnte.")
    bedeutungen = anmerkungen.bedeutungen(con)
    namen = {o["id"]: o["name"] for o in lesezeichen.liste(con, akte_id=akte_id)["ordner"]}
    jetzt = jetzt or datetime.now().astimezone()
    kopf = ki_export.aktenkopf(con, akte_id, [], jetzt)
    n_mark = sum(1 for _, art, _e in eintraege if art == "markierung")
    n_lz = len(eintraege) - n_mark
    n_komm = sum(1 for _, art, e in eintraege if art == "markierung" and e.get("kommentar"))
    umfang = ", ".join(t for t in (
        f"{n_mark} {'Markierung' if n_mark == 1 else 'Markierungen'}" + (f" ({n_komm} mit Kommentar)" if n_komm
                                                                          else "") if n_mark else "",
        f"{n_lz} Lesezeichen" if n_lz else "") if t)
    kopf.zeilen[-1:-1] = [("Umfang", umfang), ("Gliederung", GLIEDERUNGEN[gliederung])]
    if auswahl:
        kopf.zeilen.insert(-1, ("Auswahl", auswahl))
    if n_mark:
        farben = [f for f in anmerkungen.FARBEN if any(art == "markierung" and e["farbe"] == f
                                                        for _, art, e in eintraege)]
        kopf.zeilen.insert(-1, ("Farben", "; ".join(f"{f.replace('ue', 'ü').capitalize()} = {bedeutungen[f]}"
                                                     for f in farben)))
    b = Bericht(f"Anmerkungen: {kopf.zeilen[0][1]}", [kopf, Absatz(HINWEIS, leise=True)])

    gruppen: list[tuple[str, list[tuple[int | None, str, dict]]]] = []
    if gliederung == "ordner":
        for oid, art, e in eintraege:
            name = namen.get(oid, "Ohne Ordner") if oid is not None else "Ohne Ordner"
            if not gruppen or gruppen[-1][0] != name:
                gruppen.append((name, []))
            gruppen[-1][1].append((oid, art, e))
    else:
        reihe = _lesereihenfolge(con, akte_id)
        sortiert = sorted(eintraege, key=lambda x: (reihe.get(x[2]["dokument_id"], 0), x[2]["status"] != "gefunden",
                                                    x[2].get("start") or 0, x[1] != "lesezeichen"))
        for t in sortiert:
            if not gruppen or gruppen[-1][0] != t[2]["dokument"]:
                gruppen.append((t[2]["dokument"], []))
            gruppen[-1][1].append(t)

    zeilen = []
    nr = 0
    for name, teil in gruppen:
        if len(gruppen) > 1 or gliederung == "dokumente" or name != "Ohne Ordner":
            b.bausteine.append(Ueberschrift(name))
        for oid, art, e in teil:
            nr += 1
            b.bausteine.append(_eintrag(art, e, bedeutungen, f"{nr}.", gliederung == "ordner"))
            zeilen.append(_zeile(nr, namen.get(oid, "") if oid is not None else "", art, e, bedeutungen))
    b.tabellen.append(Tabelle("Anmerkungen", _SPALTEN, zeilen, _BREITEN))
    return b


def dateiname(con: sqlite3.Connection, akte_id: int, jetzt: datetime | None = None) -> str:
    return ki_export.dateiname(con, akte_id, jetzt, vorne="Anmerkungen")


def schreiben(con: sqlite3.Connection, akte_id: int, ordner: list[dict], format: str, pfad: str | Path,
              gliederung: str = "ordner", auswahl: str | None = None) -> dict:
    if format not in ausgabe.FORMATE:
        raise ValueError(f"Unbekanntes Format: {format!r}")
    ziel = Path(pfad)
    if ziel.suffix.lower() != f".{format}":
        ziel = ziel.with_name(ziel.name + f".{format}")
    daten = ausgabe.schreiben(bericht(con, akte_id, ordner, gliederung, auswahl), format)
    ziel.write_bytes(daten)
    return {"pfad": str(ziel), "format": format, "groesse": len(daten)}


def druckansicht(con: sqlite3.Connection, akte_id: int, ordner: list[dict], gliederung: str = "ordner",
                 auswahl: str | None = None) -> dict:
    from ..ausgabe import html

    b = bericht(con, akte_id, ordner, gliederung, auswahl)
    return {"titel": b.titel, "html": html.fragment(b), "stil": html.STIL}
