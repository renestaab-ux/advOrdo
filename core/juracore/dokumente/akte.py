"""Akten: Dokumente einlesen, Originale unverändert ablegen, Normzitate verknüpfen.

Die Akten liegen in einer eigenen Datenbank (``akten.sqlite``), getrennt von der
Wissensbasis. Jede Originaldatei wird unverändert unter ihrer SHA-256-Prüfsumme
im Ordner der Akte abgelegt; dieselbe Datei wird pro Akte nur einmal übernommen.

Normzitate werden beim Einlesen gegen die Wissensbasis aufgelöst. Gespeichert
wird die dabei verwendete Fassung, damit der Beleg später mit demselben
Quellenstand nachvollziehbar bleibt.

Dokumente tragen Tags, die zeigen, zu welchem Beteiligten sie gehören (Kläger,
Beklagter, Gericht …). Beim Einlesen eines Ordners werden sie aus den Namen der
Unterordner vorgeschlagen; übernommen werden sie nur, wenn die Oberfläche das
nach Rückfrage so übergibt. Von Hand lassen sie sich jederzeit ändern.

Gelöscht wird nur, was die App selbst angelegt hat: die Einträge in der
Datenbank und die abgelegte Kopie. Die Datei am ursprünglichen Ort bleibt.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..gesetze import wissensbasis
from ..gesetze.zitate import finde_zitate
from ..rechtsprechung import verzeichnis
from ..rechtsprechung.zitate import finde_urteilszitate
from . import lesen
from .modell import Dokument
from .ocr import Tesseract

SCHEMA_VERSION = 4

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
    herkunft        TEXT,                   -- Unterordner beim Ordner-Import, z. B. "Kläger/Anlagen"
    UNIQUE (akte_id, sha256)
);

CREATE TABLE IF NOT EXISTS tag (
    dokument_id INTEGER NOT NULL REFERENCES dokument(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,              -- z. B. "Kläger"
    quelle      TEXT NOT NULL,              -- ordner (aus dem Ordnernamen übernommen) oder manuell
    PRIMARY KEY (dokument_id, name)
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

CREATE TABLE IF NOT EXISTS urteilszitat (
    id              INTEGER PRIMARY KEY,
    abschnitt_id    INTEGER NOT NULL REFERENCES abschnitt(id) ON DELETE CASCADE,
    start           INTEGER NOT NULL,
    ende            INTEGER NOT NULL,
    seite           INTEGER,
    zitat           TEXT NOT NULL,          -- normalisiert: "BGH, Urteil vom 12.10.2016 – VIII ZR 103/15"
    gericht         TEXT NOT NULL,
    aktenzeichen    TEXT,
    datum           TEXT,
    status          TEXT NOT NULL,          -- belegt, abweichend, nicht_gefunden, ausserhalb, …
    hinweis         TEXT,
    stand_id        INTEGER,                -- Stand des Rechtsprechungsverzeichnisses bei der Prüfung
    entscheidung    TEXT,                   -- JSON: Gericht, Spruchkörper, Datum, Aktenzeichen, Link
    rn_zitiert      INTEGER                 -- zitierte Randnummer, z. B. 22 bei „…, Rn. 22“
);
CREATE INDEX IF NOT EXISTS urteilszitat_abschnitt ON urteilszitat (abschnitt_id);

-- Entscheidungen, die zur Akte im Volltext vorliegen: selbst ergänzt (z. B. PDF aus juris) oder geladen.
CREATE TABLE IF NOT EXISTS urteil (
    id              INTEGER PRIMARY KEY,
    akte_id         INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE,
    zitat           TEXT,                   -- Zitat der Akte, zu dem die Entscheidung ergänzt wurde
    gericht         TEXT NOT NULL,
    aktenzeichen    TEXT,
    az_norm         TEXT,
    datum           TEXT,
    quelle          TEXT NOT NULL,          -- manuell oder rii (rechtsprechung-im-internet.de)
    herkunft        TEXT,                   -- z. B. "juris", "beck-online" oder die Adresse des Abrufs
    dateiname       TEXT NOT NULL,
    format          TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    original        TEXT NOT NULL,          -- Pfad der unverändert abgelegten Datei
    lesart          TEXT NOT NULL,
    hinweise        TEXT NOT NULL,          -- JSON-Liste
    hinzugefuegt_am TEXT NOT NULL,
    doknr           TEXT,                   -- Dokumentnummer bei rechtsprechung-im-internet.de
    kopf            TEXT,                   -- JSON: Spruchkörper, Art, Normen, Vorinstanzen, Titel
    UNIQUE (akte_id, sha256)
);

CREATE TABLE IF NOT EXISTS urteil_abschnitt (
    urteil_id       INTEGER NOT NULL REFERENCES urteil(id) ON DELETE CASCADE,
    nr              INTEGER NOT NULL,
    seite           INTEGER,
    rn              INTEGER,
    text            TEXT NOT NULL,
    teil            TEXT                    -- leitsatz, tenor, gruende …; NULL bei eigenen Dateien
);
CREATE INDEX IF NOT EXISTS urteil_abschnitt_urteil ON urteil_abschnitt (urteil_id, nr);
"""


