"""JSON-RPC über stdin/stdout für die Desktop-App.

Der Kern öffnet bewusst keinen Netzwerkport: Die App startet ihn als
Kindprozess und tauscht zeilenweise JSON aus. So kann kein anderer Prozess
oder eine Webseite auf Akteninhalte zugreifen.

Anfrage:  {"id": 1, "method": "gesetze.suche", "params": {"text": "Schadensersatz"}}
Antwort:  {"id": 1, "result": [...]}  oder  {"id": 1, "error": {"message": "..."}}
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import __version__, db, einstellungen
from .gesetze import quelle, wissensbasis

log = logging.getLogger("juracore.rpc")


class Kern:
    def __init__(self, db_pfad: Path, archiv: Path):
        self.con = db.oeffne(db_pfad)
        self.archiv = archiv
        self.eigene_liste = Path(db_pfad).parent / "gesetze.json"
        self.methoden: dict[str, Callable[..., Any]] = {
            "ping": lambda: {"version": __version__},
            "gesetze.liste": lambda: db.gesetze(self.con),
            "gesetze.verfuegbar": lambda: quelle.voreinstellung(self.eigene_liste),
            "gesetze.importieren": self.importieren,
            "gesetze.importieren_datei": self.importieren_datei,
            "gesetze.suche": lambda text, gesetz=None, limit=20: wissensbasis.suche(self.con, text, gesetz, limit),
            "gesetze.norm": lambda gesetz, nummer, fassung_id=None: wissensbasis.norm(
                self.con, gesetz, nummer, fassung_id
            ),
            "zitat.aufloesen": lambda zitat, fassung_id=None: wissensbasis.loese_zitat(self.con, zitat, fassung_id),
        }

    def importieren(self, gesetze: list[str]) -> list[dict]:
        ergebnisse = []
        for abk in gesetze:
            try:
                roh = quelle.lade_gesetz(abk, self.archiv, gesetze=quelle.voreinstellung(self.eigene_liste))
                ergebnisse.append(wissensbasis.importiere(self.con, roh, roh.abk))
            except quelle.NichtGeaendert:
                ergebnisse.append({"abk": abk.upper(), "neu": False, "hinweis": "Unverändert seit letztem Abruf."})
            except (ValueError, OSError) as fehler:
                # Ein fehlerhaftes Gesetz soll die übrigen nicht aufhalten.
                log.warning("Import von %s fehlgeschlagen: %s", abk, fehler)
                ergebnisse.append({"abk": abk.upper(), "neu": False, "fehler": str(fehler)})
        return ergebnisse

    def importieren_datei(self, pfad: str) -> dict:
        roh = quelle.lies_datei(Path(pfad), self.archiv)
        return wissensbasis.importiere(self.con, roh)

    def bearbeite(self, zeile: str) -> dict:
        anfrage_id = None
        try:
            anfrage = json.loads(zeile)
            anfrage_id = anfrage.get("id")
            methode = self.methoden.get(anfrage.get("method", ""))
            if methode is None:
                raise LookupError(f"Unbekannte Methode: {anfrage.get('method')!r}")
            params = anfrage.get("params") or {}
            ergebnis = methode(**params) if isinstance(params, dict) else methode(*params)
            return {"id": anfrage_id, "result": ergebnis}
        except (ValueError, LookupError, TypeError, OSError, sqlite3.Error) as fehler:
            log.warning("Fehler bei Anfrage %s: %s", anfrage_id, fehler)
            return {"id": anfrage_id, "error": {"message": str(fehler), "typ": type(fehler).__name__}}


def serve(db_pfad: Path | None = None, archiv: Path | None = None) -> None:
    kern = Kern(db_pfad or einstellungen.datenbank(), archiv or einstellungen.roharchiv())
    # Unabhängig von der Systemeinstellung (Windows: cp1252) immer UTF-8 und "\n" sprechen.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    for zeile in sys.stdin:
        if not zeile.strip():
            continue
        antwort = kern.bearbeite(zeile)
        sys.stdout.write(json.dumps(antwort, ensure_ascii=False) + "\n")
        sys.stdout.flush()
