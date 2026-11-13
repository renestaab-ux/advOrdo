"""JSON-RPC über stdin/stdout für die Desktop-App.

Der Kern öffnet bewusst keinen Netzwerkport: Die App startet ihn als
Kindprozess und tauscht zeilenweise JSON aus. So kann kein anderer Prozess
oder eine Webseite auf Akteninhalte zugreifen.

Anfrage:  {"id": 1, "method": "gesetze.suche", "params": {"text": "Schadensersatz"}}
Antwort:  {"id": 1, "result": [...]}  oder  {"id": 1, "error": {"message": "..."}}
"""

from __future__ import annotations

import http.client
import json
import logging
import sqlite3
import sys
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import (
    db,
    einstellungen,
    gerichte,
    hintergrund,
    justizadressen,
    kernmethoden,
    nachrichten,
    netzprotokoll,
    programme,
    zeiterfassung,
)
from .aktenverwaltung import (
    aus_dokument,
    beteiligte,
    kalender,
    kollision,
    stammdaten,
    verfahren,
)
from .aktenverwaltung import einrichten as aktenverwaltung_einrichten
from .dokumente import (
    akte,
    anmerkungen,
    fassungen,
    lesen,
    lesezeichen,
    metadaten,
    pdf_markiert,
    urteile,
)
from .eigene import daten as eigene
from .gesetze import quelle, wissensbasis
from .ki import anbieter as ki_anbieter
from .ki import chat as ki_chat
from .ki import gegenueberstellung as ki_gegenueberstellung
from .ki import leistung as ki_leistung
from .ki import metadaten as ki_metadaten
from .ki import speicher as ki_speicher
from .ki import vergleich as ki_vergleich
from .ki import wissen as ki_wissen
from .ki.analyse import Analyse
from .ki.auftraege import Auftraege
from .rechner import basiszins
from .rechtsprechung import online, recherche, verzeichnis
from .schriftstuecke import kostennote
from .schriftstuecke import vorlagen as schrift_vorlagen
from .umgebungen import Umgebungen

log = logging.getLogger("juracore.rpc")


