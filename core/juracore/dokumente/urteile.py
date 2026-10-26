"""Entscheidungen im Volltext zur Akte: selbst ergänzte Dateien und später geladene Volltexte.

Findet die App eine zitierte Entscheidung nicht im Verzeichnis (etwa ein OLG-Urteil oder einen
Tippfehler im Aktenzeichen), kann man sie aus einer anderen Quelle ergänzen, z. B. als PDF-Ausdruck
aus juris oder beck-online. Die Datei wird wie ein Aktendokument unverändert unter ihrer SHA-256-
Prüfsumme abgelegt und gelesen; Randnummern werden als Fundstellen erkannt.

Belegte Entscheidungen lädt ``volltexte_laden`` als öffentliche Rechtsquelle aus der Quelle, die
sie belegt hat: rechtsprechung-im-internet.de, gesetze-bayern.de oder NeuRIS. Die geladene Datei
wird unverändert im Roharchiv abgelegt und bleibt dort, auch wenn das Urteil aus der Akte entfernt
wird.

Ein Urteil gehört zu dem Zitat, für das es ergänzt wurde, und zu jedem anderen Zitat der Akte mit
demselben Gericht und Aktenzeichen.

Die Sammlung (Bereich „Rechtsprechung“) zeigt alle Entscheidungen über alle Akten. Eine Entscheidung kann
auch ohne Akte dort stehen („nicht zugeordnet“, ``akte_id`` NULL) und später einer oder mehreren Akten
zugeordnet werden; jede Zuordnung ist eine eigene Zeile mit eigener Kopie, damit das Löschen einer Akte
die anderen nicht berührt.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import sqlite3
import urllib.error
from collections.abc import Callable
from pathlib import Path

from ..rechtsprechung import bayern, kopfdaten, neuris, verzeichnis
from ..rechtsprechung import volltext as rii
from ..rechtsprechung.zitate import az_kern, normalisiere_az
from . import lesen
from .akte import _entferne_datei, _jetzt, _sha256
from .modell import Dokument
from .ocr import Tesseract
from .suche import _AUF, _ZU, _ausschnitt, _treffer, abfrage

MANUELL = "manuell"
RII = "rii"
BAYERN = "bayern"
NEURIS = "neuris"

# Je Quelle: Leser (Daten, Treffer) → Volltext, Herkunft, Archivordner und Dateiendung.
_QUELLEN = {
    RII: (lambda daten, _e: rii.lies(daten), rii.HERKUNFT, "volltexte", "zip"),
    BAYERN: (bayern.lies, bayern.HERKUNFT, "bayern", "zip"),
    NEURIS: (neuris.lies, neuris.HERKUNFT, "neuris", "html"),
}

log = logging.getLogger("juracore.urteile")


# Ablage der selbst ergänzten Dateien, die keiner Akte zugeordnet sind.
SAMMLUNG = "rechtsprechung"


def _ordner(ablage: Path, akte_id: int | None) -> Path:
    if akte_id is None:
        return Path(ablage) / SAMMLUNG
    return Path(ablage) / f"akte-{akte_id}" / "urteile"


def ergaenzen(
    con: sqlite3.Connection,
    akte_id: int | None,
    pfad: str | Path,
    ablage: Path,
    gericht: str,
    aktenzeichen: str | None = None,
    datum: str | None = None,
    zitat: str | None = None,
    herkunft: str | None = None,
    ocr: Tesseract | None | bool = True,
    art: str | None = None,
) -> dict:
    """Legt eine Entscheidung aus einer eigenen Datei (PDF, DOCX, TXT, MD) zur Akte ab; ohne Akte in die Sammlung.

    ``art`` (Urteil, Beschluss …) steht wie bei geladenen Volltexten im Kopf (``kopf.doktyp``)."""
    pfad = Path(pfad)
    if akte_id is not None and con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    if not pfad.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {pfad}")
    gericht = " ".join((gericht or "").split())
    if not gericht:
        raise ValueError("Bitte das Gericht angeben.")
    aktenzeichen = " ".join((aktenzeichen or "").split()) or None
    fmt = lesen.format_von(pfad)
    sha = _sha256(pfad)
    vorhanden = _vorhanden(con, akte_id, sha)
    if vorhanden:
        return {"urteil_id": vorhanden["id"], "neu": False, "dateiname": pfad.name}

    dok = _lies(pfad, ocr)
    if not any(a.text.strip() for a in dok.abschnitte):
        raise ValueError(f"In {pfad.name} wurde kein Text gefunden. " + " ".join(dok.hinweise))

    ordner = _ordner(ablage, akte_id)
    ordner.mkdir(parents=True, exist_ok=True)
    original = ordner / f"{sha}{pfad.suffix.lower()}"
    if not original.exists():
        shutil.copyfile(pfad, original)

    with con:
        urteil_id = con.execute(
            """INSERT INTO urteil (akte_id, zitat, gericht, aktenzeichen, az_norm, datum, quelle, herkunft,
                                   dateiname, format, sha256, original, lesart, hinweise, hinzugefuegt_am, kopf)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (akte_id, zitat, gericht, aktenzeichen, normalisiere_az(aktenzeichen) if aktenzeichen else None,
             datum or None, MANUELL, (herkunft or "").strip() or None, pfad.name, fmt, sha, str(original),
             dok.lesart, json.dumps(dok.hinweise, ensure_ascii=False), _jetzt(), _kopf_art(art)),
        ).lastrowid
        con.executemany(
            "INSERT INTO urteil_abschnitt (urteil_id, nr, seite, rn, text) VALUES (?, ?, ?, ?, ?)",
            [(urteil_id, a.nr, a.seite, a.rn, a.text) for a in dok.abschnitte],
        )
    return {"urteil_id": urteil_id, "neu": True, "dateiname": pfad.name, "abschnitte": len(dok.abschnitte),
            "lesart": dok.lesart, "hinweise": dok.hinweise}


