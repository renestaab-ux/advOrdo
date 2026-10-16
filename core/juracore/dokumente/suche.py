"""Volltextsuche über alle Akten, nach dem Vorbild von „PDF Search“: Treffer je Dokument und Seite.

Der Index (`abschnitt_fts`, SQLite FTS5) enthält den aufbereiteten Text jedes Abschnitts und wird über Trigger
mit der Tabelle `abschnitt` mitgeführt. Gesucht wird ohne Rücksicht auf Groß- und Kleinschreibung und diakritische
Zeichen; die Seite eines Treffers ergibt sich aus der Position im Abschnitt (`seitenwechsel`).
"""

from __future__ import annotations

import json
import re
import sqlite3
import time

from . import akte

# Markierungen, die FTS5 um jeden Treffer im Text setzt.
_AUF, _ZU = "\x01", "\x02"
_UMFELD = 70  # Zeichen vor und nach dem ersten Treffer im Ausschnitt
MAX_ABSCHNITTE = 5000


def abfrage(suchtext: str) -> str:
    """Nutzereingabe als sichere FTS5-Abfrage: Wörter (alle müssen vorkommen), „genaue Wortfolge“, Wortanfang*."""
    teile: list[str] = []
    for phrase, wort in re.findall(r'"([^"]*)"?|(\S+)', suchtext):
        if phrase:
            woerter = _woerter(phrase)
            if woerter:
                teile.append('"' + " ".join(woerter) + '"')
            continue
        praefix = wort.endswith("*")
        for i, w in enumerate(woerter := _woerter(wort)):
            teile.append(f'"{w}"*' if praefix and i == len(woerter) - 1 else f'"{w}"')
    return " ".join(teile)


def _woerter(text: str) -> list[str]:
    return "".join(c if c.isalnum() else " " for c in text).split()


def suche(con: sqlite3.Connection, suchtext: str, akte_id: int | None = None) -> dict:
    """Treffer gruppiert nach Dokument und Seite; Rang 1 ist die relevanteste Seite (BM25)."""
    beginn = time.perf_counter()
    fts = abfrage(suchtext)
    if not fts:
        return {"dokumente": [], "seiten": 0, "treffer": 0, "dauer_ms": 0, "gekuerzt": False}
    zeilen = con.execute(
        f"""SELECT a.dokument_id, a.nr, a.seite, a.rn, a.seitenwechsel,
                  highlight(abschnitt_fts, 0, '{_AUF}', '{_ZU}') AS markiert, bm25(abschnitt_fts) AS gewicht
           FROM abschnitt_fts
           JOIN abschnitt a ON a.id = abschnitt_fts.rowid
           JOIN dokument d ON d.id = a.dokument_id
           WHERE abschnitt_fts MATCH ? AND (? IS NULL OR d.akte_id = ?)
           ORDER BY gewicht
           LIMIT ?""",
        (fts, akte_id, akte_id, MAX_ABSCHNITTE + 1),
    ).fetchall()
    gekuerzt = len(zeilen) > MAX_ABSCHNITTE

    # Fundstelle ist die Seite; Dokumente ohne Seiten (Word, Text) werden nach Abschnitten gezählt.
    seiten: dict[tuple, dict] = {}
    for z in sorted(zeilen[:MAX_ABSCHNITTE], key=lambda z: (z["dokument_id"], z["nr"])):
        wechsel = json.loads(z["seitenwechsel"])
        for start, ende, text, begriff in _treffer(z["markiert"]):
            seite = akte._seite_an(z["seite"], wechsel, start)
            schluessel = (z["dokument_id"], seite) if seite is not None else (z["dokument_id"], None, z["nr"])
            eintrag = seiten.get(schluessel)
            if eintrag is None:
                eintrag = seiten[schluessel] = {
                    "seite": seite, "abschnitt": z["nr"], "rn": z["rn"], "treffer": 0, "gewicht": 0.0,
                    "ausschnitt": _ausschnitt(text, start, ende), "begriffe": [],
                }
            eintrag["treffer"] += 1
            eintrag["gewicht"] = min(eintrag["gewicht"], z["gewicht"])
            if begriff not in eintrag["begriffe"]:
                eintrag["begriffe"].append(begriff)

    # Rang über alle Fundstellen (BM25, bei Gleichstand mehr Treffer zuerst); Dokumente nach ihrer besten Fundstelle.
    rangfolge = sorted(seiten.items(), key=lambda s: (s[1]["gewicht"], -s[1]["treffer"], s[0][0], s[1]["abschnitt"]))
    dokumente: dict[int, list[dict]] = {}
    for rang, (schluessel, eintrag) in enumerate(rangfolge, start=1):
        eintrag["rang"] = rang
        del eintrag["gewicht"]
        dokumente.setdefault(schluessel[0], []).append(eintrag)

    ergebnis = []
    if dokumente:
        info = {
            d["id"]: dict(d)
            for d in con.execute(
                f"""SELECT d.id, d.dateiname, d.format, d.seiten, d.akte_id, k.name AS akte
                    FROM dokument d JOIN akte k ON k.id = d.akte_id
                    WHERE d.id IN ({",".join("?" * len(dokumente))})""",
                list(dokumente),
            )
        }
        for dokument_id, treffer_seiten in dokumente.items():
            treffer_seiten.sort(key=lambda s: (s["seite"] or 0, s["abschnitt"]))
            ergebnis.append({
                **info[dokument_id],
                "treffer": sum(s["treffer"] for s in treffer_seiten),
                "rang": min(s["rang"] for s in treffer_seiten),
                "fundstellen": treffer_seiten,
            })
        ergebnis.sort(key=lambda d: d["rang"])
    return {
        "dokumente": ergebnis,
        "seiten": len(seiten),
        "treffer": sum(d["treffer"] for d in ergebnis),
        "dauer_ms": round((time.perf_counter() - beginn) * 1000),
        "gekuerzt": gekuerzt,
    }


def _treffer(markiert: str):
    """(Start, Ende, Text ohne Markierungen, gefundenes Wort) für jede Markierung im Abschnitt."""
    text = markiert.replace(_AUF, "").replace(_ZU, "")
    versatz = 0
    for m in re.finditer(f"{_AUF}([^{_ZU}]*){_ZU}", markiert):
        start = m.start() - versatz
        versatz += 2
        yield start, start + len(m.group(1)), text, m.group(1)


def _ausschnitt(text: str, start: int, ende: int) -> dict:
    von = max(0, start - _UMFELD)
    bis = min(len(text), ende + _UMFELD)
    if von > 0 and (leer := text.find(" ", von, start)) != -1:
        von = leer + 1
    if bis < len(text) and (leer := text.rfind(" ", ende, bis)) != -1:
        bis = leer
    return {
        "vor": ("… " if von > 0 else "") + text[von:start],
        "treffer": text[start:ende],
        "nach": text[ende:bis] + (" …" if bis < len(text) else ""),
    }
