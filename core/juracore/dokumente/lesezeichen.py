"""Lesezeichen an Dokumenten einer Akte: das Inhaltsverzeichnis des PDFs und eigene Lesezeichen in Ordnern.

Das Inhaltsverzeichnis (Gliederung, „Outline“) eines PDFs wird nur gelesen, nie verändert.

Die Ordner (Tabelle ``lesezeichen_ordner``) sind die Ordner der Akte für Lesezeichen und für Markierungen mit
Kommentaren gleichermaßen; beide teilen sich eine Reihenfolge, damit sie in einer gemeinsamen Ansicht sortierbar sind.

Eigene Lesezeichen hängen an einer Stelle im gelesenen Text wie Markierungen: Lage, Wortlaut und Umgebung. Nach einer
neuen Fassung wird die Stelle neu gesucht; findet sie sich nicht, bleibt das Lesezeichen mit „nicht_gefunden“
erhalten. Ordner gehören zur Akte; Lesezeichen und Ordner haben eine eigene Reihenfolge zum Sortieren.
"""

from __future__ import annotations

import sqlite3

from . import anmerkungen
from .anmerkungen import _jetzt, _Text, _umgebung, wiederfinden

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lesezeichen_ordner (
    id           INTEGER PRIMARY KEY,
    akte_id      INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    reihenfolge  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS lesezeichen (
    id           INTEGER PRIMARY KEY,
    dokument_id  INTEGER NOT NULL REFERENCES dokument(id) ON DELETE CASCADE,
    ordner_id    INTEGER REFERENCES lesezeichen_ordner(id) ON DELETE SET NULL,
    titel        TEXT NOT NULL,
    start        INTEGER NOT NULL,                    -- Lage im Text wie bei Markierungen
    ende         INTEGER NOT NULL,
    zitat        TEXT NOT NULL,
    davor        TEXT NOT NULL DEFAULT '',
    danach       TEXT NOT NULL DEFAULT '',
    seite        INTEGER,
    status       TEXT NOT NULL DEFAULT 'gefunden',    -- gefunden, nicht_gefunden
    textstand    TEXT,
    reihenfolge  INTEGER NOT NULL DEFAULT 0,
    angelegt_am  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS lesezeichen_dokument ON lesezeichen (dokument_id);
"""

MAX_TITEL = 200
ANKER = 60  # Zeichen ab der Stelle, über die ein Lesezeichen wiedergefunden wird


def einrichten(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)
    con.commit()


# --- Inhaltsverzeichnis des PDFs -------------------------------------------------------------------------------------

def inhalt(con: sqlite3.Connection, dokument_id: int) -> list[dict]:
    """Gliederung des Original-PDFs: ``ebene`` (0 = oberste), ``titel`` und ``seite`` (1-basiert, None ohne Ziel)."""
    import pypdfium2 as pdfium

    d = con.execute("SELECT format, original FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if d is None:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
    if d["format"] != "pdf":
        return []
    pdf = pdfium.PdfDocument(d["original"])
    try:
        eintraege = []
        for b in pdf.get_toc(max_depth=8):
            ziel = b.get_dest()
            nr = ziel.get_index() if ziel is not None else None
            titel = " ".join((b.get_title() or "").split())
            if titel:
                eintraege.append({"ebene": b.level, "titel": titel[:MAX_TITEL],
                                  "seite": nr + 1 if nr is not None and 0 <= nr < len(pdf) else None})
            if len(eintraege) >= 2000:
                break
        return eintraege
    finally:
        pdf.close()


# --- Eigene Lesezeichen ----------------------------------------------------------------------------------------------

def _pruefen(con: sqlite3.Connection, dokument_id: int) -> _Text:
    t = _Text(con, dokument_id)
    offen = con.execute("SELECT id, start, ende, zitat, davor, danach FROM lesezeichen "
                        "WHERE dokument_id = ? AND (textstand IS NULL OR textstand != ?)",
                        (dokument_id, t.stand)).fetchall()
    if not offen:
        return t
    with con:
        for z in offen:
            if t.text[z["start"]:z["ende"]] == z["zitat"]:
                lage = (z["start"], z["ende"])
            else:
                lage = wiederfinden(t.text, z["zitat"], z["davor"], z["danach"], z["start"])
            if lage is None:
                con.execute("UPDATE lesezeichen SET status = 'nicht_gefunden', textstand = ? WHERE id = ?",
                            (t.stand, z["id"]))
                continue
            davor, danach = _umgebung(t.text, *lage)
            con.execute("UPDATE lesezeichen SET start = ?, ende = ?, zitat = ?, davor = ?, danach = ?, seite = ?, "
                        "status = 'gefunden', textstand = ? WHERE id = ?",
                        (lage[0], lage[1], t.text[lage[0]:lage[1]], davor, danach, t.ort(lage[0])["seite"], t.stand,
                         z["id"]))
    return t


def _info(z: sqlite3.Row, t: _Text | None) -> dict:
    d = {k: z[k] for k in ("id", "dokument_id", "ordner_id", "titel", "start", "ende", "zitat", "seite", "status",
                           "reihenfolge", "angelegt_am")}
    ort = t.ort(z["start"]) if t is not None and z["status"] == "gefunden" else {}
    d["abschnitt"] = ort.get("abschnitt")
    d["rn"] = ort.get("rn")
    d["dokument"] = z["dokument"]
    return d


_ABFRAGE = """SELECT l.*, COALESCE(d.titel, d.dateiname) AS dokument FROM lesezeichen l
              JOIN dokument d ON d.id = l.dokument_id"""


def liste(con: sqlite3.Connection, akte_id: int | None = None, dokument_id: int | None = None) -> dict:
    """Ordner der Akte und Lesezeichen (eines Dokuments oder der ganzen Akte), jeweils in ihrer Reihenfolge."""
    if dokument_id is not None:
        z = con.execute("SELECT akte_id FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
        if z is None:
            raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
        akte_id = z["akte_id"]
    if akte_id is None:
        raise ValueError("Akte oder Dokument angeben.")
    dokumente = [dokument_id] if dokument_id is not None else [r[0] for r in con.execute(
        "SELECT DISTINCT l.dokument_id FROM lesezeichen l JOIN dokument d ON d.id = l.dokument_id "
        "WHERE d.akte_id = ?", (akte_id,))]
    texte = {d: _pruefen(con, d) for d in dokumente}
    zeilen = con.execute(
        _ABFRAGE + " WHERE d.akte_id = ? AND (? IS NULL OR l.dokument_id = ?) "
                   "ORDER BY l.reihenfolge, d.datum, d.id, l.start, l.id",
        (akte_id, dokument_id, dokument_id)).fetchall()
    ordner = [dict(o) for o in con.execute(
        "SELECT id, name, reihenfolge FROM lesezeichen_ordner WHERE akte_id = ? ORDER BY reihenfolge, id", (akte_id,))]
    return {"ordner": ordner, "lesezeichen": [_info(z, texte.get(z["dokument_id"])) for z in zeilen]}


def _titel(titel: str | None, vorgabe: str) -> str:
    text = " ".join(str(titel or "").split()) or " ".join(vorgabe.split())
    return text[:MAX_TITEL] or "Lesezeichen"


def _naechste(con: sqlite3.Connection, tabelle: str, wert: int) -> int:
    # Neue Einträge kommen ans Ende: Ordner je Akte, Lesezeichen in der gemeinsamen Ordnung mit den Markierungen.
    if tabelle != "lesezeichen_ordner":
        return anmerkungen.naechste_reihenfolge(con, wert)
    z = con.execute("SELECT MAX(reihenfolge) FROM lesezeichen_ordner WHERE akte_id = ?", (wert,)).fetchone()
    return (z[0] if z[0] is not None else -1) + 1


def anlegen(con: sqlite3.Connection, dokument_id: int, start: int, ende: int | None = None, titel: str | None = None,
            ordner_id: int | None = None) -> dict:
    """Setzt ein Lesezeichen an ``start`` (–``ende``). Ohne Titel gilt der Wortlaut an der Stelle."""
    t = _Text(con, dokument_id)
    if not t.abschnitte:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht oder es hat keinen Text.")
    start = min(max(0, int(start)), len(t.text) - 1)
    while start < len(t.text) - 1 and t.text[start].isspace():
        start += 1
    while start > 0 and t.text[start - 1].isalnum() and t.text[start].isalnum():
        start -= 1
    if ende is None or int(ende) <= start:
        ende = start + ANKER
    ende = min(int(ende), len(t.text))
    # Ohne eigene Auswahl bis zum Ende des Wortes bzw. der Zeile.
    zeilenende = t.text.find("\n", start)
    if 0 <= zeilenende < ende:
        ende = max(zeilenende, start + 1)
    while ende < len(t.text) and t.text[ende].isalnum() and t.text[ende - 1].isalnum():
        ende += 1
    zitat = t.text[start:ende]
    akte_id = con.execute("SELECT akte_id FROM dokument WHERE id = ?", (dokument_id,)).fetchone()["akte_id"]
    _pruefe_ordner(con, ordner_id, akte_id)
    davor, danach = _umgebung(t.text, start, ende)
    with con:
        cur = con.execute(
            "INSERT INTO lesezeichen (dokument_id, ordner_id, titel, start, ende, zitat, davor, danach, seite, "
            "textstand, reihenfolge, angelegt_am) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (dokument_id, ordner_id, _titel(titel, zitat[:80]), start, ende, zitat, davor, danach,
             t.ort(start)["seite"], t.stand, _naechste(con, "lesezeichen", akte_id), _jetzt()))
    return _eins(con, cur.lastrowid)


def anlegen_auf_seite(con: sqlite3.Connection, dokument_id: int, seite: int, wort_von: int | None = None,
                      wort_bis: int | None = None, titel: str | None = None, ordner_id: int | None = None) -> dict:
    """Lesezeichen im Original: an den gewählten Wörtern oder, ohne Wörter, am Anfang der Seite."""
    t = _Text(con, dokument_id)
    if wort_von is None:
        bereiche = t.seitenbereiche(int(seite))
        if not bereiche:
            raise ValueError(f"Auf Seite {seite} wurde kein Text gelesen.")
        return anlegen(con, dokument_id, bereiche[0][0], None, titel or f"Seite {seite}", ordner_id)
    from . import ansicht

    alle = anmerkungen.woerter(con, dokument_id, seite)
    von, bis = max(0, int(wort_von)), min(int(wort_bis if wort_bis is not None else wort_von), len(alle) - 1)
    if not alle or von > bis:
        raise ValueError("Die Auswahl enthält keinen Text.")
    seitentext, _ = ansicht._woerter_text(alle)
    vorher, _ = ansicht._woerter_text(alle[:von])
    stelle, _ = ansicht._woerter_text(alle[von:bis + 1])
    lage = (len(vorher) + 1) / max(len(seitentext), 1) if von else 0.0
    treffer = anmerkungen._auf_seite_finden(t, seite, stelle, lage)
    if treffer is None:
        raise ValueError("Die Stelle wurde im gelesenen Text der Seite nicht gefunden.")
    return anlegen(con, dokument_id, treffer[0], treffer[1], titel, ordner_id)


def _eins(con: sqlite3.Connection, lesezeichen_id: int) -> dict:
    z = con.execute(_ABFRAGE + " WHERE l.id = ?", (lesezeichen_id,)).fetchone()
    if z is None:
        raise LookupError(f"Lesezeichen {lesezeichen_id} gibt es nicht.")
    return _info(z, _Text(con, z["dokument_id"]))


def _pruefe_ordner(con: sqlite3.Connection, ordner_id: int | None, akte_id: int) -> None:
    if ordner_id is None:
        return
    z = con.execute("SELECT akte_id FROM lesezeichen_ordner WHERE id = ?", (ordner_id,)).fetchone()
    if z is None or z["akte_id"] != akte_id:
        raise ValueError("Der Ordner gehört nicht zu dieser Akte.")


def aendern(con: sqlite3.Connection, lesezeichen_id: int, titel: str | None = None) -> dict:
    z = _eins(con, lesezeichen_id)
    with con:
        con.execute("UPDATE lesezeichen SET titel = ? WHERE id = ?", (_titel(titel, z["titel"]), lesezeichen_id))
    return _eins(con, lesezeichen_id)


def loeschen(con: sqlite3.Connection, lesezeichen_id: int) -> dict:
    z = _eins(con, lesezeichen_id)
    with con:
        con.execute("DELETE FROM lesezeichen WHERE id = ?", (lesezeichen_id,))
    return {"geloescht": lesezeichen_id, "dokument_id": z["dokument_id"]}


_TABELLE = {"lesezeichen": "lesezeichen", "markierung": "anmerkung"}


def anordnen(con: sqlite3.Connection, akte_id: int, ordner: list[dict]) -> dict:
    """Neue Ordnung nach Ziehen und Ablegen: ``ordner`` ist die vollständige Folge der Ordner
    ``[{"id": Ordner-ID oder None für „Ohne Ordner“, "eintraege": [{"art": "lesezeichen"|"markierung", "id": …}]}]``.
    Lesezeichen und Markierungen teilen sich eine Reihenfolge. ``"lesezeichen": [IDs]`` gilt weiter als Kurzform."""
    eigene = {r[0] for r in con.execute("SELECT id FROM lesezeichen_ordner WHERE akte_id = ?", (akte_id,))}
    erlaubt = {art: {r[0] for r in con.execute(
        f"SELECT x.id FROM {tabelle} x JOIN dokument d ON d.id = x.dokument_id WHERE d.akte_id = ?", (akte_id,))}
        for art, tabelle in _TABELLE.items()}
    with con:
        nr_ordner = 0
        nr = 0
        for o in ordner:
            oid = o.get("id")
            if oid is not None:
                if oid not in eigene:
                    raise ValueError("Der Ordner gehört nicht zu dieser Akte.")
                con.execute("UPDATE lesezeichen_ordner SET reihenfolge = ? WHERE id = ?", (nr_ordner, oid))
                nr_ordner += 1
            eintraege = o.get("eintraege") or [{"art": "lesezeichen", "id": i} for i in o.get("lesezeichen", [])]
            for e in eintraege:
                art, eid = e.get("art"), e.get("id")
                if art not in _TABELLE or eid not in erlaubt[art]:
                    raise ValueError("Der Eintrag gehört nicht zu dieser Akte.")
                con.execute(f"UPDATE {_TABELLE[art]} SET ordner_id = ?, reihenfolge = ? WHERE id = ?", (oid, nr, eid))
                nr += 1
    return liste(con, akte_id=akte_id)


def ordner_anlegen(con: sqlite3.Connection, akte_id: int, name: str) -> dict:
    name = " ".join(str(name or "").split())[:80]
    if not name:
        raise ValueError("Der Ordner braucht einen Namen.")
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    with con:
        cur = con.execute("INSERT INTO lesezeichen_ordner (akte_id, name, reihenfolge) VALUES (?, ?, ?)",
                          (akte_id, name, _naechste(con, "lesezeichen_ordner", akte_id)))
    return {"id": cur.lastrowid, "name": name}


def ordner_umbenennen(con: sqlite3.Connection, ordner_id: int, name: str) -> dict:
    name = " ".join(str(name or "").split())[:80]
    if not name:
        raise ValueError("Der Ordner braucht einen Namen.")
    with con:
        if con.execute("UPDATE lesezeichen_ordner SET name = ? WHERE id = ?", (name, ordner_id)).rowcount == 0:
            raise LookupError(f"Ordner {ordner_id} gibt es nicht.")
    return {"id": ordner_id, "name": name}


def ordner_loeschen(con: sqlite3.Connection, ordner_id: int) -> dict:
    """Löscht den Ordner; seine Lesezeichen und Markierungen bleiben erhalten und stehen danach „Ohne Ordner“."""
    with con:
        con.execute("UPDATE lesezeichen SET ordner_id = NULL WHERE ordner_id = ?", (ordner_id,))
        con.execute("UPDATE anmerkung SET ordner_id = NULL WHERE ordner_id = ?", (ordner_id,))
        if con.execute("DELETE FROM lesezeichen_ordner WHERE id = ?", (ordner_id,)).rowcount == 0:
            raise LookupError(f"Ordner {ordner_id} gibt es nicht.")
    return {"geloescht": ordner_id}


def auf_seite(con: sqlite3.Connection, dokument_id: int, nr: int) -> list[dict]:
    """Lesezeichen auf Seite ``nr`` des Originals mit der Höhe der Stelle (Anteil der Seite, None = unbekannt)."""
    from . import ansicht

    t = _pruefen(con, dokument_id)
    zeilen = con.execute(_ABFRAGE + " WHERE l.dokument_id = ? AND l.status = 'gefunden' ORDER BY l.start",
                         (dokument_id,)).fetchall()
    ergebnis = []
    wo = None
    for z in zeilen:
        teile = t.stuecke_auf_seite(z["start"], z["ende"], nr)
        if not teile:
            continue
        if wo is None:
            wo = anmerkungen.woerter(con, dokument_id, nr)
        text, lage = teile[0]
        rechtecke = ansicht.rechtecke_fuer_stelle(wo, text, lage)
        ergebnis.append(_info(z, t) | {"y": rechtecke[0]["y"] if rechtecke else None})
    return ergebnis
