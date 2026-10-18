"""Zitate online prüfen: bayerische Gerichte bei gesetze-bayern.de, Bundesgerichte zusätzlich bei NeuRIS.

Das Verzeichnis von rechtsprechung-im-internet.de deckt nur die Bundesgerichte ab und wird als
Ganzes geladen. Für die übrigen Quellen gibt es kein solches Verzeichnis; hier wird je Zitat live
gesucht, und zwar nur, wenn man in der Akte „Online prüfen“ wählt. Gesendet wird nur das
Aktenzeichen der zitierten Entscheidung.

Die Ergebnisse sind öffentliche Angaben ohne Bezug zur Akte und liegen deshalb in der Wissensbasis
(Tabelle ``rechtsprechung_online``). Beim Prüfen eines Zitats ergänzen sie das Ergebnis des
Verzeichnisses: Was online gefunden wurde, gilt als belegt, mit der Quelle im Hinweis.

Auch hier gilt: Belegt ist nur, dass es die Entscheidung so gibt, nicht, dass sie die zitierte
Aussage trägt. Dass eine Entscheidung im Portal fehlt, heißt nicht, dass es sie nicht gibt; dort
stehen nur Entscheidungen, die zur Veröffentlichung bestimmt wurden.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import urllib.error
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from . import bayern, neuris, verzeichnis
from .zitate import normalisiere_az

log = logging.getLogger("juracore.online")

BAYERN = "bayern"
NEURIS = "neuris"
TITEL = {BAYERN: "gesetze-bayern.de", NEURIS: "NeuRIS (Testphase)"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rechtsprechung_online (
    quelle          TEXT NOT NULL,          -- bayern, neuris
    zitat           TEXT NOT NULL,          -- normalisiertes Zitat wie in urteilszitat.zitat
    status          TEXT NOT NULL,          -- belegt, abweichend, nicht_gefunden
    hinweis         TEXT,
    entscheidung    TEXT,                   -- JSON wie bei verzeichnis.pruefe, mit "quelle" und "doknr"
    geprueft_am     TEXT NOT NULL,
    PRIMARY KEY (quelle, zitat)
);
"""

# Was das Verzeichnis nicht belegen konnte und eine Online-Quelle klären kann.
_OFFEN = {verzeichnis.NICHT_GEFUNDEN, verzeichnis.ABWEICHEND, verzeichnis.KEIN_VERZEICHNIS, verzeichnis.AUSSERHALB}


# --- Einstellungen ---------------------------------------------------------------------------------


