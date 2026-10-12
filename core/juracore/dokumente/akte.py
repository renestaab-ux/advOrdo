"""Akten: Dokumente einlesen, Originale unverändert ablegen, Normzitate verknüpfen.

Die Akten liegen in einer eigenen Datenbank (``akten.sqlite``), getrennt von der
Wissensbasis. Jede Originaldatei wird unverändert unter ihrer SHA-256-Prüfsumme
im Ordner der Akte abgelegt; dieselbe Datei wird pro Akte nur einmal übernommen.

Normzitate werden beim Einlesen gegen die Wissensbasis aufgelöst. Gespeichert
wird die dabei verwendete Fassung, damit der Beleg später mit demselben
Quellenstand nachvollziehbar bleibt.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..gesetze import wissensbasis
from ..gesetze.zitate import finde_zitate
from . import lesen
from .modell import Dokument
from .ocr import Tesseract

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS akte (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    angelegt_am TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dokument (
    id              INTEGER PRIMARY KEY,
    akte_id         INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE,
    dateiname       TEXT NOT NULL,
    format          TEXT NOT NULL,          -- pdf, docx, txt, md
    sha256          TEXT NOT NULL,          -- Prüfsumme der unveränderten Originaldatei
    groesse         INTEGER NOT NULL,
    original        TEXT NOT NULL,          -- Pfad der abgelegten Originaldatei
    importiert_am   TEXT NOT NULL,
    seiten          INTEGER,                -- NULL, wenn das Format keine Seiten kennt
    lesart          TEXT NOT NULL,          -- textebene, ocr, gemischt, datei, leer
    ocr_konfidenz   REAL,
    hinweise        TEXT NOT NULL,          -- JSON-Liste
    UNIQUE (akte_id, sha256)
);

CREATE TABLE IF NOT EXISTS seite (
    dokument_id INTEGER NOT NULL REFERENCES dokument(id) ON DELETE CASCADE,
    nr          INTEGER,
    quelle      TEXT NOT NULL,
    konfidenz   REAL,
    text        TEXT NOT NULL               -- Rohtext der Seite vor der Aufbereitung
);

CREATE TABLE IF NOT EXISTS abschnitt (
    id              INTEGER PRIMARY KEY,
    dokument_id     INTEGER NOT NULL REFERENCES dokument(id) ON DELETE CASCADE,
    nr              INTEGER NOT NULL,
    seite           INTEGER,
    seite_bis       INTEGER,
    rn              INTEGER,
    art             TEXT NOT NULL,
    text            TEXT NOT NULL,
    seitenwechsel   TEXT NOT NULL           -- JSON [[Zeichenposition, Seite], …]
);
CREATE INDEX IF NOT EXISTS abschnitt_dokument ON abschnitt (dokument_id, nr);

CREATE TABLE IF NOT EXISTS normzitat (
    id              INTEGER PRIMARY KEY,
    abschnitt_id    INTEGER NOT NULL REFERENCES abschnitt(id) ON DELETE CASCADE,
    start           INTEGER NOT NULL,       -- Ziel im Abschnittstext, z. B. "280 Abs. 1"
    ende            INTEGER NOT NULL,
    treffer_start   INTEGER NOT NULL,       -- ganzes Zitat, z. B. "§§ 280 Abs. 1, 281 BGB"
    treffer_ende    INTEGER NOT NULL,
    seite           INTEGER,
    zitat           TEXT NOT NULL,          -- normalisiert: "§ 280 Abs. 1 BGB"
    gesetz          TEXT NOT NULL,
    status          TEXT NOT NULL,          -- belegt, nicht_gefunden, unbekanntes_gesetz
    fassung_id      INTEGER,                -- Fassung der Wissensbasis bei der Prüfung
    norm            TEXT,
    titel           TEXT,
    hinweis         TEXT
);
CREATE INDEX IF NOT EXISTS normzitat_abschnitt ON normzitat (abschnitt_id);
"""


def oeffne(pfad: str | Path) -> sqlite3.Connection:
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(pfad)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(_SCHEMA)
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return con


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def akten(con: sqlite3.Connection) -> list[dict]:
    zeilen = con.execute(
        """SELECT a.*, (SELECT COUNT(*) FROM dokument d WHERE d.akte_id = a.id) AS dokumente
           FROM akte a ORDER BY a.id DESC"""
    ).fetchall()
    return [dict(z) for z in zeilen]


def akte_anlegen(con: sqlite3.Connection, name: str) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("Die Akte braucht einen Namen.")
    with con:
        akte_id = con.execute("INSERT INTO akte (name, angelegt_am) VALUES (?, ?)", (name, _jetzt())).lastrowid
    return dict(con.execute("SELECT *, 0 AS dokumente FROM akte WHERE id = ?", (akte_id,)).fetchone())


