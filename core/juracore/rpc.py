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
from .dokumente import akte, ansicht, ocr, suche, urteile
from .eigene import daten as eigene
from .eigene.felder import FELDER, FORMEN
from .gesetze import quelle, wissensbasis
from .ki import anbieter as ki_anbieter
from .ki import chat as ki_chat
from .ki import speicher as ki_speicher
from .ki.analyse import Analyse
from .ki.auftraege import Auftraege
from .rechner import basiszins, fristen, verzugszinsen
from .rechtsprechung import online, verzeichnis
from .umgebungen import Umgebungen

log = logging.getLogger("juracore.rpc")


class Kern:
    def __init__(self, db_pfad: Path, archiv: Path):
        self.con = db.oeffne(db_pfad)
        self.archiv = archiv
        self.eigene_liste = Path(db_pfad).parent / "gesetze.json"
        # Akten getrennt von der Wissensbasis: eigene Datenbank, Originale je Akte in einem eigenen Ordner.
        # Beides gehört zur aktiven Arbeitsumgebung; die Wissensbasis teilen sich alle Umgebungen.
        self.umgebungen = Umgebungen(Path(db_pfad).parent)
        self._oeffne_akten(self.umgebungen.ordner())
        self.ki_datei = Path(db_pfad).parent / "ki.json"
        self.schluessel_datei = Path(db_pfad).parent / "ki-schluessel.json"
        self.ki_fabrik = ki_anbieter.erzeuge_aktiv
        self.auftraege = Auftraege()
        self.basiszins_datei = Path(db_pfad).parent / "basiszins.json"
        self.quellen_datei = Path(db_pfad).parent / "rechtsprechung-quellen.json"
        self.methoden: dict[str, Callable[..., Any]] = {
            "ping": lambda: {"version": __version__},
            "umgebungen.liste": self.umgebungen.liste,
            "umgebungen.anlegen": self.umgebungen.anlegen,
            "umgebungen.umbenennen": self.umgebungen.umbenennen,
            "umgebungen.loeschen": self.umgebungen.loeschen,
            "umgebungen.wechseln": self.umgebung_wechseln,
            "eigene.felder": lambda: {"felder": FELDER, "formen": FORMEN},
            "eigene.stand": lambda: eigene.stand(self.akten),
            "eigene.kurzstand": lambda: eigene.kurzstand(self.akten),
            "eigene.form_setzen": lambda form: eigene.form_setzen(self.akten, form),
            "eigene.organisation_speichern": lambda daten: eigene.organisation_speichern(self.akten, daten),
            "eigene.inhaber_speichern": lambda daten, mitgliedschaft=None: eigene.inhaber_speichern(
                self.akten, daten, mitgliedschaft),
            "eigene.inhaber_waehlen": lambda person_id: eigene.inhaber_waehlen(self.akten, person_id),
            "eigene.einheit_speichern": lambda art, daten, einheit_id=None: eigene.einheit_speichern(
                self.akten, art, daten, einheit_id),
            "eigene.person_speichern": lambda organisation_id, daten, mitgliedschaft=None, person_id=None:
                eigene.person_speichern(self.akten, organisation_id, daten, mitgliedschaft, person_id),
            "eigene.archivieren": lambda objekt, objekt_id, archiviert=True: eigene.archivieren(
                self.akten, objekt, objekt_id, archiviert),
            "eigene.loeschen": lambda objekt, objekt_id: eigene.loeschen(self.akten, objekt, objekt_id),
            "eigene.duplizieren": lambda organisation_id: eigene.duplizieren(self.akten, organisation_id),
            "eigene.assistent_fertig": lambda fertig=True: eigene.assistent_fertig(self.akten, fertig),
            "eigene.aenderungen": lambda limit=50: eigene.aenderungen(self.akten, limit),
            "eigene.exportieren": lambda pfad: eigene.exportieren(self.akten, pfad),
            "eigene.importieren": lambda pfad, ersetzen=False: eigene.importieren(self.akten, pfad, ersetzen),
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
            "akten.normen": lambda akte_id, dokument_id=None: akte.normen(self.akten, akte_id, dokument_id),
            "akten.seitenbild": lambda dokument_id, seite, breite=1000, begriffe=None: ansicht.seitenbild(
                self.akten, dokument_id, seite, breite, begriffe),
            "akten.suche": lambda text, akte_id=None: suche.suche(self.akten, text, akte_id),
            "akten.zitate_pruefen": lambda akte_id: akte.zitate_neu_pruefen(self.akten, self.con, akte_id),
            "akten.rechtsprechung": lambda akte_id, dokument_id=None: akte.rechtsprechung(
                self.akten, self.con, akte_id, dokument_id, self._online_quellen()),
            "akten.online_pruefen": self.online_pruefen,
            "rechtsprechung.quellen": lambda: online.einstellungen(self.quellen_datei),
            "rechtsprechung.quellen_setzen": lambda neuris: online.einstellungen_setzen(self.quellen_datei, neuris),
            "akten.urteil_ergaenzen": lambda akte_id, pfad, gericht, aktenzeichen=None, datum=None, zitat=None,
                herkunft=None: urteile.ergaenzen(self.akten, akte_id, pfad, self.ablage, gericht, aktenzeichen, datum,
                                                 zitat, herkunft),
            "akten.urteile": lambda akte_id: urteile.liste(self.akten, akte_id),
            "akten.volltexte_laden": lambda akte_id, zitat=None: urteile.volltexte_laden(
                self.akten, self.con, akte_id, self.archiv, zitat=zitat),
            "rechtsprechung.eigene": lambda: urteile.uebersicht(self.akten),
            "akten.urteil": lambda urteil_id: urteile.volltext(self.akten, urteil_id),
            "akten.urteil_entfernen": lambda urteil_id: urteile.entfernen(self.akten, urteil_id, self.ablage),
            "rechtsprechung.stand": lambda: verzeichnis.stand(self.con),
            "rechtsprechung.laden": self.rechtsprechung_laden,
            "rechtsprechung.laden_datei": self.rechtsprechung_laden_datei,
            "akten.abgleich": lambda akte_id, dokument_ids=None: abgleich.abgleich(self.akten, akte_id, dokument_ids),
            "ki.status": self.ki_status,
            "ki.modus": self.ki_modus,
            "ki.einstellungen_setzen": self.ki_einstellungen_setzen,
            "ki.extern_setzen": self.ki_extern_setzen,
            "ki.starten": self.ki_starten,
            "ki.auftrag": self.auftraege.status,
            "ki.laufend": lambda: (a.als_dict() if (a := self.auftraege.laufend()) else None),
            "ki.abbrechen": self.auftraege.abbrechen,
            "ki.ergebnisse": lambda akte_id: ki_speicher.ergebnisse(
                self.akten, akte_id, ki_anbieter.lade_einstellungen(self.ki_datei).aktives_modell
            ),
            "ki.chat_verlauf": lambda akte_id, dokument_id=None: ki_chat.verlauf(self.akten, akte_id, dokument_id),
            "ki.chat_fragen": self.ki_chat_fragen,
            "rechner.verzugszinsen": lambda **p: verzugszinsen.berechne(
                verzugszinsen.aus_params(p), basiszins.lade(self.basiszins_datei)),
            "rechner.frist": lambda **p: fristen.aus_params(p),
            "rechner.basiszins": lambda: basiszins.stand(self.basiszins_datei),
            "rechner.basiszins_eintragen": lambda ab, satz: basiszins.eintragen(self.basiszins_datei, ab, satz),
            "rechner.basiszins_entfernen": lambda ab: basiszins.entfernen(self.basiszins_datei, ab),
            "ki.chat_leeren": lambda akte_id, dokument_id=None: ki_chat.leeren(self.akten, akte_id, dokument_id),
        }

    def _oeffne_akten(self, ordner: Path) -> None:
        self.akten_pfad = ordner / "akten.sqlite"
        self.akten = akte.oeffne(self.akten_pfad)
        self.ablage = ordner / "akten"
        # Sprachmodell: Einstellungen in ki.json, Analysen als Hintergrundaufträge, Ergebnisse in akten.sqlite.
        ki_speicher.einrichten(self.akten)
        ki_chat.einrichten(self.akten)
        # Eigene Daten (Profil, Kanzlei bzw. Unternehmen) gehören ebenfalls zur Umgebung.
        eigene.einrichten(self.akten)

    def umgebung_wechseln(self, umgebung_id: str) -> dict:
        """Schließt die Akten der aktiven Umgebung und öffnet die der gewählten."""
        if self.auftraege.laufend():
            raise RuntimeError("Eine Analyse läuft noch. Bitte warten oder sie abbrechen, dann die Umgebung wechseln.")
        ordner = self.umgebungen.aktivieren(umgebung_id)
        self.akten.close()
        self._oeffne_akten(ordner)
        return self.umgebungen.liste()

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

    def _schluessel(self, e: ki_anbieter.KiEinstellungen) -> str | None:
        return ki_anbieter.lade_schluessel(self.schluessel_datei, e.extern_anbieter)

    def ki_status(self, verbindung: bool = False) -> dict:
        """Stand des gewählten Modells; ``verbindung`` fragt auch den externen Anbieter (nur die Modellliste)."""
        e = ki_anbieter.lade_einstellungen(self.ki_datei)
        return ki_anbieter.gesamtstatus(e, self._schluessel(e), bool(verbindung))

    def ki_modus(self) -> dict:
        """Ohne Anfrage an ein Modell: ob Dokumentinhalte das Gerät verlassen (für die Anzeige in der Navigation)."""
        e = ki_anbieter.lade_einstellungen(self.ki_datei)
        titel = ki_anbieter.EXTERNE[e.extern_anbieter]["titel"] if e.extern else None
        return {"aktiv": ki_anbieter.EXTERN if e.extern else ki_anbieter.LOKAL, "titel": titel,
                "modell": e.aktives_modell}

    def ki_einstellungen_setzen(self, anbieter: str, endpunkt: str, modell: str = "", kontext: int = 16384) -> dict:
        """Das lokale Modell; die Einstellungen der externen KI bleiben, wie sie sind."""
        e = ki_anbieter.lade_einstellungen(self.ki_datei)
        e.anbieter, e.endpunkt, e.modell, e.kontext = anbieter, endpunkt, modell, kontext
        ki_anbieter.speichere_einstellungen(self.ki_datei, e)
        return ki_anbieter.gesamtstatus(e, self._schluessel(e))

    def ki_extern_setzen(
        self, freigegeben: bool, anbieter: str | None = None, modell: str | None = None, adresse: str | None = None,
        kontext: int | None = None, aktiv: str | None = None, schluessel: str | None = None,
        schluessel_loeschen: bool = False, verbindung: bool = False,
    ) -> dict:
        """Schalter „Externe KI einbinden“, Anbieter, Modell, Schlüssel und die Wahl lokal/extern.

        Ausschalten setzt die Wahl auf lokal zurück; hinterlegte Schlüssel bleiben, bis sie gelöscht werden.
        """
        e = ki_anbieter.lade_einstellungen(self.ki_datei)
        e.extern_freigegeben = bool(freigegeben)
        if anbieter is not None:
            e.extern_anbieter = anbieter
        if modell is not None:
            e.extern_modell = modell
        if adresse is not None:
            e.extern_adresse = adresse
        if kontext is not None:
            e.extern_kontext = kontext
        if aktiv is not None:
            e.aktiv = aktiv
        if aktiv == ki_anbieter.EXTERN and not e.extern_freigegeben:
            raise ValueError("Externe KI ist nicht eingebunden; zuerst den Schalter einschalten.")
        e.pruefen()
        if schluessel_loeschen:
            ki_anbieter.speichere_schluessel(self.schluessel_datei, e.extern_anbieter, None)
        elif schluessel:
            ki_anbieter.speichere_schluessel(self.schluessel_datei, e.extern_anbieter, schluessel)
        ki_anbieter.speichere_einstellungen(self.ki_datei, e)
        return ki_anbieter.gesamtstatus(e, self._schluessel(e), bool(verbindung))

    def _ki_modell(self) -> tuple[ki_anbieter.KiEinstellungen, ki_anbieter.Anbieter]:
        e = ki_anbieter.lade_einstellungen(self.ki_datei)
        if not e.aktives_modell:
            raise ValueError("Kein Sprachmodell gewählt. Bitte unter „Einstellungen“ ein Modell auswählen.")
        return e, self.ki_fabrik(e, self._schluessel(e) if e.extern else None)

    def ki_chat_fragen(self, akte_id: int, frage: str, dokument_id: int | None = None) -> dict:
        """Stellt eine Frage an die Akte bzw. an ein Dokument im Hintergrund; die Antwort liefert ``ki.auftrag``."""
        if not str(frage).strip():
            raise ValueError("Die Frage ist leer.")
        e, modell = self._ki_modell()
        extern = ki_anbieter.EXTERNE[e.extern_anbieter]["titel"] if e.extern else None

        def arbeit(auftrag) -> dict:
            con = akte.oeffne(self.akten_pfad)
            try:
                return ki_chat.frage(con, modell, e.aktiver_kontext, int(akte_id), str(frage),
                                     None if dokument_id is None else int(dokument_id), auftrag, extern)
            finally:
                con.close()

        return self.auftraege.starte("chat", arbeit)

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
        e, modell = self._ki_modell()

        def arbeit(auftrag) -> dict:
            # Eigene Verbindung: SQLite-Verbindungen gehören zu dem Thread, der sie geöffnet hat.
            con = akte.oeffne(self.akten_pfad)
            try:
                analyse = Analyse(con, modell, e.aktiver_kontext, auftrag, neu=bool(neu))
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

    def _online_quellen(self) -> set[str]:
        return online.quellen(online.einstellungen(self.quellen_datei))

    def online_pruefen(self, akte_id: int, neu: bool = False) -> dict:
        """Prüft offene Zitate einer Akte bei gesetze-bayern.de bzw. NeuRIS; gesendet wird nur das Aktenzeichen."""
        aktiv = self._online_quellen()
        ergebnis = online.pruefe(self.con, akte.rechtsprechung(self.akten, self.con, akte_id, None, aktiv), aktiv,
                                 bool(neu))
        akte.urteilszitate_neu_pruefen(self.akten, self.con, akte_id)
        return ergebnis

    def rechtsprechung_laden(self) -> dict:
        """Lädt das Verzeichnis der Bundesrechtsprechung (öffentliche Liste, keine Akteninhalte)."""
        daten, sha, archivpfad = verzeichnis.lade(self.archiv)
        return verzeichnis.importiere(self.con, daten, verzeichnis.URL, sha, archivpfad)

    def rechtsprechung_laden_datei(self, pfad: str) -> dict:
        daten = Path(pfad).read_bytes()
        sha, archivpfad = verzeichnis.archiviere(daten, self.archiv)
        return verzeichnis.importiere(self.con, daten, str(pfad), sha, archivpfad)

    def importieren_datei(self, pfad: str) -> dict:
        roh = quelle.lies_datei(Path(pfad), self.archiv, gesetze=quelle.voreinstellung(self.eigene_liste))
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