def oeffne(pfad: str | Path) -> sqlite3.Connection:
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(pfad)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    # Gelöschte Akteninhalte nicht als Reste in freien Seiten der Datei stehen lassen.
    con.execute("PRAGMA secure_delete = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(_SCHEMA)
    _migriere(con)
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return con


def _migriere(con: sqlite3.Connection) -> None:
    """Bringt Akten aus älteren Versionen auf den aktuellen Stand, ohne Inhalte zu verändern."""
    spalten = {z["name"] for z in con.execute("PRAGMA table_info(dokument)")}
    if "herkunft" not in spalten:
        con.execute("ALTER TABLE dokument ADD COLUMN herkunft TEXT")
    if "urteile_erkannt" not in spalten:
        # Dokumente aus älteren Versionen: Rechtsprechungszitate werden beim nächsten Abruf nachgetragen.
        con.execute("ALTER TABLE dokument ADD COLUMN urteile_erkannt INTEGER")
    # Zwischenstände von Schema 4 (Entwicklungsversion) um die späteren Spalten ergänzen.
    for tabelle, spalte, typ in (("urteilszitat", "rn_zitiert", "INTEGER"), ("urteil", "doknr", "TEXT"),
                                 ("urteil", "kopf", "TEXT"), ("urteil_abschnitt", "teil", "TEXT")):
        if spalte not in {z["name"] for z in con.execute(f"PRAGMA table_info({tabelle})")}:
            con.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {typ}")


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
    tags: list[str] | None = None,
    herkunft: str | None = None,
) -> dict:
    """Liest eine Datei in die Akte ein. Dieselbe Datei (gleiche Prüfsumme) wird nicht doppelt übernommen.

    ``tags`` sind die bestätigten Tags aus dem Ordnernamen, ``herkunft`` der Unterordner beim Ordner-Import.
    """
    pfad = Path(pfad)
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    if not pfad.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {pfad}")
    fmt = lesen.format_von(pfad)
    sha = _sha256(pfad)
    vorhanden = con.execute("SELECT id FROM dokument WHERE akte_id = ? AND sha256 = ?", (akte_id, sha)).fetchone()
    if vorhanden:
        # Schon vorhanden: nur bestätigte Tags ergänzen, nichts überschreiben.
        with con:
            _tags_ergaenzen(con, vorhanden["id"], tags or [], "ordner")
        return {"dateiname": pfad.name, "dokument_id": vorhanden["id"], "neu": False}

    dok = lesen.lies(pfad, ocr)

    # Original unverändert ablegen, bevor etwas in der Datenbank steht.
    ordner = Path(ablage) / f"akte-{akte_id}"
    ordner.mkdir(parents=True, exist_ok=True)
    original = ordner / f"{sha}{pfad.suffix.lower()}"
    if not original.exists():
        shutil.copyfile(pfad, original)

    with con:
        dokument_id = _speichere(con, akte_id, pfad, fmt, sha, original, dok, herkunft)
        _tags_ergaenzen(con, dokument_id, tags or [], "ordner")
        _verknuepfe_zitate(con, wissen, dokument_id)
        _verknuepfe_urteile(con, wissen, dokument_id)
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
    con: sqlite3.Connection,
    akte_id: int,
    pfad: Path,
    fmt: str,
    sha: str,
    original: Path,
    dok: Dokument,
    herkunft: str | None = None,
) -> int:
    seitenzahl = max((s.nr for s in dok.seiten if s.nr), default=None)
    dokument_id = con.execute(
        """INSERT INTO dokument (akte_id, dateiname, format, sha256, groesse, original, importiert_am,
                                 seiten, lesart, ocr_konfidenz, hinweise, herkunft)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            herkunft or None,
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


def _verknuepfe_urteile(con: sqlite3.Connection, wissen: sqlite3.Connection, dokument_id: int) -> None:
    """Erkennt Rechtsprechungszitate in allen Abschnitten und prüft sie gegen das Verzeichnis."""
    con.execute(
        "DELETE FROM urteilszitat WHERE abschnitt_id IN (SELECT id FROM abschnitt WHERE dokument_id = ?)",
        (dokument_id,),
    )
    stand = verzeichnis.stand(wissen)
    cache: dict[str, dict] = {}
    for a in con.execute("SELECT * FROM abschnitt WHERE dokument_id = ?", (dokument_id,)).fetchall():
        wechsel = json.loads(a["seitenwechsel"])
        for z in finde_urteilszitate(a["text"]):
            schluessel = str(z)
            if schluessel not in cache:
                cache[schluessel] = verzeichnis.pruefe(wissen, z, stand)
            beleg = cache[schluessel]
            con.execute(
                """INSERT INTO urteilszitat (abschnitt_id, start, ende, seite, zitat, gericht, aktenzeichen, datum,
                                             status, hinweis, stand_id, entscheidung, rn_zitiert)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (a["id"], *z.treffer, _seite_an(a["seite"], wechsel, z.treffer[0]), schluessel, z.gericht,
                 z.aktenzeichen, z.datum, beleg["status"], beleg["hinweis"], beleg["stand_id"],
                 json.dumps(beleg["entscheidung"], ensure_ascii=False) if beleg["entscheidung"] else None, z.rn),
            )
    con.execute("UPDATE dokument SET urteile_erkannt = 1 WHERE id = ?", (dokument_id,))