def _sha256(pfad: Path) -> str:
    h = hashlib.sha256()
    with pfad.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def importiere(
    con: sqlite3.Connection,
    wissen: sqlite3.Connection,
    akte_id: int,
    pfad: str | Path,
    ablage: Path,
    ocr: Tesseract | None | bool = True,
) -> dict:
    """Liest eine Datei in die Akte ein. Dieselbe Datei (gleiche Prüfsumme) wird nicht doppelt übernommen."""
    pfad = Path(pfad)
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    if not pfad.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {pfad}")
    fmt = lesen.format_von(pfad)
    sha = _sha256(pfad)
    vorhanden = con.execute("SELECT id FROM dokument WHERE akte_id = ? AND sha256 = ?", (akte_id, sha)).fetchone()
    if vorhanden:
        return {"dateiname": pfad.name, "dokument_id": vorhanden["id"], "neu": False}

    dok = lesen.lies(pfad, ocr)

    # Original unverändert ablegen, bevor etwas in der Datenbank steht.
    ordner = Path(ablage) / f"akte-{akte_id}"
    ordner.mkdir(parents=True, exist_ok=True)
    original = ordner / f"{sha}{pfad.suffix.lower()}"
    if not original.exists():
        shutil.copyfile(pfad, original)

    with con:
        dokument_id = _speichere(con, akte_id, pfad, fmt, sha, original, dok)
        _verknuepfe_zitate(con, wissen, dokument_id)
    zaehlung = _zitat_zaehlung(con, dokument_id)
    return {
        "dateiname": pfad.name,
        "dokument_id": dokument_id,
        "neu": True,
        "abschnitte": len(dok.abschnitte),
        "lesart": dok.lesart,
        "zitate": zaehlung,
        "hinweise": dok.hinweise,
    }


def _speichere(
    con: sqlite3.Connection, akte_id: int, pfad: Path, fmt: str, sha: str, original: Path, dok: Dokument
) -> int:
    seitenzahl = max((s.nr for s in dok.seiten if s.nr), default=None)
    dokument_id = con.execute(
        """INSERT INTO dokument (akte_id, dateiname, format, sha256, groesse, original, importiert_am,
                                 seiten, lesart, ocr_konfidenz, hinweise)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            akte_id,
            pfad.name,
            fmt,
            sha,
            pfad.stat().st_size,
            str(original),
            _jetzt(),
            seitenzahl,
            dok.lesart,
            dok.ocr_konfidenz,
            json.dumps(dok.hinweise, ensure_ascii=False),
        ),
    ).lastrowid
    con.executemany(
        "INSERT INTO seite (dokument_id, nr, quelle, konfidenz, text) VALUES (?, ?, ?, ?, ?)",
        [(dokument_id, s.nr, s.quelle, s.konfidenz, "\n".join(z for z in s.zeilen if z)) for s in dok.seiten],
    )
    con.executemany(
        """INSERT INTO abschnitt (dokument_id, nr, seite, seite_bis, rn, art, text, seitenwechsel)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (dokument_id, a.nr, a.seite, a.seite_bis, a.rn, a.art, a.text, json.dumps(a.seitenwechsel))
            for a in dok.abschnitte
        ],
    )
    return dokument_id


def _seite_an(seite: int | None, seitenwechsel: list, position: int) -> int | None:
    for pos, nr in seitenwechsel:
        if position >= pos:
            seite = nr
    return seite