# Zuletzt gelesene Datei: Der Vorschlag liest sie, das Ablegen gleich danach braucht denselben Text (bei Scans OCR).
_GELESEN: dict[tuple, Dokument] = {}


def _lies(pfad: Path, ocr: Tesseract | None | bool) -> Dokument:
    st = pfad.stat()
    schluessel = (str(pfad.resolve()), st.st_size, st.st_mtime_ns, bool(ocr))
    if schluessel not in _GELESEN:
        _GELESEN.clear()
        _GELESEN[schluessel] = lesen.lies(pfad, ocr)
    return _GELESEN[schluessel]


def _kopf_art(art: str | None) -> str | None:
    art = " ".join((art or "").split())
    if not art:
        return None
    return json.dumps({"spruchkoerper": None, "doktyp": art, "normen": None, "vorinstanz": [], "titel": None},
                      ensure_ascii=False)


def vorschlag(pfad: str | Path, ocr: Tesseract | None | bool = True) -> dict:
    """Liest eine eigene Datei und schlägt Gericht, Aktenzeichen, Datum, Art und Quelle vor, je mit Fundstelle."""
    pfad = Path(pfad)
    if not pfad.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {pfad}")
    dok = _lies(pfad, ocr)
    erkannt = kopfdaten.erkenne([(a.nr, a.seite, a.text) for a in dok.abschnitte])
    return {"dateiname": pfad.name, "lesart": dok.lesart, "hinweise": dok.hinweise} | erkannt


def _vorhanden(con: sqlite3.Connection, akte_id: int | None, sha: str) -> sqlite3.Row | None:
    return con.execute("SELECT id FROM urteil WHERE akte_id IS ? AND sha256 = ?", (akte_id, sha)).fetchone()


def _info(z: sqlite3.Row) -> dict:
    return {k: z[k] for k in ("id", "akte_id", "zitat", "gericht", "aktenzeichen", "datum", "quelle", "herkunft",
                              "dateiname", "format", "sha256", "lesart", "hinzugefuegt_am", "doknr")} | {
        "hinweise": json.loads(z["hinweise"]), "kopf": json.loads(z["kopf"]) if z["kopf"] else None}


