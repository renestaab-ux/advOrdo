"""Methoden des Kerns: Umgebungen, Eigene Daten, Marke, Diagnose, Netzprotokoll, Programme, Hintergrundaufträge
und Nachrichten."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .. import __version__, diagnose, netzprotokoll, programme
from ..dokumente import ocr
from ..eigene import daten as eigene
from ..eigene import marke
from ..eigene.felder import FELDER, FORMEN

if TYPE_CHECKING:
    from ..rpc import Kern


def methoden(k: Kern) -> dict[str, Callable[..., Any]]:
    return {
        "ping": lambda: {"version": __version__},
        "umgebungen.liste": k.umgebungen.liste,
        "umgebungen.anlegen": k.umgebungen.anlegen,
        "umgebungen.umbenennen": k.umgebungen.umbenennen,
        "umgebungen.loeschen": k.umgebungen.loeschen,
        "umgebungen.wechseln": k.umgebung_wechseln,
        "eigene.felder": lambda: {"felder": FELDER, "formen": FORMEN},
        "eigene.stand": lambda: eigene.stand(k.akten),
        "eigene.kurzstand": lambda: eigene.kurzstand(k.akten),
        "eigene.form_setzen": lambda form: eigene.form_setzen(k.akten, form),
        "eigene.organisation_speichern": lambda daten: eigene.organisation_speichern(k.akten, daten),
        "eigene.inhaber_speichern": lambda daten, mitgliedschaft=None: eigene.inhaber_speichern(
                k.akten, daten, mitgliedschaft),
        "eigene.inhaber_waehlen": lambda person_id: eigene.inhaber_waehlen(k.akten, person_id),
        "eigene.einheit_speichern": lambda art, daten, einheit_id=None: eigene.einheit_speichern(
                k.akten, art, daten, einheit_id),
        "eigene.person_speichern": lambda organisation_id, daten, mitgliedschaft=None, person_id=None:
                eigene.person_speichern(k.akten, organisation_id, daten, mitgliedschaft, person_id),
        "eigene.archivieren": lambda objekt, objekt_id, archiviert=True: eigene.archivieren(
                k.akten, objekt, objekt_id, archiviert),
        "eigene.loeschen": lambda objekt, objekt_id: eigene.loeschen(k.akten, objekt, objekt_id),
        "eigene.duplizieren": lambda organisation_id: eigene.duplizieren(k.akten, organisation_id),
        "eigene.assistent_fertig": lambda fertig=True: eigene.assistent_fertig(k.akten, fertig),
        "eigene.aenderungen": lambda limit=50: eigene.aenderungen(k.akten, limit),
        "eigene.exportieren": lambda pfad: eigene.exportieren(k.akten, pfad),
        "eigene.importieren": lambda pfad, ersetzen=False: eigene.importieren(k.akten, pfad, ersetzen),
        # Logo, Kurzbezeichnung und Logo-Hintergrund (Einstellungen → Allgemeines), je Umgebung.
        "marke.lesen": lambda: marke.lesen(k.umgebungen.ordner(), k.akten),
        "marke.logo_setzen": lambda pfad: marke.logo_setzen(k.umgebungen.ordner(), k.akten, pfad),
        "marke.logo_entfernen": lambda: marke.logo_entfernen(k.umgebungen.ordner(), k.akten),
        "marke.druckbild_setzen": lambda png: marke.druckbild_setzen(k.umgebungen.ordner(), k.akten, png),
        "marke.kurz_setzen": lambda text: marke.kurz_setzen(k.umgebungen.ordner(), k.akten, text),
        "marke.hintergrund_setzen": lambda hintergrund: marke.hintergrund_setzen(
            k.umgebungen.ordner(), k.akten, hintergrund),
        "ocr.status": ocr.status,
        "diagnose.liste": diagnose.liste,
        "diagnose.pruefen": lambda pruef_id: diagnose.pruefe(k, pruef_id),
        # Protokoll der Online-Anfragen (Einstellungen → Diagnose): gilt für das Gerät.
        "netz.protokoll": lambda nur_internet=False, limit=500: netzprotokoll.liste(
                k.netzprotokoll_datei, bool(nur_internet), int(limit)),
        "netz.exportieren": lambda pfad, nur_internet=False: netzprotokoll.exportieren(
                k.netzprotokoll_datei, pfad, bool(nur_internet)),
        "netz.einstellungen": lambda: netzprotokoll.einstellungen(k.netzprotokoll_datei),
        "netz.einstellungen_setzen": lambda tage, hoechstens: netzprotokoll.einstellungen_setzen(
                k.netzprotokoll_datei, int(tage), int(hoechstens)),
        "nachrichten.einstellungen": k.nachrichten.einstellungen,
        "nachrichten.hinzufuegen": k.nachrichten_hinzufuegen,
        "nachrichten.umbenennen": k.nachrichten.umbenennen,
        "nachrichten.entfernen": k.nachrichten.entfernen,
        "nachrichten.liste": k.nachrichten.liste,
        "nachrichten.oeffnen": programme.adresse_oeffnen,
        "programme.einstellungen": lambda: programme.lade(k.programme_datei),
        "programme.setzen": lambda art, programm="", parameter="": programme.speichere(
                k.programme_datei, art, programm, parameter),
        # Lange Befehle (Importe, Online-Abrufe) im Hintergrund, damit die App bedienbar bleibt.
        "hintergrund.starten": k.hintergrund_starten,
        "hintergrund.auftrag": k.hintergrund.status,
        "hintergrund.abbrechen": k.hintergrund.abbrechen,
    }