def einstellungen(datei: Path) -> dict:
    """Welche Online-Quellen genutzt werden. NeuRIS ist in der Testphase und deshalb zunächst aus."""
    try:
        gespeichert = json.loads(Path(datei).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        gespeichert = {}
    return {"neuris": bool(gespeichert.get("neuris", False))}


def einstellungen_setzen(datei: Path, neuris: bool) -> dict:
    datei = Path(datei)
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(json.dumps({"neuris": bool(neuris)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return einstellungen(datei)


def quellen(e: dict) -> set[str]:
    return {BAYERN} | ({NEURIS} if e.get("neuris") else set())


# --- Zwischenspeicher ------------------------------------------------------------------------------


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)


def ergebnisse(con: sqlite3.Connection, zitat: str) -> dict[str, dict]:
    try:
        zeilen = con.execute("SELECT * FROM rechtsprechung_online WHERE zitat = ?", (zitat,)).fetchall()
    except sqlite3.OperationalError:  # noch nie online geprüft: Tabelle fehlt
        return {}
    return {z["quelle"]: {"status": z["status"], "hinweis": z["hinweis"], "geprueft_am": z["geprueft_am"],
                          "entscheidung": json.loads(z["entscheidung"]) if z["entscheidung"] else None}
            for z in zeilen}


def _speichere(con: sqlite3.Connection, quelle: str, zitat: str, ergebnis: dict) -> None:
    with con:
        con.execute(
            """INSERT OR REPLACE INTO rechtsprechung_online (quelle, zitat, status, hinweis, entscheidung, geprueft_am)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (quelle, zitat, ergebnis["status"], ergebnis["hinweis"],
             json.dumps(ergebnis["entscheidung"], ensure_ascii=False) if ergebnis["entscheidung"] else None,
             datetime.now(UTC).isoformat(timespec="seconds")),
        )


# --- Welche Quelle für welches Zitat ---------------------------------------------------------------


def zustaendig(gericht: str, aktenzeichen: str | None, status: str, aktiv: set[str]) -> str | None:
    """Die Online-Quelle, die ein noch nicht belegtes Zitat klären kann, oder None."""
    if not aktenzeichen or status not in _OFFEN:
        return None
    if BAYERN in aktiv and bayern.ist_bayerisch(gericht):
        return BAYERN
    if NEURIS in aktiv and gericht.split()[0] in verzeichnis.BUNDESGERICHTE:
        return NEURIS
    return None


def ergaenze(con: sqlite3.Connection, zitat: str, beleg: dict) -> dict:
    """Ergänzt das Prüfergebnis des Verzeichnisses um gespeicherte Online-Ergebnisse."""
    if beleg["status"] == verzeichnis.BELEGT:
        return beleg
    online = ergebnisse(con, zitat)
    for quelle in (BAYERN, NEURIS):
        e = online.get(quelle)
        if e and e["status"] == verzeichnis.BELEGT:
            return beleg | {"status": e["status"], "hinweis": e["hinweis"], "entscheidung": e["entscheidung"]}
    for quelle in (BAYERN, NEURIS):
        e = online.get(quelle)
        if e and e["status"] == verzeichnis.ABWEICHEND:
            return beleg | {"status": e["status"], "hinweis": e["hinweis"], "entscheidung": e["entscheidung"]}
    zusatz = [e["hinweis"] for q in (BAYERN, NEURIS) if (e := online.get(q))]
    if zusatz:
        return beleg | {"hinweis": " ".join(filter(None, [beleg["hinweis"], *zusatz]))}
    return beleg


# --- Prüfen ----------------------------------------------------------------------------------------


def _tag(iso: str | None) -> str:
    if not iso:
        return "unbekanntem Datum"
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def _passt_gericht(zitiert: str, gefunden: str) -> bool:
    """„OLG München“ passt zu „OLG München“, „LG München“ auch zu „LG München I“; „BGH“ zu „BGH“."""
    z, g = zitiert.casefold().split(), gefunden.casefold().split()
    return bool(z) and g[:len(z)] == z


def bewerte(quelle: str, gericht: str, aktenzeichen: str, datum: str | None, treffer: list[dict]) -> dict:
    """Ordnet die Treffer einer Suche dem Zitat zu: belegt, abweichend oder nicht gefunden."""
    titel = TITEL[quelle]
    az = normalisiere_az(aktenzeichen)

    def az_passt(t: dict) -> bool:
        liste = t.get("aktenzeichen_liste") or [a for a in (t.get("aktenzeichen") or "").split(",")]
        return any(normalisiere_az(a) == az for a in liste if a.strip())

    gleiche = [t for t in treffer if az_passt(t)]
    eigene = [t for t in gleiche if _passt_gericht(gericht, t["gericht"])]
    passend = [t for t in eigene if datum is None or t["datum"] == datum]

    def beschreibung(t: dict) -> str:
        art = f"{t['doktyp']} vom {_tag(t['datum'])}" if t.get("doktyp") else _tag(t["datum"])
        return f"{t['gericht']}, {art} – {t['aktenzeichen']} ({titel})"

    if passend:
        return {"status": verzeichnis.BELEGT, "hinweis": beschreibung(passend[0]) + ".", "entscheidung": passend[0]}
    if eigene:
        daten = ", ".join(_tag(t["datum"]) for t in eigene)
        return {"status": verzeichnis.ABWEICHEND, "entscheidung": eigene[0],
                "hinweis": f"Laut {titel} ist diese Entscheidung vom {daten}, nicht vom {_tag(datum)}."}
    if gleiche:
        return {"status": verzeichnis.ABWEICHEND, "entscheidung": gleiche[0],
                "hinweis": f"Das Aktenzeichen gehört laut {titel} zu {beschreibung(gleiche[0])}."}
    if quelle == BAYERN:
        hinweis = (f"Bei {titel} nicht gefunden; dort stehen nur zur Veröffentlichung bestimmte Entscheidungen.")
    else:
        hinweis = f"Auch bei {titel} nicht gefunden."
    return {"status": verzeichnis.NICHT_GEFUNDEN, "hinweis": hinweis, "entscheidung": None}


def _bayern_suche(aktenzeichen: str) -> list[dict]:
    return [t.als_dict() for t in bayern.suche(aktenzeichen)[0]]


def _neuris_suche(aktenzeichen: str) -> list[dict]:
    return neuris.suche(aktenzeichen)[0]


SUCHE: dict[str, Callable[[str], list[dict]]] = {BAYERN: _bayern_suche, NEURIS: _neuris_suche}


def pruefe(
    con: sqlite3.Connection,
    zitate: list[dict],
    aktiv: set[str],
    neu: bool = False,
    suche: dict[str, Callable[[str], list[dict]]] | None = None,
) -> dict:
    """Prüft Zitate (``zitat``, ``gericht``, ``aktenzeichen``, ``datum``, ``status``) bei der zuständigen
    Online-Quelle. Bereits geprüfte Zitate werden nur mit ``neu`` erneut abgefragt."""
    einrichten(con)
    suche = SUCHE | (suche or {})
    geprueft, fehler = [], []
    for z in zitate:
        quelle = zustaendig(z["gericht"], z["aktenzeichen"], z["status"], aktiv)
        if quelle is None or (not neu and quelle in ergebnisse(con, z["zitat"])):
            continue
        try:
            ergebnis = bewerte(quelle, z["gericht"], z["aktenzeichen"], z["datum"], suche[quelle](z["aktenzeichen"]))
        except (OSError, ValueError, urllib.error.URLError) as f:
            log.warning("Online-Prüfung %s bei %s fehlgeschlagen: %s", z["zitat"], quelle, f)
            fehler.append({"zitat": z["zitat"], "quelle": TITEL[quelle], "fehler": str(f)})
            continue
        _speichere(con, quelle, z["zitat"], ergebnis)
        geprueft.append({"zitat": z["zitat"], "quelle": TITEL[quelle], "status": ergebnis["status"]})
    return {"geprueft": geprueft, "fehler": fehler}
