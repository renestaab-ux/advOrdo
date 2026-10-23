"""Verfahren einer Akte: Mahnverfahren, Klage in erster Instanz, Berufung usw., je mit Gericht und Aktenzeichen.

Eine Akte kann nacheinander mehrere Verfahren haben (Mahnverfahren, danach Klageverfahren am Landgericht, danach
Berufung). Das jüngste laufende Verfahren ist das „aktuelle“; es steht im Kopf der Akte und in der Aktenübersicht.
Das Gericht eines Verfahrens wird zugleich als Beteiligter der Akte (Rolle Gericht, mit Aktenzeichen) geführt.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

from . import beteiligte

_SCHEMA = """
CREATE TABLE IF NOT EXISTS verfahren (
    id            INTEGER PRIMARY KEY,
    akte_id       INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE,
    art           TEXT NOT NULL,
    instanz       TEXT,                    -- "1. Instanz", "2. Instanz", "3. Instanz" oder leer
    gericht       TEXT,                    -- Name wie im Beteiligtenverzeichnis
    spruchkoerper TEXT,                    -- z. B. "2. Zivilkammer", "Kammer für Handelssachen"
    aktenzeichen  TEXT,                    -- gerichtliches Aktenzeichen bzw. Geschäftsnummer
    status        TEXT NOT NULL DEFAULT 'laufend',
    beginn        TEXT,
    ende          TEXT,
    notiz         TEXT,
    angelegt_am   TEXT NOT NULL,
    geaendert_am  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS verfahren_akte ON verfahren (akte_id);
"""

ARTEN = {
    "aussergerichtlich": "Außergerichtlich",
    "mahnverfahren": "Mahnverfahren",
    "klage": "Klageverfahren",
    "eilverfahren": "Einstweiliger Rechtsschutz",
    "beweisverfahren": "Selbständiges Beweisverfahren",
    "berufung": "Berufung",
    "revision": "Revision / Nichtzulassungsbeschwerde",
    "beschwerde": "Beschwerde",
    "vollstreckung": "Zwangsvollstreckung",
    "sonstiges": "Sonstiges Verfahren",
}
INSTANZEN = ("1. Instanz", "2. Instanz", "3. Instanz")
# Vorgabe der Instanz je Verfahrensart; frei änderbar (eine Beschwerde kann z. B. 2. Instanz sein).
INSTANZ_VORGABE = {"klage": "1. Instanz", "eilverfahren": "1. Instanz", "beweisverfahren": "1. Instanz",
                   "berufung": "2. Instanz", "revision": "3. Instanz"}
STATUS = {"laufend": "laufend", "ruhend": "ruhend", "abgeschlossen": "abgeschlossen"}
FELDER = ("art", "instanz", "gericht", "spruchkoerper", "aktenzeichen", "status", "beginn", "ende", "notiz")


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
    con.commit()


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _text(v: object) -> str:
    return " ".join(str(v or "").split())


def bezeichnung(v: dict) -> str:
    """Kurzform für Kopf und Übersicht: "Klageverfahren, 1. Instanz · LG Freiburg im Breisgau, 2 O 233/26"."""
    teile = [ARTEN.get(v["art"], v["art"])]
    if v.get("instanz"):
        teile[0] += f", {v['instanz']}"
    ort = ", ".join(t for t in (v.get("gericht"), v.get("aktenzeichen")) if t)
    return f"{teile[0]} · {ort}" if ort else teile[0]


def _zeile(z: sqlite3.Row) -> dict:
    v = dict(z)
    v["art_text"] = ARTEN.get(v["art"], v["art"])
    v["bezeichnung"] = bezeichnung(v)
    return v


def liste(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    """Alle Verfahren der Akte, ältestes zuerst (nach Beginn, ohne Beginn nach Ende); das aktuelle ist markiert."""
    verfahren = [_zeile(z) for z in con.execute(
        "SELECT * FROM verfahren WHERE akte_id = ? ORDER BY COALESCE(beginn, ende, angelegt_am), id", (akte_id,))]
    aktuell = aktuelles(verfahren)
    for v in verfahren:
        v["aktuell"] = aktuell is not None and v["id"] == aktuell["id"]
    return verfahren


def aktuelles(verfahren: list[dict]) -> dict | None:
    """Das jüngste laufende Verfahren, sonst das jüngste überhaupt."""
    laufend = [v for v in verfahren if v["status"] == "laufend"]
    return (laufend or verfahren or [None])[-1]


def speichern(con: sqlite3.Connection, akte_id: int, daten: dict, verfahren_id: int | None = None,
             gericht_daten: dict | None = None) -> list[dict]:
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    alt: dict = {}
    if verfahren_id is not None:
        z = con.execute("SELECT * FROM verfahren WHERE id = ? AND akte_id = ?", (verfahren_id, akte_id)).fetchone()
        if z is None:
            raise LookupError(f"Verfahren {verfahren_id} gibt es in dieser Akte nicht.")
        alt = dict(z)
    werte = {k: alt.get(k) for k in FELDER}
    for k in FELDER:
        if k in daten:
            werte[k] = "\n".join(t.strip() for t in str(daten[k] or "").splitlines() if t.strip()) if k == "notiz" \
                else _text(daten[k])
    if werte["art"] not in ARTEN:
        raise ValueError("Bitte die Art des Verfahrens wählen.")
    if verfahren_id is None and "instanz" not in daten:
        werte["instanz"] = INSTANZ_VORGABE.get(werte["art"], "")
    if werte["instanz"] and werte["instanz"] not in INSTANZEN:
        raise ValueError(f"Unbekannte Instanz: {werte['instanz']}")
    werte["status"] = werte["status"] or "laufend"
    if werte["status"] not in STATUS:
        raise ValueError(f"Unbekannter Status: {werte['status']}")
    for k in ("beginn", "ende"):
        if werte[k]:
            try:
                date.fromisoformat(werte[k])
            except ValueError as fehler:
                raise ValueError("Datum bitte im Format JJJJ-MM-TT.") from fehler
    werte = {k: (v or None) if k != "status" else v for k, v in werte.items()}
    jetzt = _jetzt()
    with con:
        if verfahren_id is None:
            con.execute(
                f"INSERT INTO verfahren (akte_id, {', '.join(FELDER)}, angelegt_am, geaendert_am) "
                f"VALUES (?, {', '.join('?' for _ in FELDER)}, ?, ?)", (akte_id, *werte.values(), jetzt, jetzt))
        else:
            con.execute(f"UPDATE verfahren SET {', '.join(f'{k} = ?' for k in FELDER)}, geaendert_am = ? "
                        "WHERE id = ?", (*werte.values(), jetzt, verfahren_id))
        if werte["gericht"]:
            gericht_eintragen(con, akte_id, werte["gericht"], werte["aktenzeichen"] or "", gericht_daten)
        con.execute("UPDATE akte SET geaendert_am = ? WHERE id = ?", (jetzt, akte_id))
    return liste(con, akte_id)


def gericht_eintragen(con: sqlite3.Connection, akte_id: int, name: str, aktenzeichen: str = "",
                      daten: dict | None = None) -> int:
    """Sorgt dafür, dass das Gericht als Beteiligter (Rolle Gericht) mit Aktenzeichen in der Akte steht.

    Ein gleichnamiges Gericht im Verzeichnis wird verwendet, sonst angelegt. ``daten`` (etwa die Anschrift aus dem
    Dokument) füllt nur leere Felder; Vorhandenes bleibt. Läuft innerhalb der Transaktion des Aufrufers.
    """
    s = beteiligte.schluessel(name)
    vorhanden = next((z for z in con.execute("SELECT id, schluessel, daten FROM beteiligter WHERE art = 'organisation'")
                      if z["schluessel"] == s), None)
    zusatz = {k: str(v).strip() for k, v in (daten or {}).items() if k not in ("name", "kategorie") and str(v).strip()}
    if vorhanden is None:
        neu = {**zusatz, "name": name, "kategorie": "Gericht"}
        bid = beteiligte._einfuegen(con, "organisation", name, beteiligte._bereinige("organisation", neu), _jetzt())
    else:
        bid = vorhanden["id"]
        alt = json.loads(vorhanden["daten"])
        fehlend = {k: v for k, v in zusatz.items() if not alt.get(k)}
        if fehlend:
            con.execute("UPDATE beteiligter SET daten = ?, geaendert_am = ? WHERE id = ?",
                        (json.dumps(beteiligte._bereinige("organisation", alt | fehlend), ensure_ascii=False),
                         _jetzt(), bid))
    vorhanden = bid
    b = con.execute("SELECT id, aktenzeichen FROM akte_beteiligung WHERE akte_id = ? AND rolle = 'gericht' "
                    "AND beteiligter_id = ?", (akte_id, vorhanden)).fetchone()
    if b is None:
        con.execute("INSERT INTO akte_beteiligung (akte_id, beteiligter_id, rolle, aktenzeichen, angelegt_am) "
                    "VALUES (?, ?, 'gericht', ?, ?)", (akte_id, vorhanden, aktenzeichen or None, _jetzt()))
    elif aktenzeichen and not b["aktenzeichen"]:
        con.execute("UPDATE akte_beteiligung SET aktenzeichen = ? WHERE id = ?", (aktenzeichen, b["id"]))
    return vorhanden


def loeschen(con: sqlite3.Connection, verfahren_id: int) -> list[dict]:
    """Entfernt das Verfahren. Fristen und Termine bleiben in der Akte (ohne Verfahren), das Gericht als Beteiligter."""
    z = con.execute("SELECT akte_id FROM verfahren WHERE id = ?", (verfahren_id,)).fetchone()
    if z is None:
        raise LookupError(f"Verfahren {verfahren_id} gibt es nicht.")
    with con:
        con.execute("DELETE FROM verfahren WHERE id = ?", (verfahren_id,))
    return liste(con, z["akte_id"])
