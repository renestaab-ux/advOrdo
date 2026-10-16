"""Entscheidungen im Volltext zur Akte: selbst ergänzte Dateien und später geladene Volltexte.

Findet die App eine zitierte Entscheidung nicht im Verzeichnis (etwa ein OLG-Urteil oder einen
Tippfehler im Aktenzeichen), kann man sie aus einer anderen Quelle ergänzen, z. B. als PDF-Ausdruck
aus juris oder beck-online. Die Datei wird wie ein Aktendokument unverändert unter ihrer SHA-256-
Prüfsumme abgelegt und gelesen; Randnummern werden als Fundstellen erkannt.

Ein ergänztes Urteil gehört zu dem Zitat, für das es ergänzt wurde, und zu jedem anderen Zitat der
Akte mit demselben Gericht und Aktenzeichen.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from ..rechtsprechung.zitate import normalisiere_az
from . import lesen
from .akte import _entferne_datei, _jetzt, _sha256
from .ocr import Tesseract

MANUELL = "manuell"
RII = "rii"


def ergaenzen(
    con: sqlite3.Connection,
    akte_id: int,
    pfad: str | Path,
    ablage: Path,
    gericht: str,
    aktenzeichen: str | None = None,
    datum: str | None = None,
    zitat: str | None = None,
    herkunft: str | None = None,
    ocr: Tesseract | None | bool = True,
) -> dict:
    """Legt eine Entscheidung aus einer eigenen Datei (PDF, DOCX, TXT, MD) zur Akte ab."""
    pfad = Path(pfad)
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    if not pfad.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {pfad}")
    gericht = " ".join((gericht or "").split())
    if not gericht:
        raise ValueError("Bitte das Gericht angeben.")
    aktenzeichen = " ".join((aktenzeichen or "").split()) or None
    fmt = lesen.format_von(pfad)
    sha = _sha256(pfad)
    vorhanden = con.execute("SELECT id FROM urteil WHERE akte_id = ? AND sha256 = ?", (akte_id, sha)).fetchone()
    if vorhanden:
        return {"urteil_id": vorhanden["id"], "neu": False, "dateiname": pfad.name}

    dok = lesen.lies(pfad, ocr)
    if not any(a.text.strip() for a in dok.abschnitte):
        raise ValueError(f"In {pfad.name} wurde kein Text gefunden. " + " ".join(dok.hinweise))

    ordner = Path(ablage) / f"akte-{akte_id}" / "urteile"
    ordner.mkdir(parents=True, exist_ok=True)
    original = ordner / f"{sha}{pfad.suffix.lower()}"
    if not original.exists():
        shutil.copyfile(pfad, original)

    with con:
        urteil_id = con.execute(
            """INSERT INTO urteil (akte_id, zitat, gericht, aktenzeichen, az_norm, datum, quelle, herkunft,
                                   dateiname, format, sha256, original, lesart, hinweise, hinzugefuegt_am)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (akte_id, zitat, gericht, aktenzeichen, normalisiere_az(aktenzeichen) if aktenzeichen else None,
             datum or None, MANUELL, (herkunft or "").strip() or None, pfad.name, fmt, sha, str(original),
             dok.lesart, json.dumps(dok.hinweise, ensure_ascii=False), _jetzt()),
        ).lastrowid
        con.executemany(
            "INSERT INTO urteil_abschnitt (urteil_id, nr, seite, rn, text) VALUES (?, ?, ?, ?, ?)",
            [(urteil_id, a.nr, a.seite, a.rn, a.text) for a in dok.abschnitte],
        )
    return {"urteil_id": urteil_id, "neu": True, "dateiname": pfad.name, "abschnitte": len(dok.abschnitte),
            "lesart": dok.lesart, "hinweise": dok.hinweise}


def _info(z: sqlite3.Row) -> dict:
    return {k: z[k] for k in ("id", "zitat", "gericht", "aktenzeichen", "datum", "quelle", "herkunft",
                              "dateiname", "format", "lesart", "hinzugefuegt_am")} | {
        "hinweise": json.loads(z["hinweise"])}


def liste(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    zeilen = con.execute("SELECT * FROM urteil WHERE akte_id = ? ORDER BY datum, gericht, aktenzeichen", (akte_id,))
    return [_info(z) for z in zeilen]


def uebersicht(con: sqlite3.Connection) -> dict:
    """Wie viele Entscheidungen aus welcher Quelle über alle Akten vorliegen."""
    zeilen = con.execute(
        "SELECT quelle, COALESCE(herkunft, '') AS herkunft, COUNT(*) AS n FROM urteil GROUP BY quelle, herkunft"
    ).fetchall()
    return {"gesamt": sum(z["n"] for z in zeilen),
            "quellen": [{"quelle": z["quelle"], "herkunft": z["herkunft"] or None, "anzahl": z["n"]} for z in zeilen]}


def zu_zitat(urteile: list[dict], zitat: str, gericht: str, aktenzeichen: str | None) -> dict | None:
    """Das zur Akte vorliegende Urteil für ein Zitat: gleiches Zitat oder gleiches Gericht und Aktenzeichen."""
    az = normalisiere_az(aktenzeichen) if aktenzeichen else None
    for u in urteile:
        if u["zitat"] == zitat:
            return u
        if az and u["aktenzeichen"] and normalisiere_az(u["aktenzeichen"]) == az \
                and u["gericht"].casefold() == gericht.casefold():
            return u
    return None


def volltext(con: sqlite3.Connection, urteil_id: int) -> dict:
    z = con.execute("SELECT * FROM urteil WHERE id = ?", (urteil_id,)).fetchone()
    if z is None:
        raise LookupError(f"Urteil {urteil_id} gibt es nicht.")
    abschnitte = con.execute(
        "SELECT nr, seite, rn, text FROM urteil_abschnitt WHERE urteil_id = ? ORDER BY nr", (urteil_id,)
    ).fetchall()
    return _info(z) | {"abschnitte": [dict(a) for a in abschnitte]}


def entfernen(con: sqlite3.Connection, urteil_id: int, ablage: Path | None = None) -> dict:
    """Entfernt ein ergänztes Urteil und seine abgelegte Kopie. Die eigene Datei am Ursprungsort bleibt."""
    z = con.execute("SELECT * FROM urteil WHERE id = ?", (urteil_id,)).fetchone()
    if z is None:
        raise LookupError(f"Urteil {urteil_id} gibt es nicht.")
    with con:
        con.execute("DELETE FROM urteil WHERE id = ?", (urteil_id,))
    hinweis = None
    if not con.execute("SELECT 1 FROM urteil WHERE original = ?", (z["original"],)).fetchone():
        try:
            if not _entferne_datei(Path(z["original"]), ablage):
                hinweis = f"Die Kopie liegt außerhalb der Ablage und wurde nicht entfernt: {z['original']}"
        except OSError as fehler:
            hinweis = f"Die abgelegte Kopie konnte nicht entfernt werden ({fehler}): {z['original']}"
    return {"urteil_id": urteil_id, "dateiname": z["dateiname"], "hinweis": hinweis}