def _doknr(entscheidung: dict | None) -> str | None:
    if not entscheidung:
        return None
    if entscheidung.get("doknr"):
        return entscheidung["doknr"]
    # Prüfergebnisse aus Version 0.1 speicherten nur den Link.
    m = re.search(r"docid=(?:jb-)?([A-Z0-9]+)", entscheidung.get("link") or "")
    return m.group(1) if m else None


def _dateiname(quelle: str, doknr: str) -> str:
    return {RII: f"jb-{doknr}.zip", BAYERN: f"{doknr}.zip", NEURIS: f"{doknr}.html"}[quelle]


def _speichere_volltext(
    con: sqlite3.Connection, akte_id: int | None, zitat: str | None, daten: bytes, archiv: Path,
    quelle: str = RII, entscheidung: dict | None = None,
) -> int:
    leser, herkunft, ordner, endung = _QUELLEN[quelle]
    v = leser(daten, entscheidung)
    sha, pfad = rii.archiviere(daten, archiv, ordner, endung)
    vorhanden = _vorhanden(con, akte_id, sha)
    if vorhanden:
        return vorhanden["id"]
    kopf = {"spruchkoerper": v.spruchkoerper, "doktyp": v.doktyp, "normen": v.normen,
            "vorinstanz": v.vorinstanz, "titel": v.titel}
    dateiname = _dateiname(quelle, v.doknr)
    with con:
        urteil_id = con.execute(
            """INSERT INTO urteil (akte_id, zitat, gericht, aktenzeichen, az_norm, datum, quelle, herkunft, dateiname,
                                   format, sha256, original, lesart, hinweise, hinzugefuegt_am, doknr, kopf)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (akte_id, zitat, v.gericht, v.aktenzeichen, normalisiere_az(v.aktenzeichen), v.datum, quelle,
             herkunft, dateiname, quelle, sha, str(pfad), "datei", "[]", _jetzt(), v.doknr,
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
    lader_online: dict[str, Callable[[str], bytes]] | None = None,
) -> dict:
    """Lädt die Volltexte der belegten Entscheidungen der Akte, die noch nicht vorliegen, aus der Quelle,
    die sie belegt hat. Mit ``zitat`` nur die Entscheidung zu diesem Zitat."""
    from .akte import rechtsprechung  # akte nutzt dieses Modul für die Zuordnung

    lader_je_quelle = {RII: lader, BAYERN: bayern.lade, NEURIS: neuris.lade} | (lader_online or {})
    geladen, fehler = [], []
    for g in rechtsprechung(con, wissen, akte_id):
        doknr = _doknr(g["entscheidung"])
        quelle = (g["entscheidung"] or {}).get("quelle") or RII
        if zitat is not None and zitat not in g["zitate"]:
            continue
        if g["urteil"] is not None or g["status"] != verzeichnis.BELEGT or doknr is None or quelle not in _QUELLEN:
            continue
        try:
            _speichere_volltext(con, akte_id, g["zitat"], lader_je_quelle[quelle](doknr), archiv, quelle,
                                g["entscheidung"])
            geladen.append(g["zitat"])
        except (OSError, ValueError, urllib.error.URLError) as f:
            log.warning("Volltext %s nicht geladen: %s", doknr, f)
            fehler.append({"zitat": g["zitat"], "fehler": str(f)})
    return {"geladen": geladen, "fehler": fehler}


def liste(con: sqlite3.Connection, akte_id: int) -> list[dict]:
    zeilen = con.execute("SELECT * FROM urteil WHERE akte_id = ? ORDER BY datum, gericht, aktenzeichen", (akte_id,))
    return [_info(z) for z in zeilen]


def zur_bearbeitung(con: sqlite3.Connection, wissen: sqlite3.Connection, akte_id: int) -> list[dict]:
    """Entscheidungen, die der Akte aus der Sammlung zugeordnet sind, ohne dass ein Dokument der Akte sie zitiert
    (Abschnitt „Zur weiteren Bearbeitung zugeordnet“ im Reiter Rechtsprechung der Akte)."""
    from .akte import rechtsprechung

    zitiert = {g["urteil"]["id"] for g in rechtsprechung(con, wissen, akte_id, online_quellen=set()) if g["urteil"]}
    return sorted((u for u in liste(con, akte_id) if u["id"] not in zitiert),
                  key=lambda u: (u["datum"] or "", u["id"]), reverse=True)


def uebersicht(con: sqlite3.Connection) -> dict:
    """Wie viele Entscheidungen aus welcher Quelle in der Sammlung stehen; je Datei einmal, auch wenn sie mehreren
    Akten zugeordnet ist."""
    zeilen = con.execute(
        """SELECT quelle, COALESCE(herkunft, '') AS herkunft, COUNT(DISTINCT sha256) AS n FROM urteil
           GROUP BY quelle, herkunft"""
    ).fetchall()
    return {"gesamt": sum(z["n"] for z in zeilen),
            "quellen": [{"quelle": z["quelle"], "herkunft": z["herkunft"] or None, "anzahl": z["n"]} for z in zeilen]}


def randnummern(con: sqlite3.Connection, urteil_id: int) -> set[int]:
    return {z["rn"] for z in con.execute(
        "SELECT rn FROM urteil_abschnitt WHERE urteil_id = ? AND rn IS NOT NULL", (urteil_id,))}


def zu_zitat(urteile: list[dict], zitat: str, gericht: str, aktenzeichen: str | None) -> dict | None:
    """Das zur Akte vorliegende Urteil für ein Zitat: gleiches Zitat oder gleiches Gericht und Aktenzeichen."""
    az = az_kern(aktenzeichen) if aktenzeichen else None
    for u in urteile:
        if u["zitat"] == zitat:
            return u
        if az and u["aktenzeichen"] and az_kern(u["aktenzeichen"]) == az \
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


# --- Sammlung über alle Akten -------------------------------------------------------------------------


def sammlung(con: sqlite3.Connection) -> list[dict]:
    """Alle Entscheidungen, je Datei (SHA-256) einmal, mit den Akten, denen sie zugeordnet sind.

    Vertreten wird eine Entscheidung durch ihre Zeile ohne Akte, sonst durch die älteste Zuordnung; ``akten``
    nennt je Akte die Zeile, über die sie dort geöffnet oder gelöst wird.
    """
    gruppen: dict[str, dict] = {}
    for z in con.execute(
        """SELECT u.*, k.name AS akte_name FROM urteil u LEFT JOIN akte k ON k.id = u.akte_id
           ORDER BY u.akte_id IS NOT NULL, u.id"""
    ):
        g = gruppen.get(z["sha256"])
        if g is None:
            g = gruppen[z["sha256"]] = _info(z) | {"akten": [], "zugeordnet": False}
        if z["akte_id"] is not None:
            g["akten"].append({"akte_id": z["akte_id"], "name": z["akte_name"], "urteil_id": z["id"],
                               "zitat": z["zitat"]})
            g["zugeordnet"] = True
    return sorted(gruppen.values(), key=lambda g: (g["datum"] or "", g["id"]), reverse=True)


def _gleiche(con: sqlite3.Connection, urteil_id: int) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    z = con.execute("SELECT * FROM urteil WHERE id = ?", (urteil_id,)).fetchone()
    if z is None:
        raise LookupError(f"Urteil {urteil_id} gibt es nicht.")
    return z, con.execute("SELECT * FROM urteil WHERE sha256 = ? ORDER BY id", (z["sha256"],)).fetchall()


def zuordnen(con: sqlite3.Connection, urteil_id: int, akte_id: int, ablage: Path) -> dict:
    """Ordnet eine Entscheidung der Sammlung einer Akte zu.

    Steht sie noch ohne Akte in der Sammlung, wandert diese Zeile zur Akte. Gehört sie schon zu anderen Akten,
    bekommt die Akte eine eigene Zeile; eine selbst ergänzte Datei wird dafür in die Ablage der Akte kopiert.
    """
    if con.execute("SELECT 1 FROM akte WHERE id = ?", (akte_id,)).fetchone() is None:
        raise LookupError(f"Akte {akte_id} gibt es nicht.")
    z, alle = _gleiche(con, urteil_id)
    if vorhanden := next((u for u in alle if u["akte_id"] == akte_id), None):
        return {"urteil_id": vorhanden["id"], "neu": False}
    if frei := next((u for u in alle if u["akte_id"] is None), None):
        original = _verschiebe(Path(frei["original"]), frei["quelle"], ablage, akte_id)
        with con:
            con.execute("UPDATE urteil SET akte_id = ?, original = ? WHERE id = ?",
                        (akte_id, str(original), frei["id"]))
        return {"urteil_id": frei["id"], "neu": True}
    original = Path(z["original"])
    if z["quelle"] == MANUELL:
        ziel = _ordner(ablage, akte_id)
        ziel.mkdir(parents=True, exist_ok=True)
        kopie = ziel / original.name
        if not kopie.exists():
            shutil.copyfile(original, kopie)
        original = kopie
    spalten = [k for k in z.keys() if k not in ("id", "akte_id", "zitat", "original", "hinzugefuegt_am")]
    with con:
        neu = con.execute(
            f"""INSERT INTO urteil (akte_id, zitat, original, hinzugefuegt_am, {", ".join(spalten)})
                VALUES (?, NULL, ?, ?, {", ".join("?" * len(spalten))})""",
            (akte_id, str(original), _jetzt(), *(z[k] for k in spalten)),
        ).lastrowid
        con.execute(
            """INSERT INTO urteil_abschnitt (urteil_id, nr, seite, rn, text, teil)
               SELECT ?, nr, seite, rn, text, teil FROM urteil_abschnitt WHERE urteil_id = ?""",
            (neu, z["id"]),
        )
    return {"urteil_id": neu, "neu": True}


def _verschiebe(original: Path, quelle: str, ablage: Path, akte_id: int | None) -> Path:
    """Selbst ergänzte Datei in den Ordner der neuen Zuordnung; geladene Volltexte bleiben im Roharchiv."""
    if quelle != MANUELL or not original.exists():
        return original
    ziel = _ordner(ablage, akte_id) / original.name
    if ziel == original:
        return original
    ziel.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(original, ziel)
    return ziel


def loesen(con: sqlite3.Connection, urteil_id: int, ablage: Path) -> dict:
    """Löst eine Entscheidung von ihrer Akte; sie bleibt in der Sammlung.

    Ist sie noch anderen Akten zugeordnet oder steht sie schon ohne Akte in der Sammlung, entfällt nur diese
    Zuordnung. Sonst steht sie danach „nicht zugeordnet“ in der Sammlung, die eigene Datei im Ordner der Sammlung.
    """
    z, alle = _gleiche(con, urteil_id)
    if z["akte_id"] is None:
        return {"urteil_id": urteil_id, "geloest": False}
    if len(alle) > 1:
        entfernen(con, urteil_id, ablage)
        return {"urteil_id": next(u["id"] for u in alle if u["id"] != urteil_id), "geloest": True}
    original = _verschiebe(Path(z["original"]), z["quelle"], ablage, None)
    with con:
        con.execute("UPDATE urteil SET akte_id = NULL, zitat = NULL, original = ? WHERE id = ?",
                    (str(original), urteil_id))
    return {"urteil_id": urteil_id, "geloest": True}


def aus_sammlung_entfernen(con: sqlite3.Connection, urteil_id: int, ablage: Path) -> dict:
    """Entfernt eine Entscheidung ganz: aus der Sammlung und aus allen Akten, denen sie zugeordnet ist."""
    _z, alle = _gleiche(con, urteil_id)
    hinweise = [h for u in alle if (h := entfernen(con, u["id"], ablage)["hinweis"])]
    return {"entfernt": len(alle), "hinweise": hinweise}


MAX_TREFFER = 200


def suche(con: sqlite3.Connection, suchtext: str) -> dict:
    """Volltextsuche in den gespeicherten Entscheidungen: je Entscheidung die Fundstellen mit Randnummer."""

    fts = abfrage(suchtext)
    if not fts:
        return {"urteile": [], "treffer": 0}
    zeilen = con.execute(
        f"""SELECT u.id AS urteil_id, u.sha256, a.nr, a.rn, bm25(urteil_fts) AS gewicht,
                   highlight(urteil_fts, 0, '{_AUF}', '{_ZU}') AS markiert
            FROM urteil_fts
            JOIN urteil_abschnitt a ON a.rowid = urteil_fts.rowid
            JOIN urteil u ON u.id = a.urteil_id
            WHERE urteil_fts MATCH ?
            ORDER BY gewicht
            LIMIT {MAX_TREFFER * 20}""",
        (fts,),
    ).fetchall()
    # Je Datei nur eine Zeile auswerten; Kopien in weiteren Akten haben denselben Text.
    zeile_je_datei: dict[str, int] = {}
    gruppen: dict[str, dict] = {}
    for z in zeilen:
        if zeile_je_datei.setdefault(z["sha256"], z["urteil_id"]) != z["urteil_id"]:
            continue
        g = gruppen.setdefault(z["sha256"], {"sha256": z["sha256"], "gewicht": z["gewicht"], "fundstellen": []})
        for start, ende, text, _wort in _treffer(z["markiert"]):
            g["fundstellen"].append({"nr": z["nr"], "rn": z["rn"], "ausschnitt": _ausschnitt(text, start, ende)})
            break  # je Absatz der erste Treffer genügt für die Liste
    ergebnis = sorted(gruppen.values(), key=lambda g: g["gewicht"])[:MAX_TREFFER]
    for g in ergebnis:
        g["fundstellen"].sort(key=lambda f: f["nr"])
        del g["gewicht"]
    return {"urteile": ergebnis, "treffer": sum(len(g["fundstellen"]) for g in ergebnis)}


# --- Online-Recherche: Treffer ansehen und in die Sammlung übernehmen ------------------------------------


def vorschau(daten: bytes, quelle: str, treffer: dict | None = None) -> dict:
    """Liest einen geladenen Volltext zur Ansicht, ohne ihn zu speichern (Form wie ``volltext``, ``id`` None)."""
    leser, herkunft, _ordner_name, _endung = _QUELLEN[quelle]
    v = leser(daten, treffer)
    return {"id": None, "akte_id": None, "zitat": None, "gericht": v.gericht, "aktenzeichen": v.aktenzeichen,
            "datum": v.datum, "quelle": quelle, "herkunft": herkunft, "dateiname": _dateiname(quelle, v.doknr),
            "format": quelle,
            "sha256": None, "lesart": "datei", "hinzugefuegt_am": None, "doknr": v.doknr, "hinweise": [],
            "kopf": {"spruchkoerper": v.spruchkoerper, "doktyp": v.doktyp, "normen": v.normen,
                     "vorinstanz": v.vorinstanz, "titel": v.titel},
            "abschnitte": [{"nr": i, "seite": None, "rn": a.rn, "text": a.text, "teil": a.teil}
                           for i, a in enumerate(v.absaetze, 1)]}


def in_sammlung(con: sqlite3.Connection, daten: bytes, quelle: str, archiv: Path,
                treffer: dict | None = None) -> dict:
    """Übernimmt einen online gefundenen Volltext in die Sammlung (ohne Akte). Steht dieselbe Datei schon in der
    Sammlung oder in einer Akte, bleibt es bei der vorhandenen Entscheidung."""
    if quelle not in _QUELLEN:
        raise ValueError(f"Unbekannte Quelle: {quelle!r}")
    vorhanden = con.execute("SELECT id FROM urteil WHERE sha256 = ? ORDER BY akte_id IS NOT NULL, id",
                            (hashlib.sha256(daten).hexdigest(),)).fetchone()
    if vorhanden:
        return {"urteil_id": vorhanden["id"], "neu": False}
    return {"urteil_id": _speichere_volltext(con, None, None, daten, archiv, quelle, treffer), "neu": True}


def gespeichert(con: sqlite3.Connection, treffer: list[dict]) -> list[dict]:
    """Ergänzt Treffer einer Online-Suche um ``urteil_id``, wenn die Entscheidung schon gespeichert ist."""
    ids: dict[tuple[str, str], int] = {}
    for z in con.execute(
            "SELECT id, quelle, doknr FROM urteil WHERE doknr IS NOT NULL ORDER BY akte_id IS NOT NULL, id"):
        ids.setdefault((z["quelle"], z["doknr"]), z["id"])
    return [t | {"urteil_id": ids.get((t["quelle"], t["doknr"]))} for t in treffer]
