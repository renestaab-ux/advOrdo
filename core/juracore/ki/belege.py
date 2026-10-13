"""Belege des Sprachmodells am Originaltext prüfen.

Das Modell nennt zu jeder Aussage einen Absatz und ein wörtliches Zitat. Ob das
Zitat dort wirklich steht, prüft dieser Baustein ohne Modell: Er sucht das Zitat
im genannten Absatz, sonst in den übrigen Absätzen desselben Dokuments. Gezeigt
wird immer der gefundene Originaltext, nie die Wiedergabe des Modells. Wird ein
Zitat nirgends gefunden, gilt die Aussage als *ohne Beleg* und wird so angezeigt.

Verglichen wird nach einer Vereinheitlichung, die die Bedeutung nicht ändert:
Groß-/Kleinschreibung, Leerraum, Anführungszeichen, Gedankenstriche, weiche
Trennstriche. Kleinere Abweichungen (ein vertipptes oder ausgelassenes Wort)
gelten als *angenähert* gefunden, wenn mindestens 90 % des Zitats in derselben
Reihenfolge im Absatz stehen.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher

from ..dokumente import akte

WOERTLICH = "woertlich"
ANGENAEHERT = "angenaehert"

MIN_ZITAT = 6  # kürzere Zitate („ja“, „Kläger“) belegen nichts
MIN_ANTEIL = 0.9
UMFELD = 90  # Zeichen vor und nach dem Zitat im Ausschnitt

_ERSETZE = str.maketrans(
    {
        "„": '"', "“": '"', "”": '"', "»": '"', "«": '"', "‚": "'", "‘": "'", "’": "'", "´": "'", "`": "'",
        "–": "-", "—": "-", "‑": "-", "‐": "-", " ": " ", " ": " ", "…": ".",
    }
)


def normalisiere(text: str) -> tuple[str, list[int]]:
    """Vereinheitlichter Text und für jedes seiner Zeichen die Position im Original."""
    zeichen: list[str] = []
    positionen: list[int] = []
    leer = True
    for i, c in enumerate(text):
        if c == "­":  # weicher Trennstrich
            continue
        c = c.translate(_ERSETZE)
        if c.isspace():
            if leer:
                continue
            c, leer = " ", True
        else:
            leer = False
            klein = c.lower()
            c = klein if len(klein) == 1 else c
        zeichen.append(c)
        positionen.append(i)
    if zeichen and zeichen[-1] == " ":
        zeichen.pop()
        positionen.pop()
    return "".join(zeichen), positionen


@dataclass
class Fund:
    abschnitt: int  # Nummer des Abschnitts im Dokument
    start: int  # Zeichenposition im Original-Abschnittstext
    ende: int
    treffer: str  # WOERTLICH oder ANGENAEHERT


def _teile(zitat: str) -> list[str]:
    """Ein Zitat mit Auslassung („… lehnen … ab“) zerfällt in Teile, die der Reihe nach vorkommen müssen."""
    teile = re.split(r"\s*(?:\.\.\.|…|\[\.\.\.\]|\(\.\.\.\))\s*", zitat)
    return [t.strip(" \"'„“”") for t in teile if len(t.strip(" \"'„“”")) >= 3]


def _suche_woertlich(teile: list[str], text: str) -> tuple[int, int] | None:
    pos, anfang = 0, None
    for t in teile:
        i = text.find(t, pos)
        if i < 0:
            return None
        anfang = i if anfang is None else anfang
        pos = i + len(t)
    return (anfang, pos) if anfang is not None else None


def _suche_angenaehert(zitat: str, text: str) -> tuple[int, int] | None:
    if len(zitat) < 20 or len(text) < len(zitat) * MIN_ANTEIL:
        return None
    sm = SequenceMatcher(None, zitat, text, autojunk=False)
    bloecke = [b for b in sm.get_matching_blocks() if b.size >= 3]
    if not bloecke:
        return None
    # Der dichteste Bereich: Blöcke, die zusammen in ein Fenster von 1,3 × Zitatlänge passen.
    bester: tuple[int, int, int] | None = None
    for i in range(len(bloecke)):
        summe = 0
        for j in range(i, len(bloecke)):
            if bloecke[j].b + bloecke[j].size - bloecke[i].b > len(zitat) * 1.3:
                break
            summe += bloecke[j].size
            if bester is None or summe > bester[0]:
                bester = (summe, bloecke[i].b, bloecke[j].b + bloecke[j].size)
    if bester and bester[0] >= len(zitat) * MIN_ANTEIL:
        return bester[1], bester[2]
    return None


def finde(zitat: str, abschnitte: dict[int, str], bevorzugt: int | None = None) -> Fund | None:
    """Sucht das Zitat zuerst im genannten Abschnitt, dann in allen übrigen; wörtlich vor angenähert."""
    if not isinstance(zitat, str):
        return None
    norm_zitat, _ = normalisiere(zitat)
    teile = [normalisiere(t)[0] for t in _teile(zitat)] or [norm_zitat]
    if sum(len(t) for t in teile) < MIN_ZITAT:
        return None
    reihenfolge = ([bevorzugt] if bevorzugt in abschnitte else []) + [n for n in abschnitte if n != bevorzugt]
    normiert = {n: normalisiere(abschnitte[n]) for n in reihenfolge}
    for art, suche in ((WOERTLICH, lambda t: _suche_woertlich(teile, t)),
                       (ANGENAEHERT, lambda t: _suche_angenaehert(" ".join(teile), t))):
        for n in reihenfolge:
            text, positionen = normiert[n]
            treffer = suche(text)
            if treffer:
                von, bis = treffer
                return Fund(n, positionen[von], positionen[bis - 1] + 1, art)
    return None


# --- Dokumente für das Modell und Fundstellen für die Oberfläche ---------------------------------------


@dataclass
class Text:
    """Ein Dokument der Akte, wie es dem Modell vorgelegt und gegen das geprüft wird."""

    dokument_id: int
    dateiname: str
    parteien: list[str]
    abschnitte: list[sqlite3.Row]

    @property
    def nach_nr(self) -> dict[int, str]:
        return {a["nr"]: a["text"] for a in self.abschnitte}

    def fundstelle(self, fund: Fund) -> dict:
        """Fundstelle im selben Aufbau wie beim Abgleich (Dokument, Seite, Randnummer, Ausschnitt)."""
        a = next(a for a in self.abschnitte if a["nr"] == fund.abschnitt)
        text = a["text"]
        von, bis = max(0, fund.start - UMFELD), min(len(text), fund.ende + UMFELD)
        # Ausschnitt an Wortgrenzen beginnen und enden lassen.
        if von > 0:
            leer = text.find(" ", von, fund.start)
            von = leer + 1 if leer >= 0 else fund.start
        if bis < len(text):
            leer = text.rfind(" ", fund.ende, bis)
            bis = leer if leer > fund.ende else bis
        return {
            "dokument_id": self.dokument_id,
            "dateiname": self.dateiname,
            "abschnitt": a["nr"],
            "seite": akte._seite_an(a["seite"], json.loads(a["seitenwechsel"]), fund.start),
            "rn": a["rn"],
            "parteien": self.parteien,
            "treffer": fund.treffer,
            "ausschnitt": {
                "davor": ("… " if von > 0 else "") + re.sub(r"\s+", " ", text[von : fund.start]).lstrip(),
                "wert": re.sub(r"\s+", " ", text[fund.start : fund.ende]),
                "danach": re.sub(r"\s+", " ", text[fund.ende : bis]).rstrip() + (" …" if bis < len(text) else ""),
            },
        }


def lade_text(con: sqlite3.Connection, dokument_id: int, parteien_von: set[str]) -> Text:
    dok = con.execute("SELECT * FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if dok is None:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
    abschnitte = con.execute(
        "SELECT * FROM abschnitt WHERE dokument_id = ? ORDER BY nr", (dokument_id,)
    ).fetchall()
    parteien = [t["name"] for t in akte._tags(con, dokument_id) if t["name"] in parteien_von]
    return Text(dokument_id, dok["dateiname"], parteien, abschnitte)


def zeilen(abschnitte: list[sqlite3.Row]) -> str:
    """Abschnitte als nummerierte Zeilen für das Modell: „[12] Text“."""
    return "\n".join(f"[{a['nr']}] " + " ".join(a["text"].split()) for a in abschnitte)


def teile_auf(abschnitte: list[sqlite3.Row], budget: int) -> list[list[sqlite3.Row]]:
    """Teilt ein langes Dokument in Stücke, die mit ihrer Nummerierung in das Zeichenbudget passen."""
    stuecke: list[list[sqlite3.Row]] = [[]]
    groesse = 0
    for a in abschnitte:
        laenge = len(a["text"]) + 8
        if stuecke[-1] and groesse + laenge > budget:
            stuecke.append([])
            groesse = 0
        stuecke[-1].append(a)
        groesse += laenge
    return [s for s in stuecke if s]
