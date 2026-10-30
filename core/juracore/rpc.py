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
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import (
    __version__,
    db,
    diagnose,
    einstellungen,
    gerichte,
    justizadressen,
    nachrichten,
    netzprotokoll,
    programme,
    zeiterfassung,
)
from .abgleich import abgleich
from .aktenverwaltung import (
    aus_dokument,
    beteiligte,
    fristenbuch,
    kalender,
    kollision,
    notizen,
    stammdaten,
    verfahren,
)
from .aktenverwaltung import einrichten as aktenverwaltung_einrichten
from .dokumente import akte, anmerkungen, ansicht, fassungen, lesen, metadaten, ocr, suche, urteile
from .eigene import daten as eigene
from .eigene import marke
from .eigene.felder import FELDER, FORMEN
from .gesetze import quelle, wissensbasis
from .ki import anbieter as ki_anbieter
from .ki import chat as ki_chat
from .ki import export as ki_export
from .ki import gegenueberstellung as ki_gegenueberstellung
from .ki import metadaten as ki_metadaten
from .ki import speicher as ki_speicher
from .ki import wissen as ki_wissen
from .ki.analyse import Analyse
from .ki.auftraege import Auftraege
from .rechner import basiszins, fristen, prozesskosten, verzugszinsen
from .rechtsprechung import online, recherche, verzeichnis
from .schriftstuecke import kostennote
from .schriftstuecke import platzhalter as schrift_platzhalter
from .schriftstuecke import vorlagen as schrift_vorlagen
from .umgebungen import Umgebungen

log = logging.getLogger("juracore.rpc")