class Kern:
    def __init__(self, db_pfad: Path, archiv: Path):
        # Hintergrundaufträge arbeiten mit eigenen Verbindungen (SQLite-Verbindungen gehören zu ihrem Thread);
        # ``con`` und ``akten`` liefern im Auftrag dessen Verbindungen, sonst die des Hauptthreads.
        self._lokal = threading.local()
        self.hintergrund = hintergrund.Hintergrund()
        self.con = db.oeffne(db_pfad)
        self.db_pfad = Path(db_pfad)
        self.archiv = archiv
        self.eigene_liste = Path(db_pfad).parent / "gesetze.json"
        self.pakete_datei = Path(db_pfad).parent / "gesetzespakete.json"
        # Akten getrennt von der Wissensbasis: eigene Datenbank, Originale je Akte in einem eigenen Ordner.
        # Beides gehört zur aktiven Arbeitsumgebung; die Wissensbasis teilen sich alle Umgebungen.
        self.umgebungen = Umgebungen(Path(db_pfad).parent)
        self._oeffne_akten(self.umgebungen.ordner())
        self.recherche = recherche.Recherche(self.con, diagnose=Path(db_pfad).parent / "diagnose")
        self.ki_datei = Path(db_pfad).parent / "ki.json"
        # Externe Programme gelten für das Gerät, nicht je Arbeitsumgebung.
        self.programme_datei = Path(db_pfad).parent / "programme.json"
        self.schluessel_datei = Path(db_pfad).parent / "ki-schluessel.json"
        self.ki_fabrik = ki_anbieter.erzeuge_aktiv
        self.auftraege = Auftraege()
        self.basiszins_datei = Path(db_pfad).parent / "basiszins.json"
        self.quellen_datei = Path(db_pfad).parent / "rechtsprechung-quellen.json"
        self.gerichtssuche_datei = Path(db_pfad).parent / justizadressen.EINSTELLUNGEN
        # Nachrichten-Feeds der Startseite gelten für das Gerät; geladen wird im Hintergrund.
        self.nachrichten = nachrichten.Nachrichten(
            Path(db_pfad).parent / "nachrichten.json", Path(db_pfad).parent / "nachrichten-cache.json")
        # Abrufe der Diagnose und des Gerichtsverzeichnisses; in Tests ohne Netz austauschbar.
        self.diagnose_oeffnen = urllib.request.urlopen
        # Jede Verbindung des Kerns wird protokolliert (Einstellungen → Diagnose); die Datei gilt für das Gerät.
        self.netzprotokoll_datei = Path(db_pfad).parent / netzprotokoll.DATEINAME
        netzprotokoll.einrichten(self.netzprotokoll_datei)
        self.methoden: dict[str, Callable[..., Any]] = {}
        for teil in kernmethoden.TEILE:
            self.methoden.update(teil.methoden(self))

    @property
    def con(self) -> sqlite3.Connection:
        """Verbindung zur Wissensbasis; in einem Hintergrundauftrag dessen eigene."""
        lokal = getattr(self._lokal, "con", None)
        return self._con if lokal is None else lokal

    @con.setter
    def con(self, wert: sqlite3.Connection) -> None:
        self._con = wert

    @property
    def akten(self) -> sqlite3.Connection:
        """Verbindung zu den Akten der aktiven Umgebung; in einem Hintergrundauftrag dessen eigene."""
        lokal = getattr(self._lokal, "akten", None)
        return self._akten if lokal is None else lokal

    @akten.setter
    def akten(self, wert: sqlite3.Connection) -> None:
        self._akten = wert

    def hintergrund_starten(self, methode: str, params: dict | list | None = None, warten: bool = False) -> dict:
        """Startet einen langen Befehl (``hintergrund.BEFEHLE``) im Hintergrund; Fortschritt und Ergebnis liefert
        ``hintergrund.auftrag``. ``warten`` führt ihn sofort aus (Tests)."""
        funktion = self.methoden.get(methode)
        if funktion is None or methode not in hintergrund.BEFEHLE:
            raise LookupError(f"{methode!r} läuft nicht im Hintergrund.")
        db_pfad, akten_pfad = self.db_pfad, self.akten_pfad

        def arbeit() -> Any:
            self._lokal.con = db.oeffne(db_pfad)
            self._lokal.akten = akte.oeffne(akten_pfad)
            try:
                return _aufrufen(funktion, params)
            finally:
                self._lokal.con.close()
                self._lokal.akten.close()
                del self._lokal.con, self._lokal.akten

        return self.hintergrund.starte(methode, arbeit, warten=bool(warten))

    def _oeffne_akten(self, ordner: Path) -> None:
        self.akten_pfad = ordner / "akten.sqlite"
        self.akten = akte.oeffne(self.akten_pfad)
        self.ablage = ordner / "akten"
        # Sprachmodell: Einstellungen in ki.json, Analysen als Hintergrundaufträge, Ergebnisse in akten.sqlite.
        ki_speicher.einrichten(self.akten)
        ki_chat.einrichten(self.akten)
        # Eigene Daten (Profil, Kanzlei bzw. Unternehmen) gehören ebenfalls zur Umgebung.
        eigene.einrichten(self.akten)
        # Aktenverwaltung: Beteiligte, Aktenzeichen, Kollisionsprüfung (verweist auf Akten und Eigene Daten).
        aktenverwaltung_einrichten(self.akten)
        # Kostennoten: vergebene Rechnungsnummern der Umgebung.
        kostennote.einrichten(self.akten)
        # Zeiterfassung: Zeiten je Akte, Stundensätze und Bearbeiter der Umgebung.
        zeiterfassung.einrichten(self.akten)
        # Markierungen und Kommentare an Dokumenten.
        anmerkungen.einrichten(self.akten)
        lesezeichen.einrichten(self.akten)

    def akten_dokumente(self, akte_id: int) -> list[dict]:
        liste = metadaten.mit_absender(self.akten, akte.dokumente(self.akten, akte_id))
        zahlen = anmerkungen.zahlen(self.akten, akte_id)
        return [d | {"anmerkungen": zahlen.get(d["id"], 0)} for d in liste]

    def _programm(self, dokument_id: int) -> dict:
        fmt = akte.dokument(self.akten, dokument_id)["dokument"]["format"]
        return programme.lade(self.programme_datei)[programme.art_fuer(fmt)]

    def extern_ansehen(self, dokument_id: int, nr: int | None = None) -> dict:
        """Schreibgeschützte Kopie im eingestellten Programm öffnen; das abgelegte Original bleibt unberührt."""
        pfad = fassungen.ansichtskopie(self.akten, self.ablage, dokument_id, nr)
        programm = self._programm(dokument_id)
        programme.starten(pfad, programm)
        return {"pfad": str(pfad), "programm": programm["programm"] or "Standardprogramm"}

    def extern_bearbeiten(self, dokument_id: int) -> dict:
        """Arbeitskopie anlegen (oder die vorhandene nehmen) und im eingestellten Programm öffnen."""
        kopie = fassungen.arbeitskopie(self.akten, self.ablage, dokument_id)
        programm = self._programm(dokument_id)
        programme.starten(Path(kopie["pfad"]), programm)
        return kopie | {"programm": programm["programm"] or "Standardprogramm"}

    def vorlage_bearbeiten(self, datei: str) -> dict:
        """Eigene Vorlage in der eingestellten Textverarbeitung öffnen; Änderungen gelten beim nächsten Erzeugen."""
        pfad = schrift_vorlagen.pfad(self.umgebungen.ordner(), datei)
        programm = programme.lade(self.programme_datei)["text"]
        programme.starten(pfad, programm)
        return {"pfad": str(pfad), "programm": programm["programm"] or "Standardprogramm"}

    def pdf_markiert(self, dokument_id: int, pfad: str, ids: list[int] | None = None) -> dict:
        """PDF-Kopie mit Markierungen schreiben und im Dateimanager zeigen, damit sie gleich zu finden ist."""
        r = pdf_markiert.schreiben(self.akten, dokument_id, pfad, ids)
        self._zeigen(r["pfad"])
        return r

    def pdf_markiert_akte(self, akte_id: int, ordner: str, ids: list[int] | None = None) -> dict:
        r = pdf_markiert.akte_schreiben(self.akten, akte_id, ordner, ids)
        if r["dateien"]:
            self._zeigen(r["dateien"][0]["pfad"])
        return r

    @staticmethod
    def _zeigen(pfad: str) -> None:
        try:
            programme.im_ordner_zeigen(Path(pfad))
        except Exception as fehler:  # Ohne Dateimanager ist die Datei trotzdem geschrieben.
            log.warning("Dateimanager nicht geöffnet: %s", fehler)

    def vorlagen_ordner(self) -> dict:
        ordner = schrift_vorlagen.ordner_anlegen(self.umgebungen.ordner())
        programme.im_ordner_zeigen(ordner)
        return {"pfad": str(ordner)}

    def im_ordner_zeigen(self, dokument_id: int) -> dict:
        """Zeigt die Arbeitskopie, sonst eine Kopie zum Ansehen im Dateimanager, nie die Ablage selbst."""
        kopie = self.akten.execute("SELECT pfad FROM arbeitskopie WHERE dokument_id = ?", (dokument_id,)).fetchone()
        pfad = Path(kopie["pfad"]) if kopie and Path(kopie["pfad"]).is_file() else fassungen.ansichtskopie(
            self.akten, self.ablage, dokument_id)
        programme.im_ordner_zeigen(pfad)
        return {"pfad": str(pfad)}

    def fassung_uebernehmen(self, dokument_id: int) -> dict:
        ergebnis = fassungen.uebernehmen(self.akten, self.con, self.ablage, dokument_id)
        akte_id = self.akten.execute("SELECT akte_id FROM dokument WHERE id = ?", (dokument_id,)).fetchone()[0]
        # Zusammenfassungen und Auswertungen beruhen auf dem alten Text.
        ergebnis["ki_verworfen"] = ki_speicher.vergessen(self.akten, akte_id, dokument_id)
        return ergebnis

    def importieren_dateien(self, akte_id: int, dateien: list[dict]) -> dict:
        """Liest Dateien nacheinander in die Akte ein. Eine unlesbare Datei hält die übrigen nicht auf; ihr Fehler
        steht im Ergebnis. Abgebrochen wird zwischen zwei Dateien bzw. zwei Seiten der Texterkennung; was bis dahin
        eingelesen ist, bleibt in der Akte."""
        ergebnisse = []
        for i, d in enumerate(dateien, 1):
            hintergrund.pruefe()
            name = d.get("name") or Path(d["pfad"]).name
            hintergrund.melde(f"Lese {i} von {len(dateien)}: {name} …", i - 1, len(dateien))
            try:
                r = akte.importiere(self.akten, self.con, akte_id, d["pfad"], self.ablage, tags=d.get("tags"),
                                    herkunft=d.get("herkunft"))
                ergebnisse.append({"name": name, "dokument_id": r["dokument_id"], "neu": r["neu"]})
            except (ValueError, LookupError, OSError, RuntimeError, sqlite3.Error) as fehler:
                log.warning("Import von %s fehlgeschlagen: %s", name, fehler)
                ergebnisse.append({"name": name, "fehler": str(fehler)})
        return {"ergebnisse": ergebnisse}

    def akte_anlegen(self, name: str, aktenzeichen: str | None = None, ohne_aktenzeichen: bool = False) -> dict:
        """Neue Akte; sie bekommt das vorgeschlagene oder das eingegebene Aktenzeichen."""
        if aktenzeichen and aktenzeichen.strip():
            stammdaten.zerlege(aktenzeichen)  # Schema prüfen, bevor etwas angelegt wird
        neu = akte.akte_anlegen(self.akten, name)
        if not ohne_aktenzeichen:
            try:
                stammdaten.vergeben(self.akten, neu["id"], aktenzeichen)
            except ValueError:
                akte.akte_loeschen(self.akten, neu["id"], self.ablage)
                raise
        return next(a for a in stammdaten.uebersicht(self.akten) if a["id"] == neu["id"])

    def akten_liste(self) -> list[dict]:
        """Aktenübersicht mit aktuellem Verfahren und nächster offener Frist bzw. nächstem Termin."""
        akten = stammdaten.uebersicht(self.akten)
        naechste = kalender.naechste_je_akte(self.akten)
        aktuelle = verfahren.aktuelle_je_akte(self.akten)
        for a in akten:
            a["verfahren"] = (aktuelle.get(a["id"]) or {}).get("bezeichnung")
            a["naechste"] = naechste.get(a["id"])
        return akten

    def kalender_vorschlaege(self, akte_id: int, dokument_id: int | None = None, land: str = "BY") -> list[dict]:
        """Vorschläge für Fristen und Termine aus einem Dokument oder aus allen Dokumenten der Akte."""
        ids = [dokument_id] if dokument_id else [z["id"] for z in self.akten.execute(
            "SELECT id FROM dokument WHERE akte_id = ? ORDER BY COALESCE(datum, importiert_am), id", (akte_id,))]
        return [v | {"dateiname": e["dateiname"]} for i in ids
                for e in [kalender.dokument_vorschlaege(self.akten, i, land)] for v in e["vorschlaege"]]

    def _eigene_namen(self, s: dict | None = None) -> list[str]:
        """Name der eigenen Kanzlei bzw. Organisation und der beauftragten Kanzleien (Eigene Daten)."""
        s = s or eigene.stand(self.akten, mit_archiv=False)
        return [n for n in (s["organisation_name"], *(k["daten"].get("name", "") for k in s["beauftragte_kanzleien"]))
                if n]

    def rubrum_lesen(self, pfad: str | None = None, dokument_id: int | None = None,
                     akte_id: int | None = None) -> dict:
        """Erkennt das Rubrum für „Akte aus Dokument“ bzw. „Verfahren aus Dokument“: aus einer Datei (ohne sie
        abzulegen) oder aus einem Dokument, das schon in der Akte liegt. Mit ``akte_id`` (bei einem Dokument der Akte
        immer) wird die Vorschau mit den Beteiligten und Verfahren dieser Akte abgeglichen."""
        if dokument_id is not None:
            z = self.akten.execute("SELECT akte_id, dateiname, lesart FROM dokument WHERE id = ?",
                                   (dokument_id,)).fetchone()
            if z is None:
                raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
            abschnitte = [dict(a) for a in self.akten.execute(
                "SELECT nr, seite, text FROM abschnitt WHERE dokument_id = ? ORDER BY nr", (dokument_id,))]
            dateiname, lesart, akte_id = z["dateiname"], z["lesart"], z["akte_id"]
        elif pfad:
            dok = lesen.lies(Path(pfad))
            abschnitte = [{"nr": a.nr, "seite": a.seite, "text": a.text} for a in dok.abschnitte]
            dateiname, lesart = Path(pfad).name, dok.lesart
        else:
            raise ValueError("Bitte eine Datei oder ein Dokument der Akte wählen.")
        s = eigene.stand(self.akten, mit_archiv=False)
        namen = self._eigene_namen(s)
        konzern = [{"id": k["id"], "name": k["daten"].get("name", "")} for k in s["konzerngesellschaften"]]
        r = aus_dokument.vorschau(self.akten, abschnitte, namen, konzern)
        if akte_id is not None:
            aus_dokument.mit_akte_abgleichen(self.akten, akte_id, r)
        r["dateiname"] = dateiname
        r["lesart"] = lesart
        r["abschnitte"] = {a["nr"]: a["text"] for a in abschnitte[:80]}
        return r

    def aus_dokument_anlegen(self, pfad: str, auswahl: dict) -> dict:
        """Neue Akte mit der bestätigten Auswahl; das Dokument wird als erstes Dokument eingelesen."""
        if not Path(pfad).is_file():
            raise FileNotFoundError(f"Datei nicht gefunden: {pfad}")
        if auswahl.get("eigene_seite") not in ("aktiv", "passiv"):
            raise ValueError("Bitte angeben, welche Seite wir vertreten.")  # vor dem Anlegen: Az. bleibt frei
        neu = self.akte_anlegen(auswahl.get("name") or "Neue Akte", auswahl.get("aktenzeichen"))
        try:
            aus_dokument.uebernehmen(self.akten, neu["id"], auswahl)
            akte.importiere(self.akten, self.con, neu["id"], pfad, self.ablage)
        except Exception:
            akte.akte_loeschen(self.akten, neu["id"], self.ablage)
            raise
        self.kollision_pruefen(neu["id"])
        return next(a for a in self.akten_liste() if a["id"] == neu["id"])

    def verfahren_aus_dokument(self, akte_id: int, auswahl: dict, pfad: str | None = None) -> list[dict]:
        """Weiteres Verfahren in einer bestehenden Akte aus der bestätigten Auswahl. Mit ``pfad`` (neues Dokument)
        wird die Datei dabei in die Akte eingelesen; scheitert die Übernahme, wird sie wieder entfernt."""
        if (auswahl.get("verfahren") or {}).get("art") not in verfahren.ARTEN:
            raise ValueError("Bitte die Art des Verfahrens wählen.")  # vor dem Einlesen prüfen
        eingelesen = akte.importiere(self.akten, self.con, akte_id, pfad, self.ablage) if pfad else None
        try:
            liste = aus_dokument.verfahren_uebernehmen(self.akten, akte_id, auswahl)
        except Exception:
            if eingelesen and eingelesen["neu"]:
                akte.dokument_loeschen(self.akten, eingelesen["dokument_id"], self.ablage)
            raise
        self.kollision_pruefen(akte_id)
        return liste

    def akten_optionen(self) -> dict:
        """Auswahllisten für Stammdaten und Beteiligte, dazu die passenden Einträge aus „Eigene Daten“."""
        s = eigene.stand(self.akten, mit_archiv=False)
        personen = [s["inhaber"]] if s["inhaber"] else []
        personen += [b for b in s["berufstraeger"] if not s["inhaber"] or b["id"] != s["inhaber"]["id"]]
        anwaelte = [{"id": a["id"], "name": eigene.anzeigename(a["daten"], "person_extern"), "kanzlei":
                     k["daten"].get("name", "")} for k in s["beauftragte_kanzleien"] for a in k.get("anwaelte", [])]
        if s["profil"]["form"] == "rechtsabteilung" and s["inhaber"]:
            anwaelte.insert(0, {"id": s["inhaber"]["id"], "name": eigene.anzeigename(
                s["inhaber"]["daten"], "person_rechtsabteilung"), "kanzlei": "selbst (Rechtsabteilung)"})
        return {
            "rollen": {k: {"seite": v[0], "text": v[1]} for k, v in stammdaten.ROLLEN.items()},
            "seiten": stammdaten.SEITEN, "gruppen": stammdaten.GRUPPEN, "status": stammdaten.STATUS,
            "verfahren_arten": verfahren.ARTEN, "instanzen": verfahren.INSTANZEN, "kalender_arten": kalender.ARTEN,
            "eigene_rollen": stammdaten.EIGENE_ROLLEN,
            "sachgebiete": stammdaten.SACHGEBIETE, "kategorien": beteiligte.KATEGORIEN,
            "beziehungen": beteiligte.BEZIEHUNGEN, "funktionen": beteiligte.FUNKTIONEN,
            "entscheidungen": kollision.ENTSCHEIDUNGEN,
            "form": s["profil"]["form"],
            "sachbearbeiter": [{"id": p["id"], "name": eigene.anzeigename(p["daten"], "person_anwalt")}
                               for p in personen],
            "konzerngesellschaften": [{"id": o["id"], "name": o["daten"].get("name", "")}
                                      for o in s["konzerngesellschaften"]],
            "anwaelte": anwaelte,
        }

    def aktives_modell(self) -> str:
        """Ergebnisse gelten je Modell; gezeigt und ausgegeben wird, was zum aktiven Modell gespeichert ist."""
        return ki_anbieter.lade_einstellungen(self.ki_datei).aktives_modell

    def akte_stammdaten(self, akte_id: int) -> dict:
        return self._mit_kollision(stammdaten.stammdaten(self.akten, akte_id))

    def _mit_kollision(self, daten: dict) -> dict:
        return {**daten, "kollision": kollision.letzte(self.akten, daten["id"]),
                "verfahren": verfahren.liste(self.akten, daten["id"])}

    def _nach_aenderung(self, daten: dict, rolle: str | None) -> dict:
        """Nach einer Änderung an Mandant oder Gegner gleich erneut prüfen."""
        if rolle is None or rolle in kollision.PARTEIROLLEN:
            self.kollision_pruefen(daten["id"])
        return self._mit_kollision(daten)

    def kollision_pruefen(self, akte_id: int) -> dict:
        """Prüft in der aktiven Umgebung und, nur lesend, in den anderen Umgebungen (außer den ausgenommenen)."""
        return self._mit_anderen_umgebungen(lambda andere, name: kollision.pruefen(self.akten, akte_id, andere, name))

    def kollision_vorab(self, akte_id: int, rolle: str, beteiligter_ids: list[int]) -> dict:
        """Hinweis für Suchtreffer, bevor sie als Mandant oder Gegner eingetragen werden."""
        return self._mit_anderen_umgebungen(
            lambda andere, name: kollision.vorab(self.akten, akte_id, rolle, beteiligter_ids, andere, name))

    def _mit_anderen_umgebungen(self, f):
        liste = self.umgebungen.liste()
        aktiv = next(u for u in liste["umgebungen"] if u["aktiv"])
        ausgenommen = set(stammdaten.einstellungen(self.akten)["kollision_ausgenommen"])
        andere: list[tuple[str, sqlite3.Connection]] = []
        try:
            for u in liste["umgebungen"]:
                pfad = self.umgebungen.ordner(u["id"]) / "akten.sqlite"
                if u["aktiv"] or u["id"] in ausgenommen or not pfad.is_file():
                    continue
                try:
                    c = sqlite3.connect(f"{pfad.resolve().as_uri()}?mode=ro", uri=True)
                    c.row_factory = sqlite3.Row
                    c.execute("SELECT 1 FROM akte LIMIT 1")
                except sqlite3.Error as fehler:
                    log.warning("Umgebung %s für die Kollisionsprüfung nicht lesbar: %s", u["name"], fehler)
                    continue
                andere.append((u["name"], c))
            return f(andere, aktiv["name"])
        finally:
            for _, c in andere:
                c.close()

    def umgebung_wechseln(self, umgebung_id: str) -> dict:
        """Schließt die Akten der aktiven Umgebung und öffnet die der gewählten."""
        if self.auftraege.laufend():
            raise RuntimeError("Eine Analyse läuft noch. Bitte warten oder sie abbrechen, dann die Umgebung wechseln.")
        if laufend := self.hintergrund.laufend():
            raise RuntimeError(f"„{laufend[0]['titel']}“ läuft noch. Bitte warten oder abbrechen, dann die Umgebung "
                               "wechseln.")
        ordner = self.umgebungen.aktivieren(umgebung_id)
        self.akten.close()
        self._oeffne_akten(ordner)
        return self.umgebungen.liste()

    def importieren(self, gesetze: list[str]) -> list[dict]:
        ergebnisse = []
        for i, abk in enumerate(gesetze, 1):
            hintergrund.pruefe()
            hintergrund.melde(f"Lade {abk.upper()} ({i} von {len(gesetze)}) …", i, len(gesetze))
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
        return {"aus": e.abgeschaltet, "aktiv": ki_anbieter.EXTERN if e.extern else ki_anbieter.LOKAL,
                "titel": titel, "modell": e.aktives_modell,
                "ort": None if e.extern else ki_anbieter.lokal_ort(e)}

    def ki_einstellungen_setzen(self, anbieter: str, endpunkt: str, modell: str = "", kontext: int = 16384) -> dict:
        """Das lokale Modell; die Einstellungen der externen KI bleiben, wie sie sind."""
        e = ki_anbieter.lade_einstellungen(self.ki_datei)
        e.anbieter, e.endpunkt, e.modell, e.kontext = anbieter, endpunkt, modell, kontext
        ki_anbieter.speichere_einstellungen(self.ki_datei, e)
        return ki_anbieter.gesamtstatus(e, self._schluessel(e))

    def ki_schalten(self, an: bool) -> dict:
        """Schalter „KI verwenden“; aus fragt die App kein Sprachmodell mehr, die übrigen Einstellungen bleiben."""
        e = ki_anbieter.lade_einstellungen(self.ki_datei)
        e.abgeschaltet = not an
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
        if e.abgeschaltet:
            raise ValueError(ki_anbieter.AUSGESCHALTET)
        if not e.aktives_modell:
            raise ValueError("Kein Sprachmodell gewählt. Bitte unter „Einstellungen“ ein Modell auswählen.")
        return e, self.ki_fabrik(e, self._schluessel(e) if e.extern else None)

    def ki_chat_fragen(self, akte_id: int, frage: str, dokument_id: int | None = None, rechner: bool = False,
                       gesetze: bool | str = False, land: str = "BY",
                       gesetze_ergaenzt: list[str] | None = None, rechtsprechung: str = "aus") -> dict:
        """Stellt eine Frage an die Akte bzw. an ein Dokument im Hintergrund; die Antwort liefert ``ki.auftrag``.

        ``rechner``: Zinsen und Fristen rechnet die App (Toolbox); ``gesetze``: "aus", "zitiert" (die in der Akte
        zitierten Normen) oder "suche" (dazu Treffer zur Frage), ``True`` gilt als "suche"; ``land``: Bundesland für
        Feiertage beim Fristenrechner; ``gesetze_ergaenzt``: Normzitate, die immer mitgehen, und Gesetze, in denen
        zusätzlich gesucht wird; ``rechtsprechung``: "aus", "akte" (Leitsätze und zitierte Randnummern der
        Entscheidungen der Akte) oder "suche" (dazu die zur Frage passenden Randnummern)."""
        stufe = ki_wissen.GESETZE_SUCHE if gesetze is True else ki_wissen.GESETZE_AUS if not gesetze else gesetze
        if stufe not in ki_wissen.GESETZE_STUFEN:
            raise ValueError(f"Unbekannte Stufe für Gesetze: {gesetze}")
        if rechtsprechung not in ki_wissen.RECHTSPRECHUNG_STUFEN:
            raise ValueError(f"Unbekannte Stufe für Rechtsprechung: {rechtsprechung}")
        if not str(frage).strip():
            raise ValueError("Die Frage ist leer.")
        e, modell = self._ki_modell()
        extern = ki_anbieter.EXTERNE[e.extern_anbieter]["titel"] if e.extern else None

        def arbeit(auftrag) -> dict:
            con = akte.oeffne(self.akten_pfad)
            wb = db.oeffne(self.db_pfad) if stufe != ki_wissen.GESETZE_AUS else None
            try:
                return ki_chat.frage(con, modell, e.aktiver_kontext, int(akte_id), str(frage),
                                     None if dokument_id is None else int(dokument_id), auftrag, extern,
                                     rechner=bool(rechner), gesetze=wb,
                                     gesetze_suche=stufe == ki_wissen.GESETZE_SUCHE,
                                     gesetze_ergaenzt=[str(x) for x in gesetze_ergaenzt or []],
                                     rechtsprechung=rechtsprechung,
                                     basiszins=basiszins.lade(self.basiszins_datei), land=str(land))
            finally:
                con.close()
                if wb is not None:
                    wb.close()

        return self.auftraege.starte("chat", arbeit)

    KI_AUFGABEN = ("zusammenfassung_dokument", "zusammenfassung_akte", "widersprueche", "chronologie",
                   "gegenueberstellung")

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
                if aufgabe == "gegenueberstellung":
                    return ki_gegenueberstellung.gegenueberstellen(
                        analyse, int(akte_id), None if dokument_id is None else int(dokument_id))
                return analyse.widersprueche(int(akte_id), dokument_ids)
            finally:
                con.close()

        return self.auftraege.starte(aufgabe, arbeit)

    def ki_leistungstest(self) -> dict:
        """Startet den KI-Leistungstest der Diagnose im Hintergrund; das Ergebnis liefert ``ki.auftrag``.

        Ans Modell gehen nur die festen Testtexte aus ``ki.leistung``, keine Akteninhalte."""
        e, modell = self._ki_modell()
        if e.extern:
            anbieter, ort = ki_anbieter.EXTERNE[e.extern_anbieter]["titel"], "Externer Anbieter"
        else:
            anbieter = ki_anbieter.ANBIETER[e.anbieter]["titel"]
            ort = "Lokales Netzwerk" if ki_anbieter.lokal_ort(e) == ki_anbieter.NETZWERK else "Eigener Rechner"
        return self.auftraege.starte(ki_leistung.AUFGABE,
                                     lambda auftrag: ki_leistung.leistungstest(modell, auftrag, anbieter, ort))

    def metadaten_ki(self, dokument_id: int, neu: bool = False, automatisch: bool = False) -> dict:
        """Art, Absender, Empfänger und Gegenstand eines Dokuments vom Sprachmodell, sofern eines eingerichtet ist.

        Status "aus" (KI ausgeschaltet oder kein Modell, die Texterkennung gilt), "fertig" mit Ergebnis (auch aus
        dem Speicher), "laeuft" mit Auftrag (Ergebnis über ``ki.auftrag``) oder "belegt" (das Modell arbeitet an
        etwas anderem). ``automatisch`` (die Ansicht „Details“ wurde nur geöffnet): Bei einem externen Anbieter startet
        nichts, Status "extern"; der Text geht erst auf Knopfdruck hinaus.
        """
        e = ki_anbieter.lade_einstellungen(self.ki_datei)
        if e.abgeschaltet or not e.aktives_modell:
            return {"status": "aus", "abgeschaltet": e.abgeschaltet}
        _, modell = self._ki_modell()
        d = self.akten.execute("SELECT akte_id FROM dokument WHERE id = ?", (int(dokument_id),)).fetchone()
        if d is None:
            raise LookupError(f"Dokument {dokument_id} gibt es nicht.")
        beteiligte = stammdaten.beteiligungen(self.akten, d["akte_id"])
        eigene = self._eigene_namen()
        if not neu and (alt := ki_metadaten.gespeichert(Analyse(self.akten, modell, e.aktiver_kontext),
                                                        int(dokument_id), beteiligte, eigene)) is not None:
            return {"status": "fertig", "ergebnis": alt}
        if automatisch and e.extern:
            return {"status": "extern"}
        # Liest das Modell dieses Dokument schon (zweites Öffnen, Doppelaufruf der Oberfläche), denselben Auftrag
        # zurückgeben statt „belegt“.
        if (laufend := self.auftraege.laufend()) is not None:
            if laufend.aufgabe == ki_metadaten.AUFGABE and laufend.bezug == int(dokument_id) and not neu:
                return {"status": "laeuft", "auftrag": laufend.als_dict()}
            return {"status": "belegt", "aufgabe": laufend.aufgabe}

        def arbeit(auftrag) -> dict:
            con = akte.oeffne(self.akten_pfad)
            try:
                analyse = Analyse(con, modell, e.aktiver_kontext, auftrag, neu=bool(neu))
                return ki_metadaten.erkennen(analyse, int(dokument_id), beteiligte, eigene)
            finally:
                con.close()

        try:
            return {"status": "laeuft",
                    "auftrag": self.auftraege.starte(ki_metadaten.AUFGABE, arbeit, bezug=int(dokument_id))}
        except RuntimeError:  # gerade eben ein anderer Auftrag gestartet
            laufend = self.auftraege.laufend()
            return {"status": "belegt", "aufgabe": laufend.aufgabe if laufend else None}

    def ki_vergleich(self, akte_id: int, dokument_ids: list[int] | None = None, neu: bool = False,
                     automatisch: bool = False) -> dict:
        """Vergleich der Akte mit dem Sprachmodell (Zahlen und Daten mit Bezug, inhaltliche Widersprüche).

        Wie ``akten.metadaten_ki``: Status "aus" (KI ausgeschaltet oder kein Modell; es gilt der regelbasierte
        ``akten.abgleich``), "fertig" mit Ergebnis (auch aus dem Speicher), "laeuft" mit Auftrag (Ergebnis über
        ``ki.auftrag``), "belegt" (das Modell arbeitet an etwas anderem) oder "extern" (``automatisch`` bei einem
        externen Anbieter: Der Text geht erst auf Knopfdruck hinaus).
        """
        e = ki_anbieter.lade_einstellungen(self.ki_datei)
        if e.abgeschaltet or not e.aktives_modell:
            return {"status": "aus", "abgeschaltet": e.abgeschaltet}
        try:
            _, modell = self._ki_modell()
        except ValueError as fehler:
            return {"status": "aus", "abgeschaltet": False, "hinweis": str(fehler)}
        ids = [int(i) for i in dokument_ids] if dokument_ids else None
        if not neu and (alt := ki_vergleich.gespeichert(Analyse(self.akten, modell, e.aktiver_kontext),
                                                        int(akte_id), ids)) is not None:
            return {"status": "fertig", "ergebnis": alt}
        if automatisch and e.extern:
            return {"status": "extern"}
        bezug = (int(akte_id), tuple(sorted(ids)) if ids else None)
        if (laufend := self.auftraege.laufend()) is not None:
            if laufend.aufgabe == ki_vergleich.AUFGABE and laufend.bezug == bezug and not neu:
                return {"status": "laeuft", "auftrag": laufend.als_dict()}
            return {"status": "belegt", "aufgabe": laufend.aufgabe}

        def arbeit(auftrag) -> dict:
            con = akte.oeffne(self.akten_pfad)
            try:
                return ki_vergleich.vergleiche(Analyse(con, modell, e.aktiver_kontext, auftrag, neu=bool(neu)),
                                               int(akte_id), ids)
            finally:
                con.close()

        try:
            return {"status": "laeuft", "auftrag": self.auftraege.starte(ki_vergleich.AUFGABE, arbeit, bezug=bezug)}
        except RuntimeError:  # gerade eben ein anderer Auftrag gestartet
            laufend = self.auftraege.laufend()
            return {"status": "belegt", "aufgabe": laufend.aufgabe if laufend else None}

    def ki_gegenueberstellung(self, akte_id: int, dokument_id: int | None = None) -> dict:
        """Gespeicherte Gegenüberstellungen (Schriftsatz und zitierte Entscheidung), ohne das Modell zu fragen."""
        e = ki_anbieter.lade_einstellungen(self.ki_datei)
        if e.abgeschaltet or not e.aktives_modell:
            return {"zitate": [], "offen": 0, "anzahl": 0, "modell": None}
        _, modell = self._ki_modell()
        return ki_gegenueberstellung.gegenueberstellen(
            Analyse(self.akten, modell, e.aktiver_kontext), int(akte_id),
            None if dokument_id is None else int(dokument_id), nur_gespeichert=True)

    def nachrichten_hinzufuegen(self, url: str, titel: str = "") -> dict:
        try:
            return self.nachrichten.hinzufuegen(url, titel)
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as fehler:
            grund = getattr(fehler, "reason", None) or type(fehler).__name__
            raise OSError(f"Die Adresse ist nicht erreichbar ({grund}).") from fehler

    def _online_quellen(self) -> set[str]:
        return online.quellen(online.einstellungen(self.quellen_datei))

    def recherche_suche(self, quelle: str, felder: dict) -> dict:
        neuris_an = online.einstellungen(self.quellen_datei)["neuris"]
        with netzprotokoll.anlass("Rechtsprechung online suchen"):
            return self._recherche_ergebnis(lambda: self.recherche.suche(quelle, felder, neuris_an))

    def _recherche_ergebnis(self, f: Callable[[], Any]) -> Any:
        """Führt einen Abruf der Online-Recherche aus; Netzfehler werden zu einer verständlichen Meldung,
        Treffer bekommen ``urteil_id``, wenn sie schon gespeichert sind."""
        try:
            ergebnis = f()
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as fehler:
            grund = getattr(fehler, "reason", None) or type(fehler).__name__
            raise OSError(f"Die Quelle ist nicht erreichbar ({grund}). Bitte später erneut versuchen.") from fehler
        except (zipfile.BadZipFile, ET.ParseError) as fehler:
            # Sonst kein erwarteter Fehler des Kerns: Er würde beendet statt eine Meldung zu geben.
            raise ValueError(f"Die Quelle hat keine lesbare Entscheidung geliefert ({fehler}).") from fehler
        if isinstance(ergebnis, dict) and "treffer" in ergebnis:
            ergebnis["treffer"] = urteile.gespeichert(self.akten, ergebnis["treffer"])
        return ergebnis

    def volltexte_laden(self, akte_id: int, zitat: str | None = None) -> dict:
        with netzprotokoll.anlass("Volltexte der Akte laden"):
            return urteile.volltexte_laden(self.akten, self.con, akte_id, self.archiv, zitat=zitat)

    def online_pruefen(self, akte_id: int, neu: bool = False) -> dict:
        """Prüft offene Zitate einer Akte bei gesetze-bayern.de bzw. NeuRIS; gesendet wird nur das Aktenzeichen."""
        aktiv = self._online_quellen()
        with netzprotokoll.anlass("Zitate der Akte online prüfen"):
            ergebnis = online.pruefe(self.con, akte.rechtsprechung(self.akten, self.con, akte_id, None, aktiv),
                                     aktiv, bool(neu), eigene=online.eigene_aktenzeichen(self.akten))
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

    def gerichte_laden(self) -> dict:
        """Lädt die Codeliste GDS.Gerichte aus XRepository (öffentliche Liste, keine Akteninhalte)."""
        daten, url = gerichte.lade(self.diagnose_oeffnen)
        sha, archivpfad = gerichte.archiviere(daten, self.archiv)
        return gerichte.importiere(self.con, daten, url, sha, archivpfad)

    def gerichte_laden_datei(self, pfad: str) -> dict:
        daten = Path(pfad).read_bytes()
        sha, archivpfad = gerichte.archiviere(daten, self.archiv)
        return gerichte.importiere(self.con, daten, str(pfad), sha, archivpfad)

    def gerichte_zustaendig(self, plz: str, ort: str, ang: str = "zivil") -> dict:
        """Zuständigkeitssuche; abgeschaltete Gerichtsbarkeiten gehen nicht ins Netz."""
        if ang in justizadressen.GERICHTSBARKEITEN and ang not in justizadressen.einstellungen(
                self.gerichtssuche_datei)["aktiv"]:
            raise ValueError(f"Die Suche nach {justizadressen.GERICHTSBARKEITEN[ang]} ist in den Einstellungen "
                             "ausgeschaltet.")
        return justizadressen.zustaendig(self.con, plz, ort, self.archiv, self.diagnose_oeffnen, ang=ang)

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
            ergebnis = _aufrufen(methode, anfrage.get("params"))
            return {"id": anfrage_id, "result": ergebnis}
        except (ValueError, LookupError, TypeError, OSError, RuntimeError, sqlite3.Error) as fehler:
            log.warning("Fehler bei Anfrage %s: %s", anfrage_id, fehler)
            return {"id": anfrage_id, "error": {"message": str(fehler), "typ": type(fehler).__name__}}
        except Exception as fehler:
            log.exception("Unerwarteter Fehler bei Anfrage %s", anfrage_id)
            return {"id": anfrage_id, "error": {
                "message": f"Unerwarteter Fehler im Analysekern ({type(fehler).__name__}: {fehler}).",
                "typ": type(fehler).__name__}}


def _aufrufen(methode: Callable[..., Any], params: Any) -> Any:
    if params is None:
        return methode()
    if isinstance(params, dict):
        return methode(**params)
    if isinstance(params, list):
        return methode(*params)
    raise TypeError(f"params muss ein Objekt oder eine Liste sein, nicht {type(params).__name__}.")


def serve(db_pfad: Path | None = None, archiv: Path | None = None) -> None:
    kern = Kern(db_pfad or einstellungen.datenbank(), archiv or einstellungen.roharchiv())
    # Unabhängig von der Systemeinstellung (Windows: cp1252) immer UTF-8 und "\n" sprechen.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    for zeile in sys.stdin:
        if not zeile.strip():
            continue
        antwort = kern.bearbeite(zeile)
        try:
            text = json.dumps(antwort, ensure_ascii=False)
            text.encode("utf-8")
        except (TypeError, ValueError) as fehler:  # nicht als JSON/UTF-8 darstellbar: Meldung statt Absturz
            log.exception("Antwort auf Anfrage %s nicht darstellbar", antwort.get("id"))
            text = json.dumps({"id": antwort.get("id"), "error": {
                "message": f"Die Antwort des Analysekerns ließ sich nicht übertragen ({fehler}).", "typ": "Antwort"}})
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
