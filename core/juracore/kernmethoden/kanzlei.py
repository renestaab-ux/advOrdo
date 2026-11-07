"""Methoden des Kerns: Schriftstücke, Kostennote, Zeiterfassung und Rechner."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .. import zeiterfassung
from ..rechner import basiszins, fristen, prozesskosten, verzugszinsen
from ..schriftstuecke import kostennote
from ..schriftstuecke import platzhalter as schrift_platzhalter
from ..schriftstuecke import vorlagen as schrift_vorlagen

if TYPE_CHECKING:
    from ..rpc import Kern


def methoden(k: Kern) -> dict[str, Callable[..., Any]]:
    return {
        # Schriftstücke aus der Akte: Grundvorlagen und eigene Word-Vorlagen der Umgebung mit Platzhaltern.
        "schriftstuecke.vorlagen": lambda: schrift_vorlagen.liste(k.umgebungen.ordner()),
        "schriftstuecke.katalog": schrift_platzhalter.katalog,
        "schriftstuecke.vorschau": lambda akte_id, vorlage, empfaenger_id=None, verfahren_id=None: (
                schrift_vorlagen.vorschau(k.akten, k.umgebungen.ordner(), akte_id, vorlage, empfaenger_id,
                                          verfahren_id)),
        "schriftstuecke.erzeugen": lambda akte_id, vorlage, empfaenger_id=None, verfahren_id=None, pfad=None,
                in_akte=True: schrift_vorlagen.erzeugen(k.akten, k.con, k.umgebungen.ordner(), k.ablage,
                                                        akte_id, vorlage, empfaenger_id, verfahren_id, pfad, in_akte),
        "kostennote.katalog": kostennote.katalog,
        "kostennote.vorschlag": lambda akte_id: kostennote.vorschlag(k.akten, akte_id),
        "kostennote.berechnen": lambda eingabe: kostennote.berechne(eingabe),
        "kostennote.erzeugen": lambda akte_id, eingabe, pfad=None, in_akte=True: kostennote.erzeugen(
                k.akten, k.con, k.umgebungen.ordner(), k.ablage, akte_id, eingabe, pfad, in_akte),
        "kostennote.eingabe": lambda kostennote_id: kostennote.eingabe(k.akten, kostennote_id),
        "kostennote.stornieren": lambda kostennote_id: kostennote.stornieren(k.akten, kostennote_id),
        # Zeiterfassung je Akte: Stufen, Bearbeiter und Taktung gelten für die Umgebung.
        "zeit.einstellungen": lambda: zeiterfassung.einstellungen(k.akten),
        "zeit.taktung_setzen": lambda minuten: zeiterfassung.taktung_setzen(k.akten, minuten),
        "zeit.stufe_speichern": lambda name, satz, stufe_id=None: zeiterfassung.stufe_speichern(
                k.akten, name, satz, stufe_id),
        "zeit.stufe_loeschen": lambda stufe_id: zeiterfassung.stufe_loeschen(k.akten, stufe_id),
        "zeit.stufe_verschieben": lambda stufe_id, richtung: zeiterfassung.stufe_verschieben(
                k.akten, stufe_id, richtung),
        "zeit.bearbeiter_speichern": lambda name, stufe_id=None, bearbeiter_id=None, archiviert=None: (
                zeiterfassung.bearbeiter_speichern(k.akten, name, stufe_id, bearbeiter_id, archiviert)),
        "zeit.bearbeiter_loeschen": lambda bearbeiter_id: zeiterfassung.bearbeiter_loeschen(
                k.akten, bearbeiter_id),
        "zeit.standard_setzen": lambda bearbeiter_id=None: zeiterfassung.standard_setzen(k.akten, bearbeiter_id),
        "zeit.aus_eigenen_daten": lambda: zeiterfassung.aus_eigenen_daten(k.akten),
        "zeit.liste": lambda akte_id: zeiterfassung.liste(k.akten, akte_id),
        "zeit.speichern": lambda akte_id, daten, eintrag_id=None: zeiterfassung.speichern(
                k.akten, akte_id, daten, eintrag_id),
        "zeit.loeschen": lambda eintrag_id: zeiterfassung.loeschen(k.akten, eintrag_id),
        "zeit.notiz_speichern": lambda eintrag_id, text: zeiterfassung.notiz_speichern(
                k.akten, eintrag_id, text),
        "zeit.notiz_verknuepfen": lambda eintrag_id, notiz_id=None: zeiterfassung.notiz_verknuepfen(
                k.akten, eintrag_id, notiz_id),
        "zeit.starten": lambda akte_id=None, bearbeiter_id=None, taetigkeit="", eintrag_id=None, stufe_id=None: (
                zeiterfassung.starten(k.akten, akte_id, bearbeiter_id, taetigkeit, eintrag_id, stufe_id=stufe_id)),
        "zeit.stoppen": lambda: zeiterfassung.stoppen(k.akten),
        "zeit.laufend": lambda: zeiterfassung.laufend(k.akten),
        "zeit.fuer_kostennote": lambda akte_id: zeiterfassung.fuer_kostennote(k.akten, akte_id),
        "zeit.vereinbarung_speichern": lambda akte_id, daten: zeiterfassung.vereinbarung_speichern(
                k.akten, akte_id, daten),
        "zeit.mandant_vereinbarungen": lambda mandant: zeiterfassung.mandant_vereinbarungen(k.akten, mandant),
        "zeit.rahmen_speichern": lambda mandant, daten: zeiterfassung.rahmen_speichern(k.akten, mandant, daten),
        "zeit.rahmen_loeschen": lambda mandant: zeiterfassung.rahmen_loeschen(k.akten, mandant),
        "zeit.exportieren": lambda akte_id, pfad, nur_offen=False: zeiterfassung.exportieren(
                k.akten, akte_id, pfad, nur_offen),
        "schriftstuecke.vorlage_hinzufuegen": lambda pfad: schrift_vorlagen.hinzufuegen(
                k.umgebungen.ordner(), pfad),
        "schriftstuecke.vorlage_entfernen": lambda datei: schrift_vorlagen.entfernen(
                k.umgebungen.ordner(), datei),
        "schriftstuecke.vorlage_bearbeiten": k.vorlage_bearbeiten,
        "schriftstuecke.vorlagen_ordner": k.vorlagen_ordner,
        "schriftstuecke.grundvorlage_speichern": lambda vorlage, pfad: schrift_vorlagen.grundvorlage_speichern(
                k.umgebungen.ordner(), vorlage, pfad),
        "rechner.verzugszinsen": lambda **p: verzugszinsen.berechne(
                verzugszinsen.aus_params(p), basiszins.lade(k.basiszins_datei)),
        "rechner.frist": lambda **p: fristen.aus_params(p),
        "rechner.prozesskosten": lambda **p: prozesskosten.berechne(prozesskosten.aus_params(p)),
        "rechner.basiszins": lambda: basiszins.stand(k.basiszins_datei),
        "rechner.basiszins_eintragen": lambda ab, satz: basiszins.eintragen(k.basiszins_datei, ab, satz),
        "rechner.basiszins_entfernen": lambda ab: basiszins.entfernen(k.basiszins_datei, ab),
    }