def _verknuepfe_zitate(con: sqlite3.Connection, wissen: sqlite3.Connection, dokument_id: int) -> None:
    """Erkennt Normzitate in allen Abschnitten und löst sie gegen die neueste Fassung auf."""
    cache: dict[str, dict] = {}
    for a in con.execute("SELECT * FROM abschnitt WHERE dokument_id = ?", (dokument_id,)).fetchall():
        wechsel = json.loads(a["seitenwechsel"])
        for z in finde_zitate(a["text"]):
            schluessel = str(z)
            if schluessel not in cache:
                cache[schluessel] = wissensbasis.loese_zitat(wissen, z)
            beleg = cache[schluessel]
            start, ende = z.fundstelle_im_text
            con.execute(
                """INSERT INTO normzitat (abschnitt_id, start, ende, treffer_start, treffer_ende, seite, zitat,
                                          gesetz, status, fassung_id, norm, titel, hinweis)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    a["id"],
                    start,
                    ende,
                    z.treffer[0],
                    z.treffer[1],
                    _seite_an(a["seite"], wechsel, start),
                    schluessel,
                    z.gesetz,
                    beleg["status"],
                    (beleg["fassung"] or {}).get("id"),
                    beleg.get("norm"),
                    beleg.get("titel"),
                    beleg["hinweis"],
                ),
            )


def zitate_neu_pruefen(con: sqlite3.Connection, wissen: sqlite3.Connection, akte_id: int) -> dict:
    """Prüft alle Zitate einer Akte erneut, z. B. nachdem weitere Gesetze geladen wurden."""
    with con:
        dokumente = [r["id"] for r in con.execute("SELECT id FROM dokument WHERE akte_id = ?", (akte_id,))]
        for dokument_id in dokumente:
            con.execute(
                "DELETE FROM normzitat WHERE abschnitt_id IN (SELECT id FROM abschnitt WHERE dokument_id = ?)",
                (dokument_id,),
            )
            _verknuepfe_zitate(con, wissen, dokument_id)
    return {"dokumente": len(dokumente)}


def _zitat_zaehlung(con: sqlite3.Connection, dokument_id: int) -> dict:
    zeilen = con.execute(
        """SELECT z.status, COUNT(*) AS n FROM normzitat z JOIN abschnitt a ON a.id = z.abschnitt_id
           WHERE a.dokument_id = ? GROUP BY z.status""",
        (dokument_id,),
    ).fetchall()
    return {z["status"]: z["n"] for z in zeilen}


def _dokument_info(con: sqlite3.Connection, zeile: sqlite3.Row) -> dict:
    info = dict(zeile)
    info["hinweise"] = json.loads(info["hinweise"])
    info["zitate"] = _zitat_zaehlung(con, zeile["id"])
    info["randnummern"] = con.execute(
        "SELECT COUNT(*) FROM abschnitt WHERE dokument_id = ? AND rn IS NOT NULL", (zeile["id"],)
    ).fetchone()[0]
    return info


def dokumente(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    zeilen = con.execute("SELECT * FROM dokument WHERE akte_id = ? ORDER BY dateiname", (akte_id,)).fetchall()
    return [_dokument_info(con, z) for z in zeilen]


def dokument(con: sqlite3.Connection, dokument_id: int) -> dict:
    """Ein Dokument mit allen Abschnitten und den darin erkannten Normzitaten."""
    zeile = con.execute("SELECT * FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if zeile is None:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
    zitate: dict[int, list[dict]] = {}
    for z in con.execute(
        """SELECT z.* FROM normzitat z JOIN abschnitt a ON a.id = z.abschnitt_id
           WHERE a.dokument_id = ? ORDER BY z.abschnitt_id, z.start""",
        (dokument_id,),
    ):
        zitate.setdefault(z["abschnitt_id"], []).append(_zitat_info(z))
    abschnitte = [
        {
            "nr": a["nr"],
            "seite": a["seite"],
            "seite_bis": a["seite_bis"],
            "rn": a["rn"],
            "art": a["art"],
            "text": a["text"],
            "zitate": zitate.get(a["id"], []),
        }
        for a in con.execute("SELECT * FROM abschnitt WHERE dokument_id = ? ORDER BY nr", (dokument_id,))
    ]
    return {"dokument": _dokument_info(con, zeile), "abschnitte": abschnitte}


def _zitat_info(z: sqlite3.Row) -> dict:
    return {k: z[k] for k in z.keys() if k not in ("id", "abschnitt_id")}


def normen(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    """Alle in einer Akte zitierten Normen, mit Prüfergebnis und jeder Fundstelle."""
    zeilen = con.execute(
        """SELECT z.*, a.nr AS abschnitt, a.rn, d.id AS dokument_id, d.dateiname
           FROM normzitat z JOIN abschnitt a ON a.id = z.abschnitt_id JOIN dokument d ON d.id = a.dokument_id
           WHERE d.akte_id = ? ORDER BY z.gesetz, z.zitat, d.dateiname, a.nr""",
        (akte_id,),
    ).fetchall()
    gruppen: dict[str, dict] = {}
    for z in zeilen:
        g = gruppen.setdefault(
            z["zitat"],
            {k: z[k] for k in ("zitat", "gesetz", "status", "fassung_id", "norm", "titel", "hinweis")}
            | {"fundstellen": []},
        )
        g["fundstellen"].append(
            {"dokument_id": z["dokument_id"], "dateiname": z["dateiname"], "abschnitt": z["abschnitt"],
             "seite": z["seite"], "rn": z["rn"]}
        )
    reihenfolge = {"nicht_gefunden": 0, "unbekanntes_gesetz": 1, "belegt": 2}
    return sorted(gruppen.values(), key=lambda g: (reihenfolge.get(g["status"], 3), g["gesetz"], _normschluessel(g)))


def _normschluessel(g: dict) -> tuple:
    zahl = re.search(r"\d+", g["zitat"])
    return (int(zahl.group()) if zahl else 0, g["zitat"])
