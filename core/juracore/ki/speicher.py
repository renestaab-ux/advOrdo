"""Ergebnisse des Sprachmodells in der Akten-Datenbank aufbewahren.

Ein lokales Modell braucht für eine Akte einige Minuten. Deshalb wird jedes
Ergebnis mit einem Schlüssel gespeichert, der Aufgabe, Fassung der Anweisungen,
Modell und den vorgelegten Text umfasst: Ändert sich nichts davon, wird das
gespeicherte Ergebnis gezeigt. Je Aufgabe, Bezug und Modell bleibt nur das
neueste Ergebnis. Mit dem Dokument oder der Akte verschwinden auch die
Ergebnisse (Kaskade, ``secure_delete`` ist an).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ki_ergebnis (
    schluessel   TEXT PRIMARY KEY,       -- SHA-256 über Aufgabe, Anweisungsfassung, Modell und Eingabe
    aufgabe      TEXT NOT NULL,          -- z. B. zusammenfassung_dokument, angaben, widersprueche
    akte_id      INTEGER REFERENCES akte(id) ON DELETE CASCADE,
    dokument_id  INTEGER REFERENCES dokument(id) ON DELETE CASCADE,
    bezug        TEXT NOT NULL,          -- Auswahl innerhalb der Akte, z. B. Dokumentnummern
    modell       TEXT NOT NULL,
    erstellt_am  TEXT NOT NULL,
    ergebnis     TEXT NOT NULL           -- JSON
);
CREATE INDEX IF NOT EXISTS ki_ergebnis_bezug ON ki_ergebnis (aufgabe, akte_id, dokument_id, bezug);
"""


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)


def schluessel(*teile: object) -> str:
    return hashlib.sha256(json.dumps(teile, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def lies(con: sqlite3.Connection, key: str) -> dict | None:
    zeile = con.execute("SELECT ergebnis FROM ki_ergebnis WHERE schluessel = ?", (key,)).fetchone()
    return json.loads(zeile["ergebnis"]) if zeile else None


def schreibe(
    con: sqlite3.Connection,
    key: str,
    aufgabe: str,
    modell: str,
    ergebnis: dict,
    akte_id: int | None = None,
    dokument_id: int | None = None,
    bezug: str = "",
) -> None:
    with con:
        con.execute(
            """DELETE FROM ki_ergebnis WHERE aufgabe = ? AND akte_id IS ? AND dokument_id IS ? AND bezug = ?
               AND modell = ?""",
            (aufgabe, akte_id, dokument_id, bezug, modell),
        )
        con.execute(
            """INSERT OR REPLACE INTO ki_ergebnis
               (schluessel, aufgabe, akte_id, dokument_id, bezug, modell, erstellt_am, ergebnis)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (key, aufgabe, akte_id, dokument_id, bezug, modell, datetime.now(UTC).isoformat(timespec="seconds"),
             json.dumps(ergebnis, ensure_ascii=False)),
        )


def ergebnisse(con: sqlite3.Connection, akte_id: int, modell: str) -> dict:
    """Gespeicherte Ergebnisse einer Akte für ein Modell: Akte, Widersprüche, Chronologie, je Dokument."""
    aus: dict = {"zusammenfassung_akte": None, "widersprueche": None, "chronologie": None, "dokumente": {}}
    for z in con.execute(
        """SELECT aufgabe, dokument_id, ergebnis FROM ki_ergebnis
           WHERE akte_id = ? AND modell = ? AND bezug = '' ORDER BY erstellt_am""",
        (akte_id, modell),
    ):
        ergebnis = json.loads(z["ergebnis"])
        ergebnis["gespeichert"] = True
        if z["aufgabe"] == "zusammenfassung_dokument":
            aus["dokumente"][str(z["dokument_id"])] = ergebnis
        elif z["aufgabe"] in aus and z["dokument_id"] is None:
            aus[z["aufgabe"]] = ergebnis
    return aus


def vergessen(con: sqlite3.Connection, akte_id: int, dokument_id: int) -> int:
    """Ein Dokument hat eine neue Fassung: Ergebnisse zu ihm und zur ganzen Akte passen nicht mehr zum Text."""
    with con:
        return con.execute(
            "DELETE FROM ki_ergebnis WHERE dokument_id = ? OR (akte_id = ? AND dokument_id IS NULL)",
            (dokument_id, akte_id),
        ).rowcount
