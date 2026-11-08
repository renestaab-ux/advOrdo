"""Dokumente außerhalb von advOrdo ansehen und bearbeiten, mit Fassungen.

Die abgelegten Dateien einer Akte werden nie verändert. Deshalb:

- Ansehen: advOrdo legt eine schreibgeschützte Kopie an und übergibt sie dem Programm.
- Bearbeiten: advOrdo legt eine Arbeitskopie an (höchstens eine je Dokument). Ändert sich
  ihre Prüfsumme, fragt die Oberfläche, ob sie als neue Fassung übernommen werden soll.
  Die neue Fassung wird unverändert abgelegt und neu eingelesen (Text, Normzitate,
  Datum); frühere Fassungen bleiben in der Ablage und lassen sich weiter ansehen.

Ablage je Akte: ``akte-<id>/<sha256>.<endung>`` für jede Fassung,
``akte-<id>/arbeitskopien/dokument-<id>/`` und ``akte-<id>/ansicht/dokument-<id>/v<nr>/``.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path

from . import akte, lesen
from .ocr import Tesseract


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _dokument(con: sqlite3.Connection, dokument_id: int) -> sqlite3.Row:
    zeile = con.execute("SELECT * FROM dokument WHERE id = ?", (dokument_id,)).fetchone()
    if zeile is None:
        raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
    return zeile


def liste(con: sqlite3.Connection, dokument_id: int) -> list[dict]:
    """Alle Fassungen eines Dokuments, neueste zuerst."""
    _dokument(con, dokument_id)
    zeilen = con.execute(
        """SELECT nr, dateiname, groesse, erstellt_am, quelle FROM dokument_fassung
           WHERE dokument_id = ? ORDER BY nr DESC""",
        (dokument_id,),
    ).fetchall()
    return [dict(z) | {"aktuell": i == 0} for i, z in enumerate(zeilen)]


def _fassung(con: sqlite3.Connection, dokument_id: int, nr: int | None) -> sqlite3.Row:
    zeile = con.execute(
        """SELECT * FROM dokument_fassung WHERE dokument_id = ? AND (? IS NULL OR nr = ?)
           ORDER BY nr DESC LIMIT 1""",
        (dokument_id, nr, nr),
    ).fetchone()
    if zeile is None:
        raise LookupError(f"Fassung {nr} von Dokument {dokument_id} gibt es nicht.")
    return zeile


def ansichtskopie(con: sqlite3.Connection, ablage: Path, dokument_id: int, nr: int | None = None) -> Path:
    """Schreibgeschützte Kopie einer Fassung (Standard: der aktuellen) zum Ansehen in einem anderen Programm."""
    d = _dokument(con, dokument_id)
    f = _fassung(con, dokument_id, nr)
    ordner = akte.dokument_ordner(ablage, d["akte_id"], dokument_id)[1] / f"v{f['nr']}"
    ziel = ordner / f["dateiname"]
    # Eine Fassung ändert sich nie; eine vorhandene Kopie bleibt (sie kann gerade in einem Programm offen sein).
    if ziel.is_file() and ziel.stat().st_size == f["groesse"]:
        return ziel
    quelle = Path(f["original"])
    if not quelle.is_file():
        raise FileNotFoundError(f"Die abgelegte Datei fehlt: {quelle}")
    ordner.mkdir(parents=True, exist_ok=True)
    if ziel.exists():
        ziel.chmod(stat.S_IREAD | stat.S_IWRITE)
    shutil.copyfile(quelle, ziel)
    ziel.chmod(stat.S_IREAD)
    return ziel


def arbeitskopie(con: sqlite3.Connection, ablage: Path, dokument_id: int) -> dict:
    """Arbeitskopie der aktuellen Fassung; eine vorhandene wird weiterverwendet, damit nichts verloren geht."""
    d = _dokument(con, dokument_id)
    vorhanden = con.execute("SELECT * FROM arbeitskopie WHERE dokument_id = ?", (dokument_id,)).fetchone()
    if vorhanden and Path(vorhanden["pfad"]).is_file():
        return {"pfad": vorhanden["pfad"], "neu": False}
    f = _fassung(con, dokument_id, None)
    ordner = akte.dokument_ordner(ablage, d["akte_id"], dokument_id)[0]
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / f["dateiname"]
    if ziel.exists():
        ziel.chmod(stat.S_IREAD | stat.S_IWRITE)
    shutil.copyfile(f["original"], ziel)
    ziel.chmod(stat.S_IREAD | stat.S_IWRITE)
    with con:
        con.execute(
            """INSERT OR REPLACE INTO arbeitskopie (dokument_id, pfad, basis_sha256, basis_nr, angelegt_am)
               VALUES (?, ?, ?, ?, ?)""",
            (dokument_id, str(ziel), f["sha256"], f["nr"], _jetzt()),
        )
    return {"pfad": str(ziel), "neu": True}


def _stand(z: sqlite3.Row) -> dict:
    pfad = Path(z["pfad"])
    aus = {"dokument_id": z["dokument_id"], "dateiname": z["dateiname"], "pfad": z["pfad"], "basis_nr": z["basis_nr"],
           "angelegt_am": z["angelegt_am"], "geaendert_am": None}
    if not pfad.is_file():
        return aus | {"status": "fehlt"}
    aus["geaendert_am"] = datetime.fromtimestamp(pfad.stat().st_mtime, UTC).isoformat(timespec="seconds")
    try:
        sha = akte._sha256(pfad)
    except OSError:
        # Während des Speicherns kann ein Programm die Datei kurz sperren; dann gilt sie als unverändert.
        return aus | {"status": "gesperrt"}
    return aus | {"status": "unveraendert" if sha == z["basis_sha256"] else "geaendert"}


def arbeitskopien(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    """Arbeitskopien einer Akte mit Status: unveraendert, geaendert, gesperrt oder fehlt."""
    zeilen = con.execute(
        """SELECT k.*, d.dateiname FROM arbeitskopie k JOIN dokument d ON d.id = k.dokument_id
           WHERE d.akte_id = ? ORDER BY d.dateiname""",
        (akte_id,),
    ).fetchall()
    return [_stand(z) for z in zeilen]


def uebernehmen(
    con: sqlite3.Connection,
    wissen: sqlite3.Connection,
    ablage: Path,
    dokument_id: int,
    ocr: Tesseract | None | bool = True,
) -> dict:
    """Übernimmt die geänderte Arbeitskopie als neue Fassung und liest sie neu ein."""
    d = _dokument(con, dokument_id)
    k = con.execute("SELECT * FROM arbeitskopie WHERE dokument_id = ?", (dokument_id,)).fetchone()
    if k is None or not Path(k["pfad"]).is_file():
        raise FileNotFoundError("Zu diesem Dokument gibt es keine Arbeitskopie.")
    pfad = Path(k["pfad"])
    sha = akte._sha256(pfad)
    if sha == k["basis_sha256"]:
        raise ValueError("Die Arbeitskopie ist unverändert; es gibt nichts zu übernehmen.")
    doppelt = con.execute(
        "SELECT dateiname FROM dokument WHERE akte_id = ? AND sha256 = ? AND id != ?", (d["akte_id"], sha, dokument_id)
    ).fetchone()
    if doppelt:
        raise ValueError(f"Genau diese Datei liegt schon als eigenes Dokument in der Akte: {doppelt['dateiname']}")
    fmt = lesen.format_von(pfad)
    dok = lesen.lies(pfad, ocr)

    # Neue Fassung unverändert ablegen, bevor etwas in der Datenbank steht.
    original = Path(ablage) / f"akte-{d['akte_id']}" / f"{sha}{pfad.suffix.lower()}"
    original.parent.mkdir(parents=True, exist_ok=True)
    if not original.exists():
        shutil.copyfile(pfad, original)
    groesse = original.stat().st_size
    nr = con.execute(
        "SELECT COALESCE(MAX(nr), 0) + 1 FROM dokument_fassung WHERE dokument_id = ?", (dokument_id,)
    ).fetchone()[0]

    with con:
        # Text und Zitate der bisherigen Fassung durch die neue ersetzen; Tags, Notizen und Chat bleiben.
        con.execute("DELETE FROM abschnitt WHERE dokument_id = ?", (dokument_id,))
        con.execute("DELETE FROM seite WHERE dokument_id = ?", (dokument_id,))
        con.execute(
            """UPDATE dokument SET format = ?, sha256 = ?, groesse = ?, original = ?, seiten = ?, lesart = ?,
                                   ocr_konfidenz = ?, hinweise = ? WHERE id = ?""",
            (fmt, sha, groesse, str(original), max((s.nr for s in dok.seiten if s.nr), default=None), dok.lesart,
             dok.ocr_konfidenz, json.dumps(dok.hinweise, ensure_ascii=False), dokument_id),
        )
        akte.inhalt_speichern(con, dokument_id, dok, fmt, original, pfad)
        akte.zitate_verknuepfen(con, wissen, dokument_id)
        con.execute(
            """INSERT INTO dokument_fassung (dokument_id, nr, dateiname, sha256, groesse, original, erstellt_am, quelle)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'bearbeitet')""",
            (dokument_id, nr, pfad.name, sha, groesse, str(original), _jetzt()),
        )
        # Die Arbeitskopie bleibt offen und zählt ab jetzt gegen die neue Fassung.
        con.execute("UPDATE arbeitskopie SET basis_sha256 = ?, basis_nr = ? WHERE dokument_id = ?",
                    (sha, nr, dokument_id))
    return {
        "dokument_id": dokument_id,
        "dateiname": pfad.name,
        "fassung": nr,
        "abschnitte": len(dok.abschnitte),
        "lesart": dok.lesart,
        "zitate": akte._zitat_zaehlung(con, dokument_id),
        "hinweise": dok.hinweise,
    }


def verwerfen(con: sqlite3.Connection, ablage: Path, dokument_id: int) -> dict:
    """Entfernt die Arbeitskopie. Nicht übernommene Änderungen gehen dabei verloren (die Oberfläche fragt vorher)."""
    d = _dokument(con, dokument_id)
    k = con.execute("SELECT * FROM arbeitskopie WHERE dokument_id = ?", (dokument_id,)).fetchone()
    if k is None:
        return {"dokument_id": dokument_id, "entfernt": False}
    if hinweis := akte.entferne_ordner(akte.dokument_ordner(ablage, d["akte_id"], dokument_id)[0]):
        raise RuntimeError(f"Die Arbeitskopie ist vermutlich noch in einem Programm geöffnet. Bitte dort schließen. "
                           f"{hinweis}")
    with con:
        con.execute("DELETE FROM arbeitskopie WHERE dokument_id = ?", (dokument_id,))
    return {"dokument_id": dokument_id, "entfernt": True}
