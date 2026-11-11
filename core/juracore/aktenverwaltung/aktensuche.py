"""Suche in den übrigen Teilen einer Akte: Notizen, Fristen und Termine, Stammdaten und Beteiligte, Zeiten.

Den Text der Dokumente durchsucht ``dokumente.suche`` (FTS5), Markierungen und Kommentare ``dokumente.anmerkungen``
und die Entscheidungen der Akte ``dokumente.urteile``. Hier geht es um die kurzen Einträge, die die Akte selbst
führt. Dafür lohnt kein eigener Index: Gesucht wird wie bei den Anmerkungen ohne Rücksicht auf Groß- und
Kleinschreibung und Akzente, und jedes Suchwort darf auch Teil eines Wortes sein („protokoll“ findet
„Terminsprotokoll“). Ein Eintrag passt, wenn er alle Suchwörter enthält, gleich in welchem Feld.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata

from . import stammdaten as _stammdaten
from . import verfahren as _verfahren

# Bereiche in der Reihenfolge der Trefferliste; der Wert ist der Reiter der Akte, der den Eintrag zeigt.
BEREICHE = {"notizen": "notizen", "fristen": "fristen", "stammdaten": "stammdaten", "beteiligte": "beteiligte",
            "zeiten": "zeiten"}
_UMFELD = 70  # Zeichen vor und nach dem Treffer im Ausschnitt
MAX_TREFFER = 500

_ART_KALENDER = {"frist": "Frist", "termin": "Termin", "wiedervorlage": "Wiedervorlage"}
_STAMMDATEN_FELDER = {"name": "Kurzbezeichnung", "aktenzeichen": "Aktenzeichen", "gegenstand": "Gegenstand",
                      "sachgebiet": "Sachgebiet", "eigene_rolle": "Unsere Rolle", "notiz": "Notiz zur Akte"}


def _klein(zeichen: str) -> str:
    zerlegt = unicodedata.normalize("NFKD", zeichen.casefold())
    return "".join(z for z in zerlegt if not unicodedata.combining(z))


def _vergleichbar(text: str) -> tuple[str, list[int]]:
    """Text klein und ohne Akzente, dazu für jedes Zeichen die Stelle im ursprünglichen Text (für den Ausschnitt)."""
    teile: list[str] = []
    stellen: list[int] = []
    for i, z in enumerate(text):
        n = _klein(z)
        teile.append(n)
        stellen.extend([i] * len(n))
    return "".join(teile), stellen


def suchwoerter(suchtext: str) -> list[str]:
    """Die Wörter der Eingabe; Anführungszeichen und der Stern * (Wortteil) spielen hier keine Rolle."""
    return [w for w in (_vergleichbar(t)[0] for t in suchtext.replace('"', " ").replace("*", " ").split()) if w]


def _ausschnitt(text: str, woerter: list[str]) -> dict | None:
    """Ausschnitt um das erste Suchwort im Feld, wie bei der Volltextsuche: vor, Treffer, nach."""
    norm, stellen = _vergleichbar(text)
    funde = [(norm.find(w), w) for w in woerter]
    funde = [(i, w) for i, w in funde if i >= 0]
    if not funde:
        return None
    i, w = min(funde)
    start, ende = stellen[i], stellen[i + len(w) - 1] + 1
    von, bis = max(0, start - _UMFELD), min(len(text), ende + _UMFELD)
    flach = lambda s: " ".join(s.split())  # noqa: E731
    vor, nach = flach(text[von:start]), flach(text[ende:bis])
    return {"vor": ("… " if von > 0 else "") + vor + (" " if text[von:start][-1:].isspace() else ""),
            "treffer": text[start:ende],
            "nach": (" " if text[ende:bis][:1].isspace() else "") + nach + (" …" if bis < len(text) else "")}


def _passt(felder: list[tuple[str, str]], woerter: list[str]) -> tuple[str, dict] | None:
    """(Feldname, Ausschnitt), wenn alle Wörter in den Feldern vorkommen; sonst None."""
    felder = [(name, wert) for name, wert in felder if wert]
    heu = _vergleichbar(" \n".join(wert for _, wert in felder))[0]
    if not all(w in heu for w in woerter):
        return None
    for name, wert in felder:
        if (a := _ausschnitt(wert, woerter)) is not None:
            return name, a
    return None  # pragma: no cover – alle Wörter stehen in einem der Felder


def _gibt(con: sqlite3.Connection, tabelle: str) -> bool:
    zeile = con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (tabelle,)).fetchone()
    return zeile is not None


def _treffer(bereich: str, art: str, eintrag_id: int, titel: str, feld: str, ausschnitt: dict,
             datum: str | None = None, dokument_id: int | None = None) -> dict:
    return {"bereich": bereich, "reiter": BEREICHE[bereich], "art": art, "id": eintrag_id, "titel": titel,
            "feld": feld, "datum": datum, "dokument_id": dokument_id, "ausschnitt": ausschnitt}


def _notizen(con: sqlite3.Connection, akte_id: int, woerter: list[str]) -> list[dict]:
    ergebnis = []
    for z in con.execute(
            """SELECT n.id, n.text, n.dokument_id, n.geaendert_am, COALESCE(d.titel, d.dateiname) AS dokument
               FROM aktennotiz n LEFT JOIN dokument d ON d.id = n.dokument_id
               WHERE n.akte_id = ? ORDER BY n.angeheftet DESC, n.geaendert_am DESC, n.id DESC""", (akte_id,)):
        if p := _passt([("Text", z["text"])], woerter):
            erste = next((zeile.strip() for zeile in z["text"].splitlines() if zeile.strip()), "")
            titel = erste.lstrip("#").strip()[:80] or "Notiz"
            art = f"Notiz zu „{z['dokument']}“" if z["dokument"] else "Notiz"
            ergebnis.append(_treffer("notizen", art, z["id"], titel, p[0], p[1], z["geaendert_am"][:10],
                                     z["dokument_id"]))
    return ergebnis


def _fristen(con: sqlite3.Connection, akte_id: int, woerter: list[str]) -> list[dict]:
    ergebnis = []
    for z in con.execute("SELECT * FROM kalender WHERE akte_id = ? ORDER BY datum DESC, id DESC", (akte_id,)):
        felder = [("Bezeichnung", z["titel"]), ("Ort", z["ort"]), ("Notiz", z["notiz"]),
                  ("Vermerk", z["erledigt_vermerk"])]
        if p := _passt(felder, woerter):
            ergebnis.append(_treffer("fristen", _ART_KALENDER.get(z["art"], z["art"]), z["id"], z["titel"], p[0],
                                     p[1], z["datum"], z["dokument_id"]))
    return ergebnis


def _stammdaten_treffer(con: sqlite3.Connection, akte_id: int, woerter: list[str]) -> list[dict]:
    ergebnis = []
    a = con.execute("SELECT * FROM akte WHERE id = ?", (akte_id,)).fetchone()
    spalten = a.keys()
    felder = [(titel, a[s]) for s, titel in _STAMMDATEN_FELDER.items() if s in spalten]
    if p := _passt(felder, woerter):
        ergebnis.append(_treffer("stammdaten", "Stammdaten", akte_id, a["name"], p[0], p[1]))
    if _gibt(con, "verfahren"):
        for v in _verfahren.liste(con, akte_id):
            felder = [("Verfahren", v["art_text"]), ("Instanz", v["instanz"]), ("Gericht", v["gericht"]),
                      ("Spruchkörper", v["spruchkoerper"]), ("Aktenzeichen", v["aktenzeichen"]),
                      ("Notiz", v["notiz"])]
            if p := _passt(felder, woerter):
                ergebnis.append(_treffer("stammdaten", "Verfahren", v["id"], v["bezeichnung"], p[0], p[1],
                                         v["beginn"]))
    return ergebnis


def _datenfelder(daten: str | None) -> list[tuple[str, str]]:
    """Angaben aus dem Beteiligtenverzeichnis (Anschrift, Telefon, E-Mail, Register …) als Felder."""
    try:
        d = json.loads(daten or "{}")
    except ValueError:
        return []
    return [(k.replace("_", " ").capitalize(), str(v)) for k, v in d.items() if isinstance(v, (str, int)) and v != ""]


def _beteiligte(con: sqlite3.Connection, akte_id: int, woerter: list[str]) -> list[dict]:
    ergebnis = []
    daten = {z["id"]: z["daten"] for z in con.execute(
        "SELECT t.id, t.daten FROM beteiligter t JOIN akte_beteiligung b ON b.beteiligter_id = t.id "
        "WHERE b.akte_id = ?", (akte_id,))}
    for b in _stammdaten.beteiligungen(con, akte_id):
        felder = [("Name", b["name"]), ("Rolle", b["rolle_text"]), ("Aktenzeichen", b["aktenzeichen"]),
                  *_datenfelder(daten.get(b["beteiligter_id"]))]
        if p := _passt(felder, woerter):
            ergebnis.append(_treffer("beteiligte", b["rolle_text"], b["id"], b["name"], p[0], p[1]))
    return ergebnis


def _zeiten(con: sqlite3.Connection, akte_id: int, woerter: list[str]) -> list[dict]:
    if not _gibt(con, "zeit_eintrag"):
        return []
    ergebnis = []
    for z in con.execute("SELECT * FROM zeit_eintrag WHERE akte_id = ? ORDER BY datum DESC, id DESC", (akte_id,)):
        if p := _passt([("Tätigkeit", z["taetigkeit"]), ("Bearbeiter", z["bearbeiter"])], woerter):
            ergebnis.append(_treffer("zeiten", "Zeiteintrag", z["id"], z["taetigkeit"] or "Zeiteintrag", p[0], p[1],
                                     z["datum"]))
    return ergebnis


_SUCHER = {"notizen": _notizen, "fristen": _fristen, "stammdaten": _stammdaten_treffer, "beteiligte": _beteiligte,
           "zeiten": _zeiten}


def suche(con: sqlite3.Connection, akte_id: int, suchtext: str, bereiche: list[str] | None = None) -> dict:
    """Treffer in Notizen, Fristen/Terminen, Stammdaten/Verfahren, Beteiligten und Zeiten der Akte ``akte_id``.

    ``bereiche`` beschränkt die Suche (Schlüssel aus ``BEREICHE``); ohne Angabe wird überall gesucht.
    """
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    unbekannt = set(bereiche or []) - set(BEREICHE)
    if unbekannt:
        raise ValueError(f"Unbekannter Bereich: {', '.join(sorted(unbekannt))}")
    woerter = suchwoerter(suchtext)
    if not woerter:
        return {"treffer": [], "gekuerzt": False}
    treffer: list[dict] = []
    for bereich in BEREICHE:
        if bereiche is None or bereich in bereiche:
            treffer.extend(_SUCHER[bereich](con, akte_id, woerter))
    return {"treffer": treffer[:MAX_TREFFER], "gekuerzt": len(treffer) > MAX_TREFFER}