def zitate_neu_pruefen(con: sqlite3.Connection, wissen: sqlite3.Connection, akte_id: int) -> dict:
    """Prüft alle Zitate einer Akte erneut, z. B. nachdem weitere Gesetze oder die Rechtsprechung geladen wurden."""
    with con:
        dokumente = [r["id"] for r in con.execute("SELECT id FROM dokument WHERE akte_id = ?", (akte_id,))]
        for dokument_id in dokumente:
            con.execute(
                "DELETE FROM normzitat WHERE abschnitt_id IN (SELECT id FROM abschnitt WHERE dokument_id = ?)",
                (dokument_id,),
            )
            _verknuepfe_zitate(con, wissen, dokument_id)
            _verknuepfe_urteile(con, wissen, dokument_id)
    return {"dokumente": len(dokumente)}


def rechtsprechung(con: sqlite3.Connection, wissen: sqlite3.Connection, akte_id: int) -> list[dict]:
    """Alle in einer Akte zitierten Entscheidungen, mit Prüfergebnis und jeder Fundstelle."""
    with con:
        for r in con.execute(
            "SELECT id FROM dokument WHERE akte_id = ? AND urteile_erkannt IS NULL", (akte_id,)
        ).fetchall():
            _verknuepfe_urteile(con, wissen, r["id"])
    zeilen = con.execute(
        """SELECT z.*, a.nr AS abschnitt, a.rn, d.id AS dokument_id, d.dateiname
           FROM urteilszitat z JOIN abschnitt a ON a.id = z.abschnitt_id JOIN dokument d ON d.id = a.dokument_id
           WHERE d.akte_id = ? ORDER BY z.datum, z.zitat, d.dateiname, a.nr""",
        (akte_id,),
    ).fetchall()
    gruppen: dict[str, dict] = {}
    for z in zeilen:
        g = gruppen.setdefault(
            z["zitat"],
            {k: z[k] for k in ("zitat", "gericht", "aktenzeichen", "datum", "status", "hinweis")}
            | {"entscheidung": json.loads(z["entscheidung"]) if z["entscheidung"] else None, "fundstellen": []},
        )
        g["fundstellen"].append(
            {"dokument_id": z["dokument_id"], "dateiname": z["dateiname"], "abschnitt": z["abschnitt"],
             "seite": z["seite"], "rn": z["rn"], "start": z["start"], "ende": z["ende"],
             "rn_zitiert": z["rn_zitiert"]}
        )
    reihenfolge = {s: i for i, s in enumerate((verzeichnis.ABWEICHEND, verzeichnis.NICHT_GEFUNDEN,
                                               verzeichnis.KEIN_VERZEICHNIS, verzeichnis.BELEGT,
                                               verzeichnis.AUSSERHALB, verzeichnis.NICHT_PRUEFBAR))}
    from . import urteile  # urteile nutzt Hilfsfunktionen dieses Moduls

    vorliegend = urteile.liste(con, akte_id)
    for g in gruppen.values():
        g["urteil"] = urteile.zu_zitat(vorliegend, g["zitat"], g["gericht"], g["aktenzeichen"])
        # Zitierte Randnummern gegen den vorliegenden Volltext prüfen.
        rns = urteile.randnummern(con, g["urteil"]["id"]) if g["urteil"] else set()
        for f in g["fundstellen"]:
            f["rn_vorhanden"] = (f["rn_zitiert"] in rns) if rns and f["rn_zitiert"] is not None else None
        g["rn_hoechste"] = max(rns) if rns else None
    # Offene Fragen zuerst: innerhalb eines Status stehen Zitate ohne vorliegenden Volltext oben.
    return sorted(gruppen.values(), key=lambda g: (reihenfolge.get(g["status"], 9), g["urteil"] is not None,
                                                   g["datum"] or "", g["zitat"]))


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
    info["tags"] = _tags(con, zeile["id"])
    info["zitate"] = _zitat_zaehlung(con, zeile["id"])
    info["randnummern"] = con.execute(
        "SELECT COUNT(*) FROM abschnitt WHERE dokument_id = ? AND rn IS NOT NULL", (zeile["id"],)
    ).fetchone()[0]
    return info


