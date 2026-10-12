"""Kommandozeile: ``python -m juracore …``"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import db, einstellungen, rpc
from .dokumente import lesen, ocr
from .gesetze import quelle, wissensbasis
from .gesetze.zitate import finde_zitate


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="juracore", description="Analysekern Juristischer Datenabgleich")
    p.add_argument("--db", type=Path, help="Pfad der Datenbank (Standard: Datenverzeichnis)")
    p.add_argument("--archiv", type=Path, help="Pfad des Roharchivs (Standard: Datenverzeichnis)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="befehl", required=True)

    sub.add_parser("serve", help="JSON-RPC über stdin/stdout für die Desktop-App")
    imp = sub.add_parser("import", help="Gesetze von gesetze-im-internet.de laden (z. B. BGB ZPO)")
    imp.add_argument("gesetze", nargs="+")
    imd = sub.add_parser("import-datei", help="Lokale GII-Datei (.xml/.zip) importieren")
    imd.add_argument("pfad", type=Path)
    su = sub.add_parser("suche", help="Volltextsuche in den Gesetzen")
    su.add_argument("text")
    su.add_argument("--gesetz")
    zi = sub.add_parser("zitat", help='Zitat auflösen, z. B. "§ 280 Abs. 1 S. 2 BGB"')
    zi.add_argument("zitat")
    sub.add_parser("liste", help="Importierte Gesetze und Fassungen")
    le = sub.add_parser("lesen", help="Dokument (PDF, DOCX, TXT, MD) lesen und Normzitate prüfen, ohne es zu speichern")
    le.add_argument("pfad", type=Path)
    le.add_argument("--ohne-ocr", action="store_true", help="Bildseiten nicht per Texterkennung lesen")
    sub.add_parser("ocr", help="Prüfen, ob die Texterkennung (Tesseract, Deutsch) verfügbar ist")

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, stream=sys.stderr)
    db_pfad = a.db or einstellungen.datenbank()
    archiv = a.archiv or einstellungen.roharchiv()

    if a.befehl == "serve":
        rpc.serve(db_pfad, archiv)
        return 0
    if a.befehl == "ocr":
        print(json.dumps(ocr.status(), ensure_ascii=False, indent=2))
        return 0

    con = db.oeffne(db_pfad)
    if a.befehl == "import":
        ergebnis = rpc.Kern(db_pfad, archiv).importieren(a.gesetze)
    elif a.befehl == "import-datei":
        ergebnis = wissensbasis.importiere(con, quelle.lies_datei(a.pfad, archiv))
    elif a.befehl == "suche":
        ergebnis = wissensbasis.suche(con, a.text, a.gesetz)
    elif a.befehl == "zitat":
        ergebnis = wissensbasis.loese_zitat(con, a.zitat)
    elif a.befehl == "lesen":
        ergebnis = _lesen(con, a.pfad, not a.ohne_ocr)
    else:
        ergebnis = db.gesetze(con)
    print(json.dumps(ergebnis, ensure_ascii=False, indent=2))
    return 0


def _lesen(con, pfad: Path, mit_ocr: bool) -> dict:
    dok = lesen.lies(pfad, mit_ocr)
    abschnitte = []
    for a in dok.abschnitte:
        zitate = []
        for z in finde_zitate(a.text):
            beleg = wissensbasis.loese_zitat(con, z)
            zitate.append({"zitat": str(z), "status": beleg["status"], "hinweis": beleg["hinweis"]})
        abschnitte.append({"nr": a.nr, "seite": a.seite, "rn": a.rn, "text": a.text, "zitate": zitate})
    return {"format": dok.format, "lesart": dok.lesart, "ocr_konfidenz": dok.ocr_konfidenz,
            "hinweise": dok.hinweise, "abschnitte": abschnitte}


if __name__ == "__main__":
    raise SystemExit(main())