class Kern:
    def __init__(self, db_pfad: Path, archiv: Path):
        self.con = db.oeffne(db_pfad)
        self.db_pfad = Path(db_pfad)
        self.archiv = archiv
        self.eigene_liste = Path(db_pfad).parent / "gesetze.json"
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
        # Nachrichten-Feeds der Startseite gelten für das Gerät; geladen wird im Hintergrund.
        self.nachrichten = nachrichten.Nachrichten(
            Path(db_pfad).parent / "nachrichten.json", Path(db_pfad).parent / "nachrichten-cache.json")
        # Abrufe der Diagnose und des Gerichtsverzeichnisses; in Tests ohne Netz austauschbar.
        self.diagnose_oeffnen = urllib.request.urlopen
        # Jede Verbindung des Kerns wird protokolliert (Einstellungen → Diagnose); die Datei gilt für das Gerät.
        self.netzprotokoll_datei = Path(db_pfad).parent / netzprotokoll.DATEINAME
        netzprotokoll.einrichten(self.netzprotokoll_datei)
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
            # Logo und Kurzbezeichnung für Leiste und Startseite (Einstellungen → Allgemeines), je Umgebung.
            "marke.lesen": lambda: marke.lesen(self.umgebungen.ordner(), self.akten),
            "marke.logo_setzen": lambda pfad: marke.logo_setzen(self.umgebungen.ordner(), self.akten, pfad),
            "marke.logo_entfernen": lambda: marke.logo_entfernen(self.umgebungen.ordner(), self.akten),
            "marke.druckbild_setzen": lambda png: marke.druckbild_setzen(self.umgebungen.ordner(), self.akten, png),
            "marke.kurz_setzen": lambda text: marke.kurz_setzen(self.umgebungen.ordner(), self.akten, text),
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
            "diagnose.liste": diagnose.liste,
            "diagnose.pruefen": lambda pruef_id: diagnose.pruefe(self, pruef_id),
            # Protokoll der Online-Anfragen (Einstellungen → Diagnose): gilt für das Gerät.
            "netz.protokoll": lambda nur_internet=False, limit=500: netzprotokoll.liste(
                self.netzprotokoll_datei, bool(nur_internet), int(limit)),
            "netz.exportieren": lambda pfad, nur_internet=False: netzprotokoll.exportieren(
                self.netzprotokoll_datei, pfad, bool(nur_internet)),
            "netz.einstellungen": lambda: netzprotokoll.einstellungen(self.netzprotokoll_datei),
            "netz.einstellungen_setzen": lambda tage, hoechstens: netzprotokoll.einstellungen_setzen(
                self.netzprotokoll_datei, int(tage), int(hoechstens)),
            "akten.liste": self.akten_liste,
            "akten.anlegen": self.akte_anlegen,
            "akten.geoeffnet": lambda akte_id: stammdaten.geoeffnet(self.akten, akte_id),
            "akten.optionen": self.akten_optionen,
            "akten.stammdaten": self.akte_stammdaten,
            "akten.stammdaten_speichern": lambda akte_id, daten: self._mit_kollision(
                stammdaten.speichern(self.akten, akte_id, daten)),
            "akten.aktenzeichen_vorschlag": lambda: stammdaten.vorschlag(self.akten),
            "akten.aktenzeichen_vergeben": lambda akte_id, aktenzeichen=None: self._mit_kollision(
                stammdaten.vergeben(self.akten, akte_id, aktenzeichen)),
            "akten.einstellungen": lambda: stammdaten.einstellungen(self.akten),
            "akten.einstellungen_setzen": lambda **p: stammdaten.einstellungen_setzen(self.akten, **p),
            "akten.beteiligung_hinzufuegen": lambda akte_id, rolle, **p: self._nach_aenderung(
                stammdaten.beteiligung_hinzufuegen(self.akten, akte_id, rolle, **p), rolle),
            "akten.beteiligung_aendern": lambda beteiligung_id, rolle=None, aktenzeichen=None: self._nach_aenderung(
                stammdaten.beteiligung_aendern(self.akten, beteiligung_id, rolle, aktenzeichen), rolle),
            "akten.beteiligung_entfernen": lambda beteiligung_id: self._nach_aenderung(
                stammdaten.beteiligung_entfernen(self.akten, beteiligung_id), "mandant"),
            "akten.kollision_pruefen": self.kollision_pruefen,
            "akten.kollision_vorab": self.kollision_vorab,
            "akten.kollision_entscheiden": lambda pruefung_id, entscheidung, begruendung="": kollision.entscheiden(
                self.akten, pruefung_id, entscheidung, begruendung),
            "akten.kollision_verlauf": lambda akte_id: kollision.verlauf(self.akten, akte_id),
            "akten.verfahren": lambda akte_id: verfahren.liste(self.akten, akte_id),
            "akten.verfahren_speichern": lambda akte_id, daten, verfahren_id=None, gericht_daten=None: (
                verfahren.speichern(self.akten, akte_id, daten, verfahren_id, gericht_daten=gericht_daten)),
            "akten.verfahren_loeschen": lambda verfahren_id: verfahren.loeschen(self.akten, verfahren_id),
            "akten.kalender": lambda akte_id: kalender.liste(self.akten, akte_id),
            "akten.kalender_speichern": lambda akte_id, daten, eintrag_id=None: kalender.speichern(
                self.akten, akte_id, daten, eintrag_id),
            "akten.kalender_erledigen": lambda eintrag_id, erledigt=True, vermerk="": kalender.erledigen(
                self.akten, eintrag_id, erledigt, vermerk),
            "akten.kalender_termin_zustand": lambda eintrag_id, zustand, vermerk="", neu=None: kalender.termin_zustand(
                self.akten, eintrag_id, zustand, vermerk, neu),
            "akten.kalender_verlaengern": lambda eintrag_id, datum, vermerk="", dokument_id=None, fundstelle=None: (
                kalender.verlaengern(self.akten, eintrag_id, datum, vermerk, dokument_id, fundstelle)),
            "akten.kalender_loeschen": lambda eintrag_id: kalender.loeschen(self.akten, eintrag_id),
            "akten.kalender_naechste": lambda tage=None, limit=50: kalender.naechste(self.akten, tage, limit),
            "kalender.zeitraum": lambda von, bis: kalender.zeitraum(self.akten, von, bis),
            "kalender.feiertage": lambda von, bis, land="BY": kalender.feiertage(von, bis, land),
            "kalender.fristenbuch_name": lambda von, bis: {"name": fristenbuch.dateiname(von, bis)},
            "kalender.fristenbuch": lambda pfad, von, bis, filter=None: fristenbuch.schreiben(
                self.akten, pfad, von, bis, filter, self.umgebungen.aktiv()),
            "kalender.fristenbuch_druck": lambda von, bis, filter=None: fristenbuch.druckansicht(
                self.akten, von, bis, filter),
            "akten.frist_berechnen": lambda bezugstag, anzahl, einheit, land="BY", beginn="ereignis": kalender.berechne(
                bezugstag, anzahl, einheit, land, beginn),
            "akten.kalender_vorschlaege": self.kalender_vorschlaege,
            "akten.notizen": lambda akte_id, dokument_id=None: notizen.liste(self.akten, akte_id, dokument_id),
            "akten.notiz_speichern": lambda akte_id, text, dokument_id=None, angeheftet=None, notiz_id=None: (
                notizen.speichern(self.akten, akte_id, text, dokument_id, angeheftet, notiz_id)),
            "akten.notiz_anheften": lambda notiz_id, angeheftet=True: notizen.anheften(
                self.akten, notiz_id, angeheftet),
            "akten.notiz_loeschen": lambda notiz_id: notizen.loeschen(self.akten, notiz_id),
            "akten.rubrum_lesen": self.rubrum_lesen,
            "akten.aus_dokument_anlegen": self.aus_dokument_anlegen,
            "akten.verfahren_aus_dokument": self.verfahren_aus_dokument,
            "beteiligte.liste": lambda suche="", art=None: beteiligte.liste(self.akten, suche, art),
            "beteiligte.eintrag": lambda beteiligter_id: beteiligte.eintrag(self.akten, beteiligter_id),
            "beteiligte.aehnliche": lambda art, daten, ausser=None: beteiligte.aehnliche(
                self.akten, art, daten, ausser),
            "beteiligte.speichern": lambda art, daten, beteiligter_id=None, vertreter=None: beteiligte.speichern(
                self.akten, art, daten, beteiligter_id, vertreter),
            "beteiligte.loeschen": lambda beteiligter_id: beteiligte.loeschen(self.akten, beteiligter_id),
            "beteiligte.beziehung_setzen": lambda von, zu, art, vorhanden=True, funktion=None: (
                beteiligte.beziehung_setzen(self.akten, von, zu, art, vorhanden, funktion)),
            "akten.dokumente": self.akten_dokumente,
            "akten.loeschen": lambda akte_id: akte.akte_loeschen(self.akten, akte_id, self.ablage),
            "akten.importieren": lambda akte_id, pfad, tags=None, herkunft=None: akte.importiere(
                self.akten, self.con, akte_id, pfad, self.ablage, tags=tags, herkunft=herkunft
            ),
            "akten.ordner_pruefen": akte.ordner_pruefen,
            "akten.dokument_loeschen": lambda dokument_id: akte.dokument_loeschen(
                self.akten, dokument_id, self.ablage
            ),
            "akten.tags_setzen": lambda dokument_id, tags: akte.tags_setzen(self.akten, dokument_id, tags),
            # Ansicht „Details“: Titel, Datum, Schlagworte, Beteiligte, Vorschläge und Verlauf eines Dokuments.
            "akten.metadaten": lambda dokument_id: metadaten.lesen(self.akten, dokument_id, self._eigene_namen()),
            "akten.metadaten_ki": self.metadaten_ki,
            "akten.metadaten_speichern": lambda dokument_id, titel=None, datum=None, schlagworte=None,
                beteiligte=None, art=None, absender=None: metadaten.speichern(
                self.akten, dokument_id, titel, datum, schlagworte, beteiligte, art, absender, self._eigene_namen()),
            "akten.dokument": lambda dokument_id: akte.dokument(self.akten, dokument_id),
            "nachrichten.einstellungen": self.nachrichten.einstellungen,
            "nachrichten.hinzufuegen": self.nachrichten_hinzufuegen,
            "nachrichten.umbenennen": self.nachrichten.umbenennen,
            "nachrichten.entfernen": self.nachrichten.entfernen,
            "nachrichten.liste": self.nachrichten.liste,
            "nachrichten.oeffnen": programme.adresse_oeffnen,
            "programme.einstellungen": lambda: programme.lade(self.programme_datei),
            "programme.setzen": lambda art, programm="", parameter="": programme.speichere(
                self.programme_datei, art, programm, parameter),
            "akten.fassungen": lambda dokument_id: fassungen.liste(self.akten, dokument_id),
            "akten.extern_ansehen": self.extern_ansehen,
            "akten.extern_bearbeiten": self.extern_bearbeiten,
            "akten.im_ordner_zeigen": self.im_ordner_zeigen,
            "akten.arbeitskopien": lambda akte_id: fassungen.arbeitskopien(self.akten, akte_id),
            "akten.fassung_uebernehmen": self.fassung_uebernehmen,
            "akten.arbeitskopie_verwerfen": lambda dokument_id: fassungen.verwerfen(
                self.akten, self.ablage, dokument_id),
            "akten.normen": lambda akte_id, dokument_id=None: akte.normen(self.akten, akte_id, dokument_id),
            "akten.seitenbild": lambda dokument_id, seite, breite=1000, begriffe=None: ansicht.seitenbild(
                self.akten, dokument_id, seite, breite, begriffe),
            "akten.suche": lambda text, akte_id=None: suche.suche(self.akten, text, akte_id),
            # Markierungen und Kommentare an Dokumenten (Textansicht, Original, Reiter „Anmerkungen“, Suche).
            "anmerkungen.liste": lambda akte_id=None, dokument_id=None: anmerkungen.liste(
                self.akten, akte_id, dokument_id),
            "anmerkungen.anlegen": lambda dokument_id, start, ende, farbe="gelb", stil="flaeche", kommentar=None: (
                anmerkungen.anlegen(self.akten, dokument_id, start, ende, farbe, stil, kommentar)),
            "anmerkungen.aendern": lambda anmerkung_id, farbe=None, stil=None, kommentar=None, ohne_kommentar=False: (
                anmerkungen.aendern(self.akten, anmerkung_id, farbe, stil, kommentar, ohne_kommentar)),
            "anmerkungen.loeschen": lambda anmerkung_id: anmerkungen.loeschen(self.akten, anmerkung_id),
            "anmerkungen.suche": lambda text, akte_id=None: anmerkungen.suche(self.akten, text, akte_id),
            "anmerkungen.seite": lambda dokument_id, seite: anmerkungen.auf_seite(self.akten, dokument_id, seite),
            "anmerkungen.bedeutungen": lambda: anmerkungen.bedeutungen(self.akten),
            "anmerkungen.bedeutungen_setzen": lambda werte: anmerkungen.bedeutungen_setzen(self.akten, werte),
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
            "akten.urteile_zugeordnet": lambda akte_id: urteile.zur_bearbeitung(self.akten, self.con, akte_id),
            "akten.volltexte_laden": self.volltexte_laden,
            "rechtsprechung.eigene": lambda: urteile.uebersicht(self.akten),
            "rechtsprechung.sammlung": lambda: urteile.sammlung(self.akten),
            "rechtsprechung.suche": lambda suchtext: urteile.suche(self.akten, suchtext),
            "rechtsprechung.vorschlag": lambda pfad: urteile.vorschlag(pfad),
            "rechtsprechung.ergaenzen": lambda pfad, gericht, aktenzeichen=None, datum=None, herkunft=None,
                akte_id=None, art=None: urteile.ergaenzen(self.akten, akte_id, pfad, self.ablage, gericht,
                                                          aktenzeichen, datum, None, herkunft, art=art),
            "rechtsprechung.zuordnen": lambda urteil_id, akte_id: urteile.zuordnen(
                self.akten, urteil_id, akte_id, self.ablage),
            "rechtsprechung.loesen": lambda urteil_id: urteile.loesen(self.akten, urteil_id, self.ablage),
            "rechtsprechung.entfernen": lambda urteil_id: urteile.aus_sammlung_entfernen(
                self.akten, urteil_id, self.ablage),
            "rechtsprechung.recherche": self.recherche_suche,
            "rechtsprechung.recherche_weiter": lambda quelle: self._recherche_ergebnis(
                lambda: self.recherche.weiter(quelle)),
            "rechtsprechung.recherche_oeffnen": lambda quelle, doknr, treffer=None: self._recherche_ergebnis(
                lambda: urteile.vorschau(self.recherche.daten(quelle, doknr), quelle, treffer)),
            "rechtsprechung.recherche_speichern": lambda quelle, doknr, treffer=None: self._recherche_ergebnis(
                lambda: urteile.in_sammlung(self.akten, self.recherche.daten(quelle, doknr), quelle, self.archiv,
                                            treffer)),
            "akten.urteil": lambda urteil_id: urteile.volltext(self.akten, urteil_id),
            "akten.urteil_entfernen": lambda urteil_id: urteile.entfernen(self.akten, urteil_id, self.ablage),
            "rechtsprechung.stand": lambda: verzeichnis.stand(self.con),
            "rechtsprechung.laden": self.rechtsprechung_laden,
            "rechtsprechung.laden_datei": self.rechtsprechung_laden_datei,
            "gerichte.stand": lambda: gerichte.stand(self.con),
            "gerichte.laden": self.gerichte_laden,
            "gerichte.laden_datei": self.gerichte_laden_datei,
            "gerichte.namen": lambda: gerichte.namen(self.con),
            "gerichte.verzeichnis_oeffnen": lambda: gerichte.verzeichnis_oeffnen(),
            "gerichte.zustaendig": lambda plz, ort: justizadressen.zustaendig(
                self.con, plz, ort, self.archiv, self.diagnose_oeffnen),
            # Schriftstücke aus der Akte: Grundvorlagen und eigene Word-Vorlagen der Umgebung mit Platzhaltern.
            "schriftstuecke.vorlagen": lambda: schrift_vorlagen.liste(self.umgebungen.ordner()),
            "schriftstuecke.katalog": schrift_platzhalter.katalog,
            "schriftstuecke.vorschau": lambda akte_id, vorlage, empfaenger_id=None, verfahren_id=None: (
                schrift_vorlagen.vorschau(self.akten, self.umgebungen.ordner(), akte_id, vorlage, empfaenger_id,
                                          verfahren_id)),
            "schriftstuecke.erzeugen": lambda akte_id, vorlage, empfaenger_id=None, verfahren_id=None, pfad=None,
                in_akte=True: schrift_vorlagen.erzeugen(self.akten, self.con, self.umgebungen.ordner(), self.ablage,
                                                        akte_id, vorlage, empfaenger_id, verfahren_id, pfad, in_akte),
            "kostennote.katalog": kostennote.katalog,
            "kostennote.vorschlag": lambda akte_id: kostennote.vorschlag(self.akten, akte_id),
            "kostennote.berechnen": lambda eingabe: kostennote.berechne(eingabe),
            "kostennote.erzeugen": lambda akte_id, eingabe, pfad=None, in_akte=True: kostennote.erzeugen(
                self.akten, self.con, self.umgebungen.ordner(), self.ablage, akte_id, eingabe, pfad, in_akte),
            "kostennote.liste": lambda akte_id: kostennote.liste(self.akten, akte_id),
            "kostennote.eingabe": lambda kostennote_id: kostennote.eingabe(self.akten, kostennote_id),
            "kostennote.stornieren": lambda kostennote_id: kostennote.stornieren(self.akten, kostennote_id),
            # Zeiterfassung je Akte: Stufen, Bearbeiter und Taktung gelten für die Umgebung.
            "zeit.einstellungen": lambda: zeiterfassung.einstellungen(self.akten),
            "zeit.taktung_setzen": lambda minuten: zeiterfassung.taktung_setzen(self.akten, minuten),
            "zeit.stufe_speichern": lambda name, satz, stufe_id=None: zeiterfassung.stufe_speichern(
                self.akten, name, satz, stufe_id),
            "zeit.stufe_loeschen": lambda stufe_id: zeiterfassung.stufe_loeschen(self.akten, stufe_id),
            "zeit.stufe_verschieben": lambda stufe_id, richtung: zeiterfassung.stufe_verschieben(
                self.akten, stufe_id, richtung),
            "zeit.bearbeiter_speichern": lambda name, stufe_id=None, bearbeiter_id=None, archiviert=None: (
                zeiterfassung.bearbeiter_speichern(self.akten, name, stufe_id, bearbeiter_id, archiviert)),
            "zeit.bearbeiter_loeschen": lambda bearbeiter_id: zeiterfassung.bearbeiter_loeschen(
                self.akten, bearbeiter_id),
            "zeit.standard_setzen": lambda bearbeiter_id=None: zeiterfassung.standard_setzen(self.akten, bearbeiter_id),
            "zeit.aus_eigenen_daten": lambda: zeiterfassung.aus_eigenen_daten(self.akten),
            "zeit.liste": lambda akte_id: zeiterfassung.liste(self.akten, akte_id),
            "zeit.speichern": lambda akte_id, daten, eintrag_id=None: zeiterfassung.speichern(
                self.akten, akte_id, daten, eintrag_id),
            "zeit.loeschen": lambda eintrag_id: zeiterfassung.loeschen(self.akten, eintrag_id),
            "zeit.notiz_speichern": lambda eintrag_id, text: zeiterfassung.notiz_speichern(
                self.akten, eintrag_id, text),
            "zeit.notiz_verknuepfen": lambda eintrag_id, notiz_id=None: zeiterfassung.notiz_verknuepfen(
                self.akten, eintrag_id, notiz_id),
            "zeit.starten": lambda akte_id=None, bearbeiter_id=None, taetigkeit="", eintrag_id=None, stufe_id=None: (
                zeiterfassung.starten(self.akten, akte_id, bearbeiter_id, taetigkeit, eintrag_id, stufe_id=stufe_id)),
            "zeit.stoppen": lambda: zeiterfassung.stoppen(self.akten),
            "zeit.laufend": lambda: zeiterfassung.laufend(self.akten),
            "zeit.fuer_kostennote": lambda akte_id: zeiterfassung.fuer_kostennote(self.akten, akte_id),
            "zeit.vereinbarung_speichern": lambda akte_id, daten: zeiterfassung.vereinbarung_speichern(
                self.akten, akte_id, daten),
            "zeit.mandant_vereinbarungen": lambda mandant: zeiterfassung.mandant_vereinbarungen(self.akten, mandant),
            "zeit.rahmen_speichern": lambda mandant, daten: zeiterfassung.rahmen_speichern(self.akten, mandant, daten),
            "zeit.rahmen_loeschen": lambda mandant: zeiterfassung.rahmen_loeschen(self.akten, mandant),
            "zeit.exportieren": lambda akte_id, pfad, nur_offen=False: zeiterfassung.exportieren(
                self.akten, akte_id, pfad, nur_offen),
            "schriftstuecke.vorlage_hinzufuegen": lambda pfad: schrift_vorlagen.hinzufuegen(
                self.umgebungen.ordner(), pfad),
            "schriftstuecke.vorlage_entfernen": lambda datei: schrift_vorlagen.entfernen(
                self.umgebungen.ordner(), datei),
            "schriftstuecke.vorlage_bearbeiten": self.vorlage_bearbeiten,
            "schriftstuecke.vorlagen_ordner": self.vorlagen_ordner,
            "schriftstuecke.grundvorlage_speichern": lambda vorlage, pfad: schrift_vorlagen.grundvorlage_speichern(
                self.umgebungen.ordner(), vorlage, pfad),
            "akten.abgleich": lambda akte_id, dokument_ids=None: abgleich.abgleich(self.akten, akte_id, dokument_ids),
            "ki.status": self.ki_status,
            "ki.modus": self.ki_modus,
            "ki.einstellungen_setzen": self.ki_einstellungen_setzen,
            "ki.schalten": self.ki_schalten,
            "ki.extern_setzen": self.ki_extern_setzen,
            "ki.starten": self.ki_starten,
            "ki.auftrag": self.auftraege.status,
            "ki.laufend": lambda: (a.als_dict() if (a := self.auftraege.laufend()) else None),
            "ki.abbrechen": self.auftraege.abbrechen,
            "ki.ergebnisse": lambda akte_id: ki_speicher.ergebnisse(self.akten, akte_id, self.aktives_modell()),
            "ki.export_name": lambda akte_id: {"name": ki_export.dateiname(self.akten, akte_id)},
            "ki.export": lambda akte_id, format, pfad, teile=None, zitate=True: ki_export.schreiben(
                self.akten, akte_id, self.aktives_modell(), format, pfad, teile, zitate),
            "ki.export_druck": lambda akte_id, teile=None, zitate=True: ki_export.druckansicht(
                self.akten, akte_id, self.aktives_modell(), teile, zitate),
            "ki.chat_verlauf": lambda akte_id, dokument_id=None: ki_chat.verlauf(self.akten, akte_id, dokument_id),
            "ki.chat_fragen": self.ki_chat_fragen,
            "ki.gegenueberstellung": self.ki_gegenueberstellung,
            "rechner.verzugszinsen": lambda **p: verzugszinsen.berechne(
                verzugszinsen.aus_params(p), basiszins.lade(self.basiszins_datei)),
            "rechner.frist": lambda **p: fristen.aus_params(p),
            "rechner.prozesskosten": lambda **p: prozesskosten.berechne(prozesskosten.aus_params(p)),
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
        # Aktenverwaltung: Beteiligte, Aktenzeichen, Kollisionsprüfung (verweist auf Akten und Eigene Daten).
        aktenverwaltung_einrichten(self.akten)
        # Kostennoten: vergebene Rechnungsnummern der Umgebung.
        kostennote.einrichten(self.akten)
        # Zeiterfassung: Zeiten je Akte, Stundensätze und Bearbeiter der Umgebung.
        zeiterfassung.einrichten(self.akten)
        # Markierungen und Kommentare an Dokumenten.
        anmerkungen.einrichten(self.akten)

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
        for a in akten:
            a["verfahren"] = (verfahren.aktuelles(verfahren.liste(self.akten, a["id"])) or {}).get("bezeichnung")
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
        return {"aus": e.abgeschaltet, "aktiv": ki_anbieter.EXTERN if e.extern else ki_anbieter.LOKAL,
                "titel": titel, "modell": e.aktives_modell,
                "ort": None if e.extern else ki_anbieter.endpunkt_ort(e.endpunkt)}

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
        except Exception as fehler:  # noqa: BLE001 – ein unerwarteter Fehler darf den Kern nicht beenden
            log.exception("Unerwarteter Fehler bei Anfrage %s", anfrage_id)
            return {"id": anfrage_id, "error": {
                "message": f"Unerwarteter Fehler im Analysekern ({type(fehler).__name__}: {fehler}).",
                "typ": type(fehler).__name__}}


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
