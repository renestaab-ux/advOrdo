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
from .abgleich import abgleich
from .dokumente import akte, ocr, urteile
from .gesetze import quelle, wissensbasis
from .ki import anbieter as ki_anbieter
from .ki import speicher as ki_speicher
from .ki.analyse import Analyse
from .ki.auftraege import Auftraege
from .rechtsprechung import verzeichnis

log = logging.getLogger("juracore.rpc")


class Kern:
    def __init__(self, db_pfad: Path, archiv: Path):
        self.con = db.oeffne(db_pfad)
        self.archiv = archiv
        self.eigene_liste = Path(db_pfad).parent / "gesetze.json"
        # Akten getrennt von der Wissensbasis: eigene Datenbank, Originale je Akte in einem eigenen Ordner.
        self.akten_pfad = Path(db_pfad).parent / "akten.sqlite"
        self.akten = akte.oeffne(self.akten_pfad)
        self.ablage = Path(db_pfad).parent / "akten"
        # Sprachmodell: Einstellungen in ki.json, Analysen als Hintergrundaufträge, Ergebnisse in akten.sqlite.
        ki_speicher.einrichten(self.akten)
        self.ki_datei = Path(db_pfad).parent / "ki.json"
        self.ki_fabrik = ki_anbieter.erzeuge
        self.auftraege = Auftraege()
        self.methoden: dict[str, Callable[..., Any]] = {
            "ping": lambda: {"version": __version__},
            "gesetze.liste": lambda: db.gesetze(self.con),
            "gesetze.verfuegbar": lambda: quelle.voreinstellung(self.eigene_liste),
            "gesetze.importieren": self.importieren,
            "gesetze.importieren_datei": self.importieren_datei,
            "gesetze.suche": lambda text, gesetz=None, limit=20: wissensbasis.suche(self.con, text, gesetz, limit),
            "gesetze.norm": lambda gesetz, nummer, fassung_id=None, typ=None: wissensbasis.norm(
                self.con, gesetz, nummer, fassung_id, typ
            ),
            "zitat.aufloesen": lambda zitat, fassung_id=None: wissensbasis.loese_zitat(self.con, zitat, fassung_id),
            "ocr.status": ocr.status,
            "akten.liste": lambda: akte.akten(self.akten),
            "akten.anlegen": lambda name: akte.akte_anlegen(self.akten, name),
            "akten.dokumente": lambda akte_id: akte.dokumente(self.akten, akte_id),
            "akten.loeschen": lambda akte_id: akte.akte_loeschen(self.akten, akte_id, self.ablage),
            "akten.importieren": lambda akte_id, pfad, tags=None, herkunft=None: akte.importiere(
                self.akten, self.con, akte_id, pfad, self.ablage, tags=tags, herkunft=herkunft
            ),
            "akten.ordner_pruefen": akte.ordner_pruefen,
            "akten.dokument_loeschen": lambda dokument_id: akte.dokument_loeschen(
                self.akten, dokument_id, self.ablage
            ),
            "akten.tags_setzen": lambda dokument_id, tags: akte.tags_setzen(self.akten, dokument_id, tags),
            "akten.dokument": lambda dokument_id: akte.dokument(self.akten, dokument_id),
            "akten.normen": lambda akte_id: akte.normen(self.akten, akte_id),
            "akten.zitate_pruefen": lambda akte_id: akte.zitate_neu_pruefen(self.akten, self.con, akte_id),
            "akten.rechtsprechung": lambda akte_id: akte.rechtsprechung(self.akten, self.con, akte_id),
            "akten.urteil_ergaenzen": lambda akte_id, pfad, gericht, aktenzeichen=None, datum=None, zitat=None,
                herkunft=None: urteile.ergaenzen(self.akten, akte_id, pfad, self.ablage, gericht, aktenzeichen, datum,
                                                 zitat, herkunft),
            "akten.urteile": lambda akte_id: urteile.liste(self.akten, akte_id),
            "rechtsprechung.eigene": lambda: urteile.uebersicht(self.akten),
            "akten.urteil": lambda urteil_id: urteile.volltext(self.akten, urteil_id),
            "akten.urteil_entfernen": lambda urteil_id: urteile.entfernen(self.akten, urteil_id, self.ablage),
            "rechtsprechung.stand": lambda: verzeichnis.stand(self.con),
            "rechtsprechung.laden": self.rechtsprechung_laden,
            "rechtsprechung.laden_datei": self.rechtsprechung_laden_datei,
            "akten.abgleich": lambda akte_id, dokument_ids=None: abgleich.abgleich(self.akten, akte_id, dokument_ids),
            "ki.status": lambda: ki_anbieter.status(ki_anbieter.lade_einstellungen(self.ki_datei)),
            "ki.einstellungen_setzen": self.ki_einstellungen_setzen,
            "ki.starten": self.ki_starten,
            "ki.auftrag": self.auftraege.status,
            "ki.laufend": lambda: (a.als_dict() if (a := self.auftraege.laufend()) else None),
            "ki.abbrechen": self.auftraege.abbrechen,
            "ki.ergebnisse": lambda akte_id: ki_speicher.ergebnisse(
                self.akten, akte_id, ki_anbieter.lade_einstellungen(self.ki_datei).modell
            ),
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

    def ki_einstellungen_setzen(self, anbieter: str, endpunkt: str, modell: str = "", kontext: int = 16384) -> dict:
        e = ki_anbieter.KiEinstellungen(anbieter, endpunkt, modell, kontext)
        ki_anbieter.speichere_einstellungen(self.ki_datei, e)
        return ki_anbieter.status(e)

    KI_AUFGABEN = ("zusammenfassung_dokument", "zusammenfassung_akte", "widersprueche", "chronologie")

    def ki_starten(
        self, aufgabe: str, akte_id: int | None = None, dokument_id: int | None = None,
        dokument_ids: list[int] | None = None, neu: bool = False,
    ) -> dict:
        """Startet eine Analyse im Hintergrund; Fortschritt und Ergebnis liefert ``ki.auftrag``."""
        if aufgabe not in self.KI_AUFGABEN:
            raise ValueError(f"Unbekannte Aufgabe: {aufgabe!r}")
        if (dokument_id if aufgabe == "zusammenfassung_dokument" else akte_id) is None:
            raise ValueError("Für diese Aufgabe fehlt die Akte bzw. das Dokument.")
        e = ki_anbieter.lade_einstellungen(self.ki_datei)
        if not e.modell:
            raise ValueError("Kein Sprachmodell gewählt. Bitte unter „Einstellungen“ ein Modell auswählen.")
        modell = self.ki_fabrik(e)

        def arbeit(auftrag) -> dict:
            # Eigene Verbindung: SQLite-Verbindungen gehören zu dem Thread, der sie geöffnet hat.
            con = akte.oeffne(self.akten_pfad)
            try:
                analyse = Analyse(con, modell, e.kontext, auftrag, neu=bool(neu))
                if aufgabe == "zusammenfassung_dokument":
                    return analyse.zusammenfassung_dokument(int(dokument_id))
                if aufgabe == "zusammenfassung_akte":
                    return analyse.zusammenfassung_akte(int(akte_id))
                if aufgabe == "chronologie":
                    return analyse.chronologie(int(akte_id))
                return analyse.widersprueche(int(akte_id), dokument_ids)
            finally:
                con.close()

        return self.auftraege.starte(aufgabe, arbeit)

    def rechtsprechung_laden(self) -> dict:
        """Lädt das Verzeichnis der Bundesrechtsprechung (öffentliche Liste, keine Akteninhalte)."""
        daten, sha, archivpfad = verzeichnis.lade(self.archiv)
        return verzeichnis.importiere(self.con, daten, verzeichnis.URL, sha, archivpfad)

    def rechtsprechung_laden_datei(self, pfad: str) -> dict:
        daten = Path(pfad).read_bytes()
        sha, archivpfad = verzeichnis.archiviere(daten, self.archiv)
        return verzeichnis.importiere(self.con, daten, str(pfad), sha, archivpfad)

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
        except (ValueError, LookupError, TypeError, OSError, RuntimeError, sqlite3.Error) as fehler:
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
