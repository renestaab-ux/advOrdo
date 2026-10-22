"""Aktennotizen: kurze Vermerke zur Akte oder zu einem Dokument, wichtige oben angeheftet."""

from __future__ import annotations

import sqlite3
from datetime import datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS aktennotiz (
    id           INTEGER PRIMARY KEY,
    akte_id      INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE,
    dokument_id  INTEGER REFERENCES dokument(id) ON DELETE CASCADE,
    text         TEXT NOT NULL,
    angeheftet   INTEGER NOT NULL DEFAULT 0,
    angelegt_am  TEXT NOT NULL,
    geaendert_am TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS aktennotiz_akte ON aktennotiz (akte_id);
"""


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
    con.commit()


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


def liste(con: sqlite3.Connection, akte_id: int, dokument_id: int | None = None) -> list[dict]:
    """Notizen der Akte (angeheftete zuerst, sonst neueste zuerst); mit ``dokument_id`` nur die zu diesem Dokument."""
    zeilen = con.execute(
        """SELECT n.*, d.dateiname AS dokument FROM aktennotiz n LEFT JOIN dokument d ON d.id = n.dokument_id
           WHERE n.akte_id = ? AND (? IS NULL OR n.dokument_id = ?)
           ORDER BY n.angeheftet DESC, n.geaendert_am DESC, n.id DESC""", (akte_id, dokument_id, dokument_id))
    return [dict(z) | {"angeheftet": bool(z["angeheftet"])} for z in zeilen]


def speichern(con: sqlite3.Connection, akte_id: int, text: str, dokument_id: int | None = None,
              angeheftet: bool | None = None, notiz_id: int | None = None) -> list[dict]:
    text = "\n".join(z.rstrip() for z in str(text or "").strip().splitlines())
    if not text:
        raise ValueError("Die Notiz ist leer.")
    if dokument_id is not None and con.execute(
            "SELECT 1 FROM dokument WHERE id = ? AND akte_id = ?", (dokument_id, akte_id)).fetchone() is None:
        raise ValueError("Das Dokument gehört nicht zu dieser Akte.")
    jetzt = _jetzt()
    with con:
        if notiz_id is None:
            con.execute("INSERT INTO aktennotiz (akte_id, dokument_id, text, angeheftet, angelegt_am, geaendert_am) "
                        "VALUES (?, ?, ?, ?, ?, ?)", (akte_id, dokument_id, text, int(bool(angeheftet)), jetzt, jetzt))
        else:
            if con.execute("SELECT 1 FROM aktennotiz WHERE id = ? AND akte_id = ?", (notiz_id, akte_id)).fetchone() \
                    is None:
                raise LookupError(f"Notiz {notiz_id} gibt es in dieser Akte nicht.")
            con.execute("UPDATE aktennotiz SET text = ?, angeheftet = COALESCE(?, angeheftet), geaendert_am = ? "
                        "WHERE id = ?", (text, None if angeheftet is None else int(angeheftet), jetzt, notiz_id))
    return liste(con, akte_id)


def anheften(con: sqlite3.Connection, notiz_id: int, angeheftet: bool = True) -> list[dict]:
    z = con.execute("SELECT akte_id FROM aktennotiz WHERE id = ?", (notiz_id,)).fetchone()
    if z is None:
        raise LookupError(f"Notiz {notiz_id} gibt es nicht.")
    with con:
        con.execute("UPDATE aktennotiz SET angeheftet = ? WHERE id = ?", (int(angeheftet), notiz_id))
    return liste(con, z["akte_id"])


def loeschen(con: sqlite3.Connection, notiz_id: int) -> list[dict]:
    z = con.execute("SELECT akte_id FROM aktennotiz WHERE id = ?", (notiz_id,)).fetchone()
    if z is None:
        raise LookupError(f"Notiz {notiz_id} gibt es nicht.")
    with con:
        con.execute("DELETE FROM aktennotiz WHERE id = ?", (notiz_id,))
    return liste(con, z["akte_id"])
