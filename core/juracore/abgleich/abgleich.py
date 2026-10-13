"""Abgleich der Dokumente einer Akte: dieselben Angaben nebeneinanderstellen, Abweichungen hervorheben.

Für jedes Merkmal (Kaufpreis, Übergabe, Kilometerstand bei Übergabe …) werden die
Werte aus allen Dokumenten gesammelt, jeweils mit Fundstelle (Dokument, Seite,
Randnummer) und dem Satz, in dem der Wert steht. Passen die Werte nicht
zusammen, ist das eine *mögliche Abweichung*: Ob ein echter Widerspruch vorliegt
oder die Angaben sich auf Verschiedenes beziehen, entscheidet der Mensch anhand
der Fundstellen. Die Einordnung (im selben Dokument, innerhalb einer Partei,
zwischen den Parteien) stützt sich auf die Tags der Dokumente.

Der Abgleich wird bei jeder Anfrage aus den gespeicherten Abschnitten neu
berechnet; er verändert die Akte nicht.
"""

from __future__ import annotations

import json
import re
import sqlite3
from bisect import bisect_right
from itertools import combinations

from ..dokumente import akte
from .angaben import MERKMALE, anzeige, finde_angaben, vereinbar

ABWEICHEND = "abweichend"
UEBEREINSTIMMEND = "uebereinstimmend"
EINZELN = "einzeln"

# Tags, die einen Beteiligten bezeichnen (wie beim Ordner-Import vorgeschlagen).
PARTEIEN = set(akte._BETEILIGTE.values()) | {"Gericht"}

MAX_AUSSCHNITT = 320
_SATZENDE = tuple(".!?:;)\"“»")


def _verbinden(vorher: str, text: str) -> bool:
    """Ob ein Abschnitt den Satz des vorigen fortsetzt ("… setzen wir eine Frist" + "bis zum 07.07.2025.")."""
    vorher = vorher.rstrip()
    return bool(vorher) and not vorher.endswith(_SATZENDE) and text[:1].islower()


def _textfluss(abschnitte: list[sqlite3.Row]) -> tuple[str, list[int]]:
    """Fügt die Abschnitte eines Dokuments zu einem Text zusammen; liefert die Startposition jedes Abschnitts."""
    teile: list[str] = []
    starts: list[int] = []
    laenge = 0
    for a in abschnitte:
        if teile:
            trenner = " " if _verbinden(teile[-1], a["text"]) else "\n\n"
            teile.append(trenner)
            laenge += len(trenner)
        starts.append(laenge)
        teile.append(a["text"])
        laenge += len(a["text"])
    return "".join(teile), starts


