"""Methoden des Kerns zum Sprachmodell: Analyse, Chat, Export und Einstellungen."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..ki import chat as ki_chat
from ..ki import export as ki_export
from ..ki import skills as ki_skills
from ..ki import speicher as ki_speicher

if TYPE_CHECKING:
    from ..rpc import Kern


def methoden(k: Kern) -> dict[str, Callable[..., Any]]:
    return {
        "ki.status": k.ki_status,
        "ki.modus": k.ki_modus,
        "ki.einstellungen_setzen": k.ki_einstellungen_setzen,
        "ki.schalten": k.ki_schalten,
        "ki.extern_setzen": k.ki_extern_setzen,
        "ki.starten": k.ki_starten,
        "ki.auftrag": k.auftraege.status,
        "ki.laufend": lambda: (a.als_dict() if (a := k.auftraege.laufend()) else None),
        "ki.abbrechen": k.auftraege.abbrechen,
        "ki.ergebnisse": lambda akte_id: ki_speicher.ergebnisse(k.akten, akte_id, k.aktives_modell()),
        "ki.export_name": lambda akte_id: {"name": ki_export.dateiname(k.akten, akte_id)},
        "ki.export": lambda akte_id, format, pfad, teile=None, zitate=True: ki_export.schreiben(
                k.akten, akte_id, k.aktives_modell(), format, pfad, teile, zitate),
        "ki.export_druck": lambda akte_id, teile=None, zitate=True: ki_export.druckansicht(
                k.akten, akte_id, k.aktives_modell(), teile, zitate),
        "ki.chat_verlauf": lambda akte_id, dokument_id=None: ki_chat.verlauf(k.akten, akte_id, dokument_id),
        "ki.chat_fragen": k.ki_chat_fragen,
        "ki.gegenueberstellung": k.ki_gegenueberstellung,
        "ki.vergleich": k.ki_vergleich,
        "ki.chat_leeren": lambda akte_id, dokument_id=None: ki_chat.leeren(k.akten, akte_id, dokument_id),
        # Skills: Arbeitsanweisungen für Chat und Analyse (Einstellungen → Skills), für das Gerät.
        "skills.liste": lambda: {"skills": ki_skills.liste(k.skills_datei, k._skill_kontext()),
                                 "kontext": k._skill_kontext()},
        "skills.speichern": lambda name, text, beschreibung="", skill_id=None, ordner="": ki_skills.speichern(
                k.skills_datei, name, text, beschreibung, skill_id, k._skill_kontext(), ordner),
        "skills.loeschen": lambda skill_id: ki_skills.loeschen(k.skills_datei, skill_id),
        "skills.importieren": lambda pfad, ordner=None: ki_skills.importieren(
                k.skills_datei, pfad, k._skill_kontext(), ordner),
        "skills.ordner_umbenennen": lambda alt, neu: ki_skills.ordner_umbenennen(k.skills_datei, alt, neu),
        "skills.ordner_loeschen": lambda ordner: ki_skills.ordner_loeschen(k.skills_datei, ordner),
        "skills.exportieren": lambda skill_id, pfad: ki_skills.exportieren(k.skills_datei, skill_id, pfad),
    }
