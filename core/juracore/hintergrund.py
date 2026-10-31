"""Lange Befehle des Kerns im Hintergrund, damit die App währenddessen bedienbar bleibt.

Der RPC-Kern beantwortet Anfragen der Reihe nach. Ein Gesetzesimport oder das Laden von Volltexten dauert
leicht eine Minute; liefe er dort, warteten Timer, Erinnerungen und jeder Klick so lange. Deshalb startet
``hintergrund.starten`` einen solchen Befehl in einem eigenen Thread mit eigenen Datenbankverbindungen (siehe
``Kern.verbindungen``) und gibt sofort die Nummer des Auftrags zurück. Die Oberfläche fragt mit
``hintergrund.auftrag`` nach Fortschritt und Ergebnis, ``hintergrund.abbrechen`` bricht ab.

Das Muster folgt den KI-Aufträgen (``ki.auftraege``), mit zwei Unterschieden: Verschiedene Befehle dürfen
gleichzeitig laufen (ein Import hält keine Volltextsuche auf), derselbe Befehl aber nur einmal. Und abgebrochen
wird spätestens vor der nächsten Netzverbindung (``netzprotokoll.abbrechbar``) oder dort, wo der Befehl selbst mit
``pruefe`` nachfragt; was schon begonnen ist (eine Antwort, die gerade gespeichert wird), wird noch beendet, sein
Ergebnis aber verworfen.
"""

from __future__ import annotations

import contextvars
import itertools
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from typing import Any

from . import netzprotokoll
from .ki.analyse import Abgebrochen
from .ki.auftraege import ABGEBROCHEN, FEHLER, FERTIG, LAEUFT, Auftrag

log = logging.getLogger("juracore.hintergrund")

# Befehle, die im Hintergrund laufen dürfen, mit dem Titel der Warteanzeige.
BEFEHLE = {
    "gesetze.importieren": "Gesetze laden",
    "gesetze.importieren_datei": "Gesetz aus Datei laden",
    "rechtsprechung.laden": "Verzeichnis der Bundesrechtsprechung laden",
    "rechtsprechung.laden_datei": "Verzeichnis der Bundesrechtsprechung aus Datei laden",
    "gerichte.laden": "Gerichtsverzeichnis laden",
    "gerichte.laden_datei": "Gerichtsverzeichnis aus Datei laden",
    "akten.volltexte_laden": "Volltexte laden",
    "akten.online_pruefen": "Zitate online prüfen",
    "anmerkungen.pdf_akte": "PDF-Kopien mit Markierungen erstellen",
}

_BEHALTEN = 20  # beendete Aufträge, deren Ergebnis noch abgeholt werden kann

_aktuell: contextvars.ContextVar[Auftrag | None] = contextvars.ContextVar("hintergrund_auftrag", default=None)


def pruefe() -> None:
    """Bricht ab (``Abgebrochen``), wenn der laufende Hintergrundauftrag abgebrochen wurde; sonst nichts."""
    if (auftrag := _aktuell.get()) is not None:
        auftrag.pruefe()


def melde(text: str, schritt: int | None = None, von: int | None = None) -> None:
    """Fortschritt für die Warteanzeige; außerhalb eines Hintergrundauftrags ohne Wirkung."""
    if (auftrag := _aktuell.get()) is not None:
        auftrag.melde(text, schritt, von)


class Hintergrund:
    def __init__(self) -> None:
        self._nummern = itertools.count(1)
        self._auftraege: dict[int, Auftrag] = {}
        self._sperre = threading.Lock()

    def laufend(self) -> list[dict]:
        with self._sperre:
            liste = [a for a in self._auftraege.values() if a.status == LAEUFT]
        return [_als_dict(a) for a in liste]

    def starte(self, methode: str, arbeit: Callable[[], Any], warten: bool = False) -> dict:
        """Startet ``arbeit()`` im Hintergrund. ``warten`` führt sie sofort aus (Tests)."""
        if methode not in BEFEHLE:
            raise LookupError(f"{methode!r} läuft nicht im Hintergrund.")
        with self._sperre:
            if any(a.status == LAEUFT and a.aufgabe == methode for a in self._auftraege.values()):
                raise RuntimeError(f"„{BEFEHLE[methode]}“ läuft schon. Bitte warten oder abbrechen.")
            auftrag = Auftrag(next(self._nummern), methode)
            auftrag.text = f"{BEFEHLE[methode]} …"
            self._auftraege[auftrag.nr] = auftrag
            for alt in sorted(self._auftraege)[:-_BEHALTEN]:
                if self._auftraege[alt].status != LAEUFT:
                    del self._auftraege[alt]
        if warten:
            self._fuehre_aus(auftrag, arbeit)
        else:
            threading.Thread(target=self._fuehre_aus, args=(auftrag, arbeit), daemon=True,
                             name=f"hintergrund-{auftrag.nr}").start()
        return _als_dict(auftrag)

    @staticmethod
    def _fuehre_aus(auftrag: Auftrag, arbeit: Callable[[], Any]) -> None:
        marke = _aktuell.set(auftrag)
        try:
            with netzprotokoll.abbrechbar(auftrag.pruefe):
                ergebnis = arbeit()
            auftrag.pruefe()  # abgebrochen, aber zu Ende gelaufen: Ergebnis verwerfen
            status, fehler, text = FERTIG, None, "Fertig"
        except Abgebrochen:
            ergebnis, status, fehler, text = None, ABGEBROCHEN, None, "Abgebrochen"
        except (ValueError, LookupError, TypeError, OSError, RuntimeError, sqlite3.Error) as f:
            if auftrag._abbruch.is_set():  # Folgefehler des Abbruchs, keine Meldung wert
                ergebnis, status, fehler, text = None, ABGEBROCHEN, None, "Abgebrochen"
            else:
                log.warning("Hintergrundauftrag %s (%s) fehlgeschlagen: %s", auftrag.nr, auftrag.aufgabe, f)
                ergebnis, status, fehler, text = None, FEHLER, str(f), "Fehlgeschlagen"
        except Exception as f:  # noqa: BLE001 – ein Fehler im Hintergrund darf den Kern nicht beenden
            log.exception("Unerwarteter Fehler in Hintergrundauftrag %s", auftrag.nr)
            ergebnis, status, fehler, text = (None, FEHLER, f"Unerwarteter Fehler im Analysekern "
                                              f"({type(f).__name__}: {f}).", "Fehlgeschlagen")
        finally:
            _aktuell.reset(marke)
        with auftrag._sperre:
            auftrag.ergebnis, auftrag.fehler, auftrag.text = ergebnis, fehler, text
            auftrag.dauer = time.monotonic() - auftrag.beginn
            auftrag.status = status

    def _hole(self, auftrag_id: int) -> Auftrag:
        with self._sperre:
            auftrag = self._auftraege.get(int(auftrag_id))
        if auftrag is None:
            raise LookupError(f"Hintergrundauftrag {auftrag_id} gibt es nicht (mehr).")
        return auftrag

    def status(self, auftrag_id: int) -> dict:
        return _als_dict(self._hole(auftrag_id))

    def abbrechen(self, auftrag_id: int) -> dict:
        auftrag = self._hole(auftrag_id)
        if auftrag.status == LAEUFT:
            auftrag._abbruch.set()
            auftrag.melde("Wird abgebrochen …")
        return _als_dict(auftrag)


def _als_dict(auftrag: Auftrag) -> dict:
    return auftrag.als_dict() | {"titel": BEFEHLE.get(auftrag.aufgabe, auftrag.aufgabe)}