def _ausschnitt(text: str, satz_start: int, satz_ende: int, start: int, ende: int) -> dict:
    """Der Satz um den Wert, bei langen Sätzen gekürzt; getrennt in davor, Wert und danach zum Hervorheben."""
    von, bis = satz_start, satz_ende
    if bis - von > MAX_AUSSCHNITT:
        rest = MAX_AUSSCHNITT - (ende - start)
        von = max(satz_start, start - rest * 2 // 3)
        bis = min(satz_ende, ende + rest - (start - von))
    return {
        "davor": ("… " if von > satz_start else "") + re.sub(r"\s+", " ", text[von:start]).lstrip(),
        "wert": re.sub(r"\s+", " ", text[start:ende]),
        "danach": re.sub(r"\s+", " ", text[ende:bis]).rstrip() + (" …" if bis < satz_ende else ""),
    }


def _angaben_im_dokument(con: sqlite3.Connection, dok: sqlite3.Row, parteien: list[str]) -> list[dict]:
    abschnitte = con.execute("SELECT * FROM abschnitt WHERE dokument_id = ? ORDER BY nr", (dok["id"],)).fetchall()
    text, starts = _textfluss(abschnitte)
    ergebnis = []
    for a in finde_angaben(text):
        i = bisect_right(starts, a.start) - 1
        abschnitt = abschnitte[i]
        seite = akte._seite_an(abschnitt["seite"], json.loads(abschnitt["seitenwechsel"]), a.start - starts[i])
        ergebnis.append(
            {
                "merkmal": a.merkmal,
                "titel": a.titel,
                "art": a.art,
                "wert": a.wert,
                "anlage": a.anlage,
                "fundstelle": {
                    "dokument_id": dok["id"],
                    "dateiname": dok["dateiname"],
                    "abschnitt": abschnitt["nr"],
                    "seite": seite,
                    "rn": abschnitt["rn"],
                    "parteien": parteien,
                    "ausschnitt": _ausschnitt(text, a.satz_start, a.satz_ende, a.start, a.ende),
                },
            }
        )
    return ergebnis


def _einordnung(werte: list[dict]) -> list[str]:
    """Wo die unvereinbaren Werte stehen: im selben Dokument, innerhalb einer Partei, zwischen Parteien."""
    einordnung: set[str] = set()
    for a, b in combinations(werte, 2):
        if vereinbar(a["art"], a["wert"], b["art"], b["wert"]):
            continue
        for fa in a["fundstellen"]:
            for fb in b["fundstellen"]:
                if fa["dokument_id"] == fb["dokument_id"]:
                    einordnung.add("im_dokument")
                elif set(fa["parteien"]) & set(fb["parteien"]):
                    einordnung.add("innerhalb_partei")
                elif fa["parteien"] and fb["parteien"]:
                    einordnung.add("zwischen_parteien")
                else:
                    einordnung.add("partei_unbekannt")
    reihenfolge = ["im_dokument", "innerhalb_partei", "zwischen_parteien", "partei_unbekannt"]
    return [e for e in reihenfolge if e in einordnung]


def _vertraege_trennen(angaben: list[dict]) -> None:
    """Mehrere Verträge gleicher Art (verschiedene Anlagen) nicht miteinander vergleichen.

    Ist ein Vertrag in der Akte nur unter einer Anlage vorgelegt, gehören alle Nennungen zusammen. Gibt es ihn
    unter mehreren Anlagen ("Generalplanervertrag vom 12.11.2019 — Anlage K 18" und "… vom 04.03.2021 — Anlage
    K 20"), sind es verschiedene Verträge; dann wird je Anlage getrennt abgeglichen und Nennungen ohne Anlage für sich.
    """
    anlagen: dict[str, set[str]] = {}
    for a in angaben:
        if a["merkmal"].startswith("vertrag:") and a["anlage"]:
            anlagen.setdefault(a["merkmal"], set()).add(a["anlage"])
    for a in angaben:
        if len(anlagen.get(a["merkmal"], ())) > 1:
            a["merkmal"] = f"{a['merkmal']}:{a['anlage'] or ''}"
            a["titel"] += f" (Anlage {a['anlage']})" if a["anlage"] else " (ohne Anlagenangabe)"


def abgleich(con: sqlite3.Connection, akte_id: int, dokument_ids: list[int] | None = None) -> dict:
    """Gleicht die Angaben aller (oder der gewählten) Dokumente einer Akte ab."""
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    dokumente = con.execute(
        "SELECT * FROM dokument WHERE akte_id = ? ORDER BY dateiname, id", (akte_id,)
    ).fetchall()
    if dokument_ids:
        gewaehlt = {int(i) for i in dokument_ids}
        dokumente = [d for d in dokumente if d["id"] in gewaehlt]
        if len(dokumente) != len(gewaehlt):
            raise LookupError("Mindestens eines der gewählten Dokumente gehört nicht zu dieser Akte.")

    angaben: list[dict] = []
    for dok in dokumente:
        parteien = [t["name"] for t in akte._tags(con, dok["id"]) if t["name"] in PARTEIEN]
        angaben.extend(_angaben_im_dokument(con, dok, parteien))
    _vertraege_trennen(angaben)

    merkmale: dict[str, dict] = {}
    for angabe in angaben:
        m = merkmale.setdefault(
            angabe["merkmal"], {"merkmal": angabe["merkmal"], "titel": angabe["titel"], "werte": {}}
        )
        w = m["werte"].setdefault(
            angabe["wert"],
            {"wert": angabe["wert"], "art": angabe["art"], "anzeige": anzeige(angabe["art"], angabe["wert"]),
             "fundstellen": []},
        )
        w["fundstellen"].append(angabe["fundstelle"])

    ergebnis = []
    for m in merkmale.values():
        werte = list(m["werte"].values())
        unvereinbar = any(not vereinbar(a["art"], a["wert"], b["art"], b["wert"]) for a, b in combinations(werte, 2))
        dokumente_mit = {f["dokument_id"] for w in werte for f in w["fundstellen"]}
        status = ABWEICHEND if unvereinbar else UEBEREINSTIMMEND if len(dokumente_mit) > 1 else EINZELN
        ergebnis.append(
            {
                "merkmal": m["merkmal"],
                "titel": m["titel"],
                "status": status,
                "einordnung": _einordnung(werte) if unvereinbar else [],
                "dokumente": len(dokumente_mit),
                "werte": werte,
            }
        )

    rang = {m.schluessel: i for i, m in enumerate(MERKMALE)}
    status_rang = {ABWEICHEND: 0, UEBEREINSTIMMEND: 1, EINZELN: 2}
    ergebnis.sort(key=lambda m: (status_rang[m["status"]], rang.get(m["merkmal"], len(rang)), m["titel"]))
    return {
        "dokumente": len(dokumente),
        "merkmale": ergebnis,
        "zaehlung": {s: sum(1 for m in ergebnis if m["status"] == s) for s in status_rang},
    }