def dokumente(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    zeilen = con.execute(
        "SELECT * FROM dokument WHERE akte_id = ? ORDER BY COALESCE(herkunft, ''), dateiname", (akte_id,)
    ).fetchall()
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


# --- Löschen --------------------------------------------------------------------------------------


def _entferne_datei(pfad: Path, ablage: Path | None) -> bool:
    """Entfernt eine abgelegte Kopie, aber nur innerhalb der Ablage der App."""
    if ablage is not None and not pfad.resolve().is_relative_to(Path(ablage).resolve()):
        return False
    try:
        pfad.unlink()
    except FileNotFoundError:
        return True
    return True


def dokument_loeschen(con: sqlite3.Connection, dokument_id: int, ablage: Path | None = None) -> dict:
    """Entfernt ein Dokument mit Text, Zitaten und Tags sowie die abgelegte Kopie. Das Original bleibt."""
    zeile = con.execute("SELECT * FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if zeile is None:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
    with con:
        con.execute("DELETE FROM dokument WHERE id = ?", (dokument_id,))
    original = Path(zeile["original"])
    hinweis = None
    noch_genutzt = con.execute("SELECT 1 FROM dokument WHERE original = ?", (zeile["original"],)).fetchone()
    if not noch_genutzt:
        try:
            if not _entferne_datei(original, ablage):
                hinweis = f"Die Kopie liegt außerhalb der Ablage und wurde nicht entfernt: {original}"
        except OSError as fehler:
            # Unter Windows kann ein anderes Programm die Datei geöffnet halten.
            hinweis = f"Die abgelegte Kopie konnte nicht entfernt werden ({fehler}): {original}"
    return {"dokument_id": dokument_id, "dateiname": zeile["dateiname"], "hinweis": hinweis}


def akte_loeschen(con: sqlite3.Connection, akte_id: int, ablage: Path) -> dict:
    """Entfernt eine Akte mit allen Dokumenten und ihrem Ablageordner. Originale am Ursprungsort bleiben."""
    zeile = con.execute("SELECT * FROM akte WHERE id = ?", (akte_id,)).fetchone()
    if zeile is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    anzahl = con.execute("SELECT COUNT(*) FROM dokument WHERE akte_id = ?", (akte_id,)).fetchone()[0]
    with con:
        con.execute("DELETE FROM akte WHERE id = ?", (akte_id,))
    ordner = Path(ablage) / f"akte-{akte_id}"
    hinweis = None
    if ordner.exists():
        try:
            shutil.rmtree(ordner)
        except OSError as fehler:
            hinweis = f"Der Ablageordner konnte nicht vollständig entfernt werden ({fehler}): {ordner}"
    return {"akte_id": akte_id, "name": zeile["name"], "dokumente": anzahl, "hinweis": hinweis}


# --- Ordner einlesen und Tags ---------------------------------------------------------------------

MAX_DATEIEN = 2000
MAX_TAG_LAENGE = 60

# Übliche Ordnernamen für Beteiligte, kleingeschrieben und ohne Umlaute -> einheitlicher Tag.
_BETEILIGTE = {
    "klaeger": "Kläger",
    "klaegerin": "Kläger",
    "klaegerseite": "Kläger",
    "klaegervertreter": "Kläger",
    "beklagte": "Beklagter",
    "beklagter": "Beklagter",
    "beklagtenseite": "Beklagter",
    "beklagtenvertreter": "Beklagter",
    "gericht": "Gericht",
    "streitverkuendete": "Streitverkündeter",
    "streitverkuendeter": "Streitverkündeter",
    "nebenintervenient": "Nebenintervenient",
    "nebenintervenientin": "Nebenintervenient",
    "sachverstaendiger": "Sachverständiger",
    "sachverstaendige": "Sachverständiger",
    "gutachten": "Sachverständiger",
    "mandant": "Mandant",
    "mandantin": "Mandant",
    "gegner": "Gegner",
    "gegenseite": "Gegner",
}
_GERICHTE = re.compile(r"(amts|land|oberlandes|bundes|arbeits|sozial|verwaltungs|finanz)?gericht", re.I)


def _schluessel(text: str) -> str:
    text = text.lower()
    for umlaut, ersatz in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(umlaut, ersatz)
    return re.sub(r"[^a-z]", "", text)


def tag_vorschlag(ordnername: str) -> str | None:
    """Schlägt zu einem Ordnernamen einen Tag vor, z. B. "02_Klägerin" -> "Kläger"."""
    # Nummerierung und Trennzeichen am Anfang weglassen ("01 Kläger", "2_Beklagte", "A) Gericht").
    name = re.sub(r"^\s*(?:\d+|[A-Za-z](?=[)._]))[\s._)\-]*(?=\D)", "", ordnername).strip(" _-.")
    name = re.sub(r"[_]+", " ", name).strip() or ordnername.strip()
    if not name:
        return None
    if beteiligter := _BETEILIGTE.get(_schluessel(name)):
        return beteiligter
    if _GERICHTE.fullmatch(_schluessel(name)):
        return "Gericht"
    return name[:MAX_TAG_LAENGE]


def _versteckt(name: str) -> bool:
    # Versteckte Dateien und Sperrdateien von Word ("~$Klage.docx") nicht einlesen.
    return name.startswith((".", "~$"))


def ordner_pruefen(pfad: str | Path) -> dict:
    """Sammelt die lesbaren Dateien eines Ordners samt Unterordnern und schlägt Tags je Unterordner vor.

    Es wird noch nichts eingelesen: Die Oberfläche fragt erst, ob die Tags übernommen werden sollen.
    """
    wurzel = Path(pfad)
    if not wurzel.is_dir():
        raise FileNotFoundError(f"Ordner nicht gefunden: {wurzel}")
    dateien: list[dict] = []
    uebersprungen: list[str] = []
    unterordner: dict[str, dict] = {}
    for ordner, verzeichnisse, namen in os.walk(wurzel):
        verzeichnisse[:] = sorted(v for v in verzeichnisse if not _versteckt(v))
        relativ = Path(ordner).relative_to(wurzel)
        herkunft = relativ.as_posix() if relativ.parts else ""
        for name in sorted(namen):
            if _versteckt(name):
                continue
            datei = Path(ordner) / name
            if datei.suffix.lower() not in lesen.FORMATE:
                uebersprungen.append((relativ / name).as_posix())
                continue
            if len(dateien) >= MAX_DATEIEN:
                raise ValueError(
                    f"Der Ordner enthält mehr als {MAX_DATEIEN} lesbare Dateien. Bitte einen kleineren wählen."
                )
            dateien.append({"pfad": str(datei), "relativ": (relativ / name).as_posix(), "herkunft": herkunft})
            if herkunft not in unterordner:
                vorschlag = [t for teil in relativ.parts if (t := tag_vorschlag(teil))]
                unterordner[herkunft] = {"herkunft": herkunft, "dateien": 0, "tags": list(dict.fromkeys(vorschlag))}
            unterordner[herkunft]["dateien"] += 1
    return {
        "ordner": str(wurzel),
        "name": wurzel.name,
        "dateien": dateien,
        "unterordner": sorted(unterordner.values(), key=lambda u: u["herkunft"]),
        "uebersprungen": uebersprungen,
    }


def _bereinige_tags(tags: list[str]) -> list[str]:
    ergebnis: dict[str, str] = {}
    for tag in tags:
        tag = re.sub(r"\s+", " ", str(tag)).strip()[:MAX_TAG_LAENGE]
        if tag:
            ergebnis.setdefault(tag.casefold(), tag)
    return list(ergebnis.values())


def _tags_ergaenzen(con: sqlite3.Connection, dokument_id: int, tags: list[str], quelle: str) -> None:
    vorhanden = {t["name"].casefold() for t in _tags(con, dokument_id)}
    con.executemany(
        "INSERT INTO tag (dokument_id, name, quelle) VALUES (?, ?, ?)",
        [(dokument_id, t, quelle) for t in _bereinige_tags(tags) if t.casefold() not in vorhanden],
    )


def tags_setzen(con: sqlite3.Connection, dokument_id: int, tags: list[str]) -> list[dict]:
    """Setzt die Tags eines Dokuments von Hand. Schon vorhandene Tags behalten ihre Herkunft."""
    if con.execute("SELECT 1 FROM dokument WHERE id = ?", (dokument_id,)).fetchone() is None:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
    neu = _bereinige_tags(tags)
    bisher = {r["name"].casefold(): r for r in con.execute("SELECT * FROM tag WHERE dokument_id = ?", (dokument_id,))}
    with con:
        con.execute("DELETE FROM tag WHERE dokument_id = ?", (dokument_id,))
        con.executemany(
            "INSERT INTO tag (dokument_id, name, quelle) VALUES (?, ?, ?)",
            [(dokument_id, t, bisher[t.casefold()]["quelle"] if t.casefold() in bisher else "manuell") for t in neu],
        )
    return _tags(con, dokument_id)


def _tags(con: sqlite3.Connection, dokument_id: int) -> list[dict]:
    zeilen = con.execute("SELECT name, quelle FROM tag WHERE dokument_id = ? ORDER BY name", (dokument_id,))
    return [dict(t) for t in zeilen]
