"""SQLite-Speicher der Wissensbasis.

Jeder Import eines Gesetzes legt eine neue *Fassung* an, sofern sich die
Quelldatei geändert hat (gleiche Prüfsumme = keine neue Fassung). Ältere
Fassungen bleiben erhalten, damit frühere Analysen mit ihrem damaligen
Quellenstand reproduzierbar sind. Suche und Zitatauflösung verwenden ohne
Angabe einer Fassung die jeweils neueste.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gesetz (
    id          INTEGER PRIMARY KEY,
    abk         TEXT NOT NULL UNIQUE,      -- "BGB"
    langtitel   TEXT
);

CREATE TABLE IF NOT EXISTS fassung (
    id              INTEGER PRIMARY KEY,
    gesetz_id       INTEGER NOT NULL REFERENCES gesetz(id),
    sha256          TEXT NOT NULL,          -- Prüfsumme der unveränderten Quelldatei
    quelle          TEXT NOT NULL,          -- URL oder Dateipfad
    abgerufen_am    TEXT NOT NULL,          -- ISO 8601, UTC
    builddate       TEXT,                   -- Erstellungsstempel der Quelle
    stand           TEXT,                   -- JSON-Liste der Standangaben
    roharchiv       TEXT,                   -- Pfad der archivierten Originaldatei
    UNIQUE (gesetz_id, sha256)
);

CREATE TABLE IF NOT EXISTS norm (
    id              INTEGER PRIMARY KEY,
    fassung_id      INTEGER NOT NULL REFERENCES fassung(id) ON DELETE CASCADE,
    doknr           TEXT,
    reihenfolge     INTEGER NOT NULL,
    bezeichnung     TEXT NOT NULL,          -- "§ 280"
    typ             TEXT NOT NULL,
    nummer          TEXT,                   -- "280"
    titel           TEXT,
    gliederung      TEXT NOT NULL,          -- JSON-Liste
    weggefallen     INTEGER NOT NULL,
    text            TEXT NOT NULL,
    fussnoten       TEXT
);
CREATE INDEX IF NOT EXISTS norm_nummer ON norm (fassung_id, typ, nummer);

CREATE TABLE IF NOT EXISTS absatz (
    id          INTEGER PRIMARY KEY,
    norm_id     INTEGER NOT NULL REFERENCES norm(id) ON DELETE CASCADE,
    reihenfolge INTEGER NOT NULL,
    nr          TEXT,                       -- "1", "1a" oder NULL bei Normen ohne Absätze
    text        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS satz (
    id          INTEGER PRIMARY KEY,
    absatz_id   INTEGER NOT NULL REFERENCES absatz(id) ON DELETE CASCADE,
    nr          INTEGER NOT NULL,
    text        TEXT NOT NULL,
    nummern     TEXT NOT NULL               -- JSON-Liste [[Nr, Text], …]
);

CREATE VIRTUAL TABLE IF NOT EXISTS norm_fts USING fts5(
    bezeichnung, titel, text,
    content='norm', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
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


def aktuelle_fassung(con: sqlite3.Connection, abk: str) -> sqlite3.Row | None:
    return con.execute(
        """SELECT f.*, g.abk, g.langtitel FROM fassung f JOIN gesetz g ON g.id = f.gesetz_id
           WHERE g.abk = ? ORDER BY f.id DESC LIMIT 1""",
        (abk.upper(),),
    ).fetchone()


def gesetze(con: sqlite3.Connection) -> list[dict]:
    zeilen = con.execute(
        """SELECT g.abk, g.langtitel, f.id AS fassung_id, f.abgerufen_am, f.builddate, f.stand, f.quelle,
                  (SELECT COUNT(*) FROM fassung f2 WHERE f2.gesetz_id = g.id) AS fassungen,
                  (SELECT COUNT(*) FROM norm n WHERE n.fassung_id = f.id) AS normen
           FROM gesetz g JOIN fassung f ON f.id = (SELECT MAX(id) FROM fassung WHERE gesetz_id = g.id)
           ORDER BY g.abk"""
    ).fetchall()
    return [{**dict(z), "stand": json.loads(z["stand"] or "[]")} for z in zeilen]


def fts_abfrage(suchtext: str) -> str:
    """Wandelt Nutzereingaben in eine sichere FTS5-Abfrage (alle Wörter, Präfixsuche)."""
    woerter = [w for w in "".join(c if c.isalnum() else " " for c in suchtext).split() if w]
    return " ".join(f'"{w}"*' for w in woerter)
