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
from .ki import anbieter as ki_anbieter


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
    ks = sub.add_parser("ki-status", help="Prüfen, ob das lokale Sprachmodell (Ollama, LM Studio) erreichbar ist")
    kp = sub.add_parser("ki-pruefen", help="Testakte einlesen und Widersprüche mit dem Sprachmodell suchen")
    kp.add_argument("ordner", type=Path, help="Ordner mit den Dokumenten (Unterordner werden mitgelesen)")
    kp.add_argument("--erwartungen", type=Path, help="erwartungen.json der Testakte zum Abgleich")
    kp.add_argument("--zusammenfassung", action="store_true", help="auch die Akte zusammenfassen")
    for k in (ks, kp):
        k.add_argument("--anbieter", choices=["ollama", "lmstudio"], help="Programm statt des gespeicherten")
        k.add_argument("--endpunkt", help="Adresse, Voreinstellung je Programm (Ollama :11434, LM Studio :1234)")
        k.add_argument("--modell", help="Modell statt des gespeicherten, z. B. qwen3:14b")
        k.add_argument("--kontext", type=int, help="Kontext in Token (Voreinstellung 16384)")

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
    if a.befehl == "ki-status":
        e = _ki_einstellungen(a, db_pfad)
        print(json.dumps(ki_anbieter.status(e), ensure_ascii=False, indent=2))
        return 0
    if a.befehl == "ki-pruefen":
        from .ki import pruefen

        e = _ki_einstellungen(a, db_pfad)
        return pruefen.main(a.ordner, e, a.erwartungen, a.zusammenfassung)

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


def _ki_einstellungen(a: argparse.Namespace, db_pfad: Path) -> ki_anbieter.KiEinstellungen:
    """Gespeicherte Einstellungen, überschrieben durch die Optionen der Kommandozeile."""
    e = ki_anbieter.lade_einstellungen(db_pfad.parent / "ki.json")
    if a.anbieter:
        e.anbieter = ki_anbieter.OPENAI if a.anbieter == "lmstudio" else ki_anbieter.OLLAMA
        e.endpunkt = ki_anbieter.ANBIETER[e.anbieter]["endpunkt"]
        if not a.modell:
            e.modell = ""
    if a.endpunkt:
        e.endpunkt = a.endpunkt
    if a.modell:
        e.modell = a.modell
    if a.kontext:
        e.kontext = a.kontext
    if not e.modell:
        # Kein Modell angegeben: das einzige bzw. erste installierte nehmen.
        modelle = ki_anbieter.status(e)["modelle"]
        if modelle:
            e.modell = modelle[0]["name"]
    return e.pruefen()


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
