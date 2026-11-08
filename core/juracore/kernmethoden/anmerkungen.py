"""Methoden des Kerns: Anmerkungen und Lesezeichen an Dokumenten."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..dokumente import anmerkungen, anmerkungen_ausgabe, lesezeichen, pdf_markiert

if TYPE_CHECKING:
    from ..rpc import Kern


def methoden(k: Kern) -> dict[str, Callable[..., Any]]:
    return {
        # Markierungen und Kommentare an Dokumenten (Textansicht, Original, Reiter „Anmerkungen“, Suche).
        "anmerkungen.liste": lambda akte_id=None, dokument_id=None: anmerkungen.liste(
                k.akten, akte_id, dokument_id),
        "anmerkungen.anlegen": lambda dokument_id, start, ende, farbe="gelb", stil="flaeche", kommentar=None: (
                anmerkungen.anlegen(k.akten, dokument_id, start, ende, farbe, stil, kommentar)),
        "anmerkungen.aendern": lambda anmerkung_id, farbe=None, stil=None, kommentar=None, ohne_kommentar=False: (
                anmerkungen.aendern(k.akten, anmerkung_id, farbe, stil, kommentar, ohne_kommentar)),
        "anmerkungen.loeschen": lambda anmerkung_id: anmerkungen.loeschen(k.akten, anmerkung_id),
        "anmerkungen.suche": lambda text, akte_id=None: anmerkungen.suche(k.akten, text, akte_id),
        "anmerkungen.seite": lambda dokument_id, seite: anmerkungen.auf_seite(k.akten, dokument_id, seite),
        "anmerkungen.woerter": lambda dokument_id, seite: anmerkungen.woerter(k.akten, dokument_id, seite),
        "anmerkungen.anlegen_seite": lambda dokument_id, seite, wort_von, wort_bis, farbe="gelb", stil="flaeche",
                kommentar=None: anmerkungen.anlegen_auf_seite(
                k.akten, dokument_id, seite, wort_von, wort_bis, farbe, stil, kommentar),
        "anmerkungen.bedeutungen": lambda: anmerkungen.bedeutungen(k.akten),
        "anmerkungen.bedeutungen_setzen": lambda werte: anmerkungen.bedeutungen_setzen(k.akten, werte),
        "lesezeichen.inhalt": lambda dokument_id: lesezeichen.inhalt(k.akten, dokument_id),
        "lesezeichen.liste": lambda akte_id=None, dokument_id=None: lesezeichen.liste(
                k.akten, akte_id, dokument_id),
        "lesezeichen.anlegen": lambda dokument_id, start, ende=None, titel=None, ordner_id=None: (
                lesezeichen.anlegen(k.akten, dokument_id, start, ende, titel, ordner_id)),
        "lesezeichen.anlegen_seite": lambda dokument_id, seite, wort_von=None, wort_bis=None, titel=None,
                ordner_id=None: lesezeichen.anlegen_auf_seite(
                k.akten, dokument_id, seite, wort_von, wort_bis, titel, ordner_id),
        "lesezeichen.aendern": lambda lesezeichen_id, titel: lesezeichen.aendern(k.akten, lesezeichen_id, titel),
        "lesezeichen.loeschen": lambda lesezeichen_id: lesezeichen.loeschen(k.akten, lesezeichen_id),
        "lesezeichen.anordnen": lambda akte_id, ordner: lesezeichen.anordnen(k.akten, akte_id, ordner),
        "lesezeichen.seite": lambda dokument_id, seite: lesezeichen.auf_seite(k.akten, dokument_id, seite),
        "lesezeichen.ordner_anlegen": lambda akte_id, name: lesezeichen.ordner_anlegen(k.akten, akte_id, name),
        "lesezeichen.ordner_umbenennen": lambda ordner_id, name: lesezeichen.ordner_umbenennen(
                k.akten, ordner_id, name),
        "lesezeichen.ordner_loeschen": lambda ordner_id: lesezeichen.ordner_loeschen(k.akten, ordner_id),
        "anmerkungen.pdf_name": lambda dokument_id: {"name": pdf_markiert.dateiname(k.akten, dokument_id)},
        "anmerkungen.pdf": k.pdf_markiert,
        "anmerkungen.pdf_akte": k.pdf_markiert_akte,
        "anmerkungen.export_name": lambda akte_id: {"name": anmerkungen_ausgabe.dateiname(k.akten, akte_id)},
        "anmerkungen.export": lambda akte_id, ordner, format, pfad, gliederung="ordner", auswahl=None: (
                anmerkungen_ausgabe.schreiben(k.akten, akte_id, ordner, format, pfad, gliederung, auswahl)),
        "anmerkungen.export_druck": lambda akte_id, ordner, gliederung="ordner", auswahl=None: (
                anmerkungen_ausgabe.druckansicht(k.akten, akte_id, ordner, gliederung, auswahl)),
    }
