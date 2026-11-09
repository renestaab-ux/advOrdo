"""Methoden des Kerns: Akten, Dokumente, Beteiligte und Kalender."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..abgleich import abgleich
from ..aktenverwaltung import beteiligte, fristenbuch, kalender, kollision, notizen, sitzung, stammdaten, verfahren
from ..dokumente import akte, ansicht, fassungen, metadaten, suche, urteile

if TYPE_CHECKING:
    from ..rpc import Kern


def methoden(k: Kern) -> dict[str, Callable[..., Any]]:
    return {
        "akten.liste": k.akten_liste,
        "akten.anlegen": k.akte_anlegen,
        "akten.geoeffnet": lambda akte_id: stammdaten.geoeffnet(k.akten, akte_id),
        "akten.optionen": k.akten_optionen,
        "akten.stammdaten": k.akte_stammdaten,
        "akten.stammdaten_speichern": lambda akte_id, daten: k._mit_kollision(
                stammdaten.speichern(k.akten, akte_id, daten)),
        "akten.aktenzeichen_vorschlag": lambda: stammdaten.vorschlag(k.akten),
        "akten.aktenzeichen_vergeben": lambda akte_id, aktenzeichen=None: k._mit_kollision(
                stammdaten.vergeben(k.akten, akte_id, aktenzeichen)),
        "akten.einstellungen": lambda: stammdaten.einstellungen(k.akten),
        "akten.einstellungen_setzen": lambda **p: stammdaten.einstellungen_setzen(k.akten, **p),
        "akten.beteiligung_hinzufuegen": lambda akte_id, rolle, **p: k._nach_aenderung(
                stammdaten.beteiligung_hinzufuegen(k.akten, akte_id, rolle, **p), rolle),
        "akten.beteiligung_entfernen": lambda beteiligung_id: k._nach_aenderung(
                stammdaten.beteiligung_entfernen(k.akten, beteiligung_id), "mandant"),
        "akten.kollision_pruefen": k.kollision_pruefen,
        "akten.kollision_vorab": k.kollision_vorab,
        "akten.kollision_entscheiden": lambda pruefung_id, entscheidung, begruendung="": kollision.entscheiden(
                k.akten, pruefung_id, entscheidung, begruendung),
        "akten.verfahren": lambda akte_id: verfahren.liste(k.akten, akte_id),
        "akten.verfahren_speichern": lambda akte_id, daten, verfahren_id=None, gericht_daten=None: (
                verfahren.speichern(k.akten, akte_id, daten, verfahren_id, gericht_daten=gericht_daten)),
        "akten.verfahren_loeschen": lambda verfahren_id: verfahren.loeschen(k.akten, verfahren_id),
        "akten.kalender": lambda akte_id: kalender.liste(k.akten, akte_id),
        "akten.kalender_speichern": lambda akte_id, daten, eintrag_id=None: kalender.speichern(
                k.akten, akte_id, daten, eintrag_id),
        "akten.kalender_erledigen": lambda eintrag_id, erledigt=True, vermerk="": kalender.erledigen(
                k.akten, eintrag_id, erledigt, vermerk),
        "akten.kalender_termin_zustand": lambda eintrag_id, zustand, vermerk="", neu=None: kalender.termin_zustand(
                k.akten, eintrag_id, zustand, vermerk, neu),
        "akten.kalender_verlaengern": lambda eintrag_id, datum, vermerk="", dokument_id=None, fundstelle=None: (
                kalender.verlaengern(k.akten, eintrag_id, datum, vermerk, dokument_id, fundstelle)),
        "akten.kalender_loeschen": lambda eintrag_id: kalender.loeschen(k.akten, eintrag_id),
        "akten.kalender_naechste": lambda tage=None, limit=50: kalender.naechste(k.akten, tage, limit),
        "kalender.zeitraum": lambda von, bis: kalender.zeitraum(k.akten, von, bis),
        "kalender.feiertage": lambda von, bis, land="BY": kalender.feiertage(von, bis, land),
        "kalender.fristenbuch_name": lambda von, bis: {"name": fristenbuch.dateiname(von, bis)},
        "kalender.fristenbuch": lambda pfad, von, bis, filter=None: fristenbuch.schreiben(
                k.akten, pfad, von, bis, filter, k.umgebungen.aktiv()),
        "kalender.fristenbuch_druck": lambda von, bis, filter=None: fristenbuch.druckansicht(
                k.akten, von, bis, filter),
        "akten.frist_berechnen": lambda bezugstag, anzahl, einheit, land="BY", beginn="ereignis": kalender.berechne(
                bezugstag, anzahl, einheit, land, beginn),
        "akten.kalender_vorschlaege": k.kalender_vorschlaege,
        "akten.notizen": lambda akte_id, dokument_id=None: notizen.liste(k.akten, akte_id, dokument_id),
        "akten.notiz_speichern": lambda akte_id, text, dokument_id=None, angeheftet=None, notiz_id=None: (
                notizen.speichern(k.akten, akte_id, text, dokument_id, angeheftet, notiz_id)),
        "akten.notiz_anheften": lambda notiz_id, angeheftet=True: notizen.anheften(
                k.akten, notiz_id, angeheftet),
        "akten.notiz_loeschen": lambda notiz_id: notizen.loeschen(k.akten, notiz_id),
        # Terminmodus des Arbeitsfensters: Sitzungsblatt (Anträge, Streitpunkte) und Terminsnotizen.
        "sitzung.punkte": lambda akte_id: sitzung.punkte(k.akten, akte_id),
        "sitzung.punkt_speichern": lambda akte_id, daten, punkt_id=None: sitzung.punkt_speichern(
                k.akten, akte_id, daten, punkt_id),
        "sitzung.punkt_loeschen": lambda punkt_id: sitzung.punkt_loeschen(k.akten, punkt_id),
        "sitzung.punkt_verschieben": lambda punkt_id, richtung: sitzung.punkt_verschieben(
                k.akten, punkt_id, richtung),
        "sitzung.aktiv": lambda akte_id: sitzung.aktiv(k.akten, akte_id),
        "sitzung.liste": lambda akte_id: sitzung.sitzungen(k.akten, akte_id),
        "sitzung.termine_heute": lambda akte_id: sitzung.termine_heute(k.akten, akte_id),
        "sitzung.beginnen": lambda akte_id, kalender_id=None, titel="": sitzung.beginnen(
                k.akten, akte_id, kalender_id, titel),
        "sitzung.notiz_anlegen": lambda sitzung_id, text, art="notiz", dokument_id=None: sitzung.notiz_anlegen(
                k.akten, sitzung_id, text, art, dokument_id),
        "sitzung.notiz_aendern": lambda notiz_id, text, art=None: sitzung.notiz_aendern(k.akten, notiz_id, text, art),
        "sitzung.notiz_loeschen": lambda notiz_id: sitzung.notiz_loeschen(k.akten, notiz_id),
        "sitzung.abschluss": lambda sitzung_id, land="BY": sitzung.abschluss(k.akten, sitzung_id, land),
        "sitzung.beenden": lambda sitzung_id, protokoll=True, zeit=None, fristen=None: sitzung.beenden(
                k.akten, sitzung_id, protokoll, zeit, fristen),
        "akten.rubrum_lesen": k.rubrum_lesen,
        "akten.aus_dokument_anlegen": k.aus_dokument_anlegen,
        "akten.verfahren_aus_dokument": k.verfahren_aus_dokument,
        "beteiligte.liste": lambda suche="", art=None: beteiligte.liste(k.akten, suche, art),
        "beteiligte.eintrag": lambda beteiligter_id: beteiligte.eintrag(k.akten, beteiligter_id),
        "beteiligte.aehnliche": lambda art, daten, ausser=None: beteiligte.aehnliche(
                k.akten, art, daten, ausser),
        "beteiligte.speichern": lambda art, daten, beteiligter_id=None, vertreter=None: beteiligte.speichern(
                k.akten, art, daten, beteiligter_id, vertreter),
        "beteiligte.loeschen": lambda beteiligter_id: beteiligte.loeschen(k.akten, beteiligter_id),
        "beteiligte.beziehung_setzen": lambda von, zu, art, vorhanden=True, funktion=None: (
                beteiligte.beziehung_setzen(k.akten, von, zu, art, vorhanden, funktion)),
        "akten.dokumente": k.akten_dokumente,
        "akten.loeschen": lambda akte_id: akte.akte_loeschen(k.akten, akte_id, k.ablage),
        "akten.importieren": lambda akte_id, pfad, tags=None, herkunft=None: akte.importiere(
                k.akten, k.con, akte_id, pfad, k.ablage, tags=tags, herkunft=herkunft
            ),
        # Mehrere Dateien nacheinander, als Hintergrundauftrag (Texterkennung dauert je Seite einige Sekunden).
        "akten.importieren_dateien": k.importieren_dateien,
        "akten.ordner_pruefen": akte.ordner_pruefen,
        "akten.dokument_loeschen": lambda dokument_id: akte.dokument_loeschen(
                k.akten, dokument_id, k.ablage
            ),
        "akten.tags_setzen": lambda dokument_id, tags: akte.tags_setzen(k.akten, dokument_id, tags),
        # Ansicht „Details“: Titel, Datum, Schlagworte, Beteiligte, Vorschläge und Verlauf eines Dokuments.
        "akten.metadaten": lambda dokument_id: metadaten.lesen(k.akten, dokument_id, k._eigene_namen()),
        "akten.metadaten_ki": k.metadaten_ki,
        "akten.metadaten_speichern": lambda dokument_id, titel=None, datum=None, schlagworte=None,
                beteiligte=None, art=None, absender=None: metadaten.speichern(
                k.akten, dokument_id, titel, datum, schlagworte, beteiligte, art, absender, k._eigene_namen()),
        "akten.dokument": lambda dokument_id: akte.dokument(k.akten, dokument_id),
        "akten.fassungen": lambda dokument_id: fassungen.liste(k.akten, dokument_id),
        "akten.extern_ansehen": k.extern_ansehen,
        "akten.extern_bearbeiten": k.extern_bearbeiten,
        "akten.im_ordner_zeigen": k.im_ordner_zeigen,
        "akten.arbeitskopien": lambda akte_id: fassungen.arbeitskopien(k.akten, akte_id),
        "akten.fassung_uebernehmen": k.fassung_uebernehmen,
        "akten.arbeitskopie_verwerfen": lambda dokument_id: fassungen.verwerfen(
                k.akten, k.ablage, dokument_id),
        "akten.normen": lambda akte_id, dokument_id=None: akte.normen(k.akten, akte_id, dokument_id),
        "akten.seitenbild": lambda dokument_id, seite, breite=1000, begriffe=None: ansicht.seitenbild(
                k.akten, dokument_id, seite, breite, begriffe),
        "akten.suche": lambda text, akte_id=None: suche.suche(k.akten, text, akte_id),
        "akten.zitate_pruefen": lambda akte_id: akte.zitate_neu_pruefen(k.akten, k.con, akte_id),
        "akten.rechtsprechung": lambda akte_id, dokument_id=None: akte.rechtsprechung(
                k.akten, k.con, akte_id, dokument_id, k._online_quellen()),
        "akten.online_pruefen": k.online_pruefen,
        "akten.urteil_ergaenzen": lambda akte_id, pfad, gericht, aktenzeichen=None, datum=None, zitat=None,
                herkunft=None: urteile.ergaenzen(k.akten, akte_id, pfad, k.ablage, gericht, aktenzeichen, datum,
                                                 zitat, herkunft),
        "akten.urteile_zugeordnet": lambda akte_id: urteile.zur_bearbeitung(k.akten, k.con, akte_id),
        "akten.volltexte_laden": k.volltexte_laden,
        "akten.urteil": lambda urteil_id: urteile.volltext(k.akten, urteil_id),
        "akten.urteil_entfernen": lambda urteil_id: urteile.entfernen(k.akten, urteil_id, k.ablage),
        "akten.abgleich": lambda akte_id, dokument_ids=None: abgleich.abgleich(k.akten, akte_id, dokument_ids),
    }
