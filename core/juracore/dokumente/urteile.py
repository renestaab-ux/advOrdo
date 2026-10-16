"""Entscheidungen im Volltext zur Akte: selbst ergänzte Dateien und später geladene Volltexte.

Findet die App eine zitierte Entscheidung nicht im Verzeichnis (etwa ein OLG-Urteil oder einen
Tippfehler im Aktenzeichen), kann man sie aus einer anderen Quelle ergänzen, z. B. als PDF-Ausdruck
aus juris oder beck-online. Die Datei wird wie ein Aktendokument unverändert unter ihrer SHA-256-
Prüfsumme abgelegt und gelesen; Randnummern werden als Fundstellen erkannt.

Entscheidungen der Bundesgerichte, die im Verzeichnis belegt sind, lädt ``volltexte_laden`` als
öffentliche Rechtsquelle von rechtsprechung-im-internet.de; das ZIP wird unverändert im Roharchiv
abgelegt und bleibt dort, auch wenn das Urteil aus der Akte entfernt wird.

Ein Urteil gehört zu dem Zitat, für das es ergänzt wurde, und zu jedem anderen Zitat der Akte mit
demselben Gericht und Aktenzeichen.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import urllib.error
from collections.abc import Callable
from pathlib import Path

from ..rechtsprechung import verzeichnis
from ..rechtsprechung import volltext as rii
from ..rechtsprechung.zitate import normalisiere_az
from . import lesen
from .akte import _entferne_datei, _jetzt, _sha256
from .ocr import Tesseract

MANUELL = "manuell"
RII = "rii"

log = logging.getLogger("juracore.urteile")


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
                              "dateiname", "format", "lesart", "hinzugefuegt_am", "doknr")} | {
        "hinweise": json.loads(z["hinweise"]), "kopf": json.loads(z["kopf"]) if z["kopf"] else None}


def _doknr(entscheidung: dict | None) -> str | None:
    if not entscheidung:
        return None
    if entscheidung.get("doknr"):
        return entscheidung["doknr"]
    # Prüfergebnisse aus Version 0.1 speicherten nur den Link.
    m = re.search(r"docid=(?:jb-)?([A-Z0-9]+)", entscheidung.get("link") or "")
    return m.group(1) if m else None


def _speichere_volltext(con: sqlite3.Connection, akte_id: int, zitat: str, daten: bytes, archiv: Path) -> int:
    v = rii.lies(daten)
    sha, pfad = rii.archiviere(daten, archiv)
    vorhanden = con.execute("SELECT id FROM urteil WHERE akte_id = ? AND sha256 = ?", (akte_id, sha)).fetchone()
    if vorhanden:
        return vorhanden["id"]
    kopf = {"spruchkoerper": v.spruchkoerper, "doktyp": v.doktyp, "normen": v.normen,
            "vorinstanz": v.vorinstanz, "titel": v.titel}
    with con:
        urteil_id = con.execute(
            """INSERT INTO urteil (akte_id, zitat, gericht, aktenzeichen, az_norm, datum, quelle, herkunft, dateiname,
                                   format, sha256, original, lesart, hinweise, hinzugefuegt_am, doknr, kopf)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (akte_id, zitat, v.gericht, v.aktenzeichen, normalisiere_az(v.aktenzeichen), v.datum, RII,
             rii.HERKUNFT, f"jb-{v.doknr}.zip", "rii", sha, str(pfad), "datei", "[]", _jetzt(), v.doknr,
             json.dumps(kopf, ensure_ascii=False)),
        ).lastrowid
        con.executemany(
            "INSERT INTO urteil_abschnitt (urteil_id, nr, seite, rn, text, teil) VALUES (?, ?, NULL, ?, ?, ?)",
            [(urteil_id, i, a.rn, a.text, a.teil) for i, a in enumerate(v.absaetze, 1)],
        )
    return urteil_id


def volltexte_laden(
    con: sqlite3.Connection,
    wissen: sqlite3.Connection,
    akte_id: int,
    archiv: Path,
    lader: Callable[[str], bytes] = rii.lade,
    zitat: str | None = None,
) -> dict:
    """Lädt die Volltexte der im Verzeichnis belegten Entscheidungen der Akte, die noch nicht vorliegen.

    Mit ``zitat`` nur die Entscheidung zu diesem Zitat."""
    from .akte import rechtsprechung  # akte nutzt dieses Modul für die Zuordnung

    geladen, fehler = [], []
    for g in rechtsprechung(con, wissen, akte_id):
        doknr = _doknr(g["entscheidung"])
        if zitat is not None and g["zitat"] != zitat:
            continue
        if g["urteil"] is not None or g["status"] != verzeichnis.BELEGT or doknr is None:
            continue
        try:
            _speichere_volltext(con, akte_id, g["zitat"], lader(doknr), archiv)
            geladen.append(g["zitat"])
        except (OSError, ValueError, urllib.error.URLError) as f:
            log.warning("Volltext %s nicht geladen: %s", doknr, f)
            fehler.append({"zitat": g["zitat"], "fehler": str(f)})
    return {"geladen": geladen, "fehler": fehler}


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


def randnummern(con: sqlite3.Connection, urteil_id: int) -> set[int]:
    return {z["rn"] for z in con.execute(
        "SELECT rn FROM urteil_abschnitt WHERE urteil_id = ? AND rn IS NOT NULL", (urteil_id,))}


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
        "SELECT nr, seite, rn, text, teil FROM urteil_abschnitt WHERE urteil_id = ? ORDER BY nr", (urteil_id,)
    ).fetchall()
    return _info(z) | {"abschnitte": [dict(a) for a in abschnitte]}


def entfernen(con: sqlite3.Connection, urteil_id: int, ablage: Path | None = None) -> dict:
    """Entfernt ein Urteil aus der Akte und die abgelegte Kopie. Die eigene Datei am Ursprungsort bleibt;
    geladene Volltexte bleiben als Rechtsquelle im Roharchiv."""
    z = con.execute("SELECT * FROM urteil WHERE id = ?", (urteil_id,)).fetchone()
    if z is None:
        raise LookupError(f"Urteil {urteil_id} gibt es nicht.")
    with con:
        con.execute("DELETE FROM urteil WHERE id = ?", (urteil_id,))
    hinweis = None
    noch_genutzt = con.execute("SELECT 1 FROM urteil WHERE original = ?", (z["original"],)).fetchone()
    if z["quelle"] == MANUELL and not noch_genutzt:
        try:
            if not _entferne_datei(Path(z["original"]), ablage):
                hinweis = f"Die Kopie liegt außerhalb der Ablage und wurde nicht entfernt: {z['original']}"
        except OSError as fehler:
            hinweis = f"Die abgelegte Kopie konnte nicht entfernt werden ({fehler}): {z['original']}"
    return {"urteil_id": urteil_id, "dateiname": z["dateiname"], "hinweis": hinweis}
