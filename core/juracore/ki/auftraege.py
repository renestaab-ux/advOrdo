"""Analysen im Hintergrund, damit die App während der Arbeit des Sprachmodells bedienbar bleibt.

Ein lokales Modell braucht für eine Akte mehrere Minuten. Der RPC-Kern
beantwortet Anfragen der Reihe nach; liefe die Analyse dort, stünde die App
still. Deshalb startet ``ki.starten`` einen Auftrag in einem eigenen Thread mit
eigener Datenbankverbindung und gibt sofort dessen Nummer zurück. Die
Oberfläche fragt mit ``ki.auftrag`` nach Fortschritt und Ergebnis.

Es läuft höchstens ein Auftrag zugleich (die Grafikkarte rechnet ohnehin nur
einen). Abbrechen wirkt nach dem laufenden Schritt; eine bereits gestellte
Anfrage an das Modell wird noch beendet.
"""

from __future__ import annotations

import itertools
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from typing import Any

from .. import netzprotokoll
from .analyse import Abgebrochen
from .anbieter import KiFehler

log = logging.getLogger("juracore.ki")

LAEUFT = "laeuft"
FERTIG = "fertig"
FEHLER = "fehler"
ABGEBROCHEN = "abgebrochen"

# Anlass der Anfragen an das Modell im Protokoll der Online-Anfragen.
AUFGABEN = {"chat": "KI-Chat", "widersprueche": "KI-Analyse Widersprüche", "chronologie": "KI-Analyse Chronologie",
            "zusammenfassung_akte": "KI-Zusammenfassung der Akte",
            "zusammenfassung_dokument": "KI-Zusammenfassung eines Dokuments",
            "gegenueberstellung": "KI-Gegenüberstellung Schriftsatz und Urteil", "metadaten": "KI-Vorschläge Details"}

_BEHALTEN = 20  # beendete Aufträge, deren Ergebnis noch abgeholt werden kann


class Auftrag:
    def __init__(self, nr: int, aufgabe: str, bezug: object = None):
        self.nr = nr
        self.aufgabe = aufgabe
        self.bezug = bezug  # woran der Auftrag arbeitet, z. B. die Dokumentnummer
        self.status = LAEUFT
        self.text = "Starte …"
        self.schritt: int | None = None
        self.von: int | None = None
        self.ergebnis: Any = None
        self.fehler: str | None = None
        self.beginn = time.monotonic()
        self.dauer: float | None = None
        self._abbruch = threading.Event()
        self._sperre = threading.Lock()

    # Schnittstelle Fortschritt für die Analyse
    def melde(self, text: str, schritt: int | None = None, von: int | None = None) -> None:
        with self._sperre:
            self.text = text
            if von is not None:
                self.schritt, self.von = schritt, von

    def pruefe(self) -> None:
        if self._abbruch.is_set():
            raise Abgebrochen()

    def als_dict(self) -> dict:
        with self._sperre:
            return {
                "auftrag_id": self.nr,
                "aufgabe": self.aufgabe,
                "status": self.status,
                "text": self.text,
                "schritt": self.schritt,
                "von": self.von,
                "sekunden": round(self.dauer if self.dauer is not None else time.monotonic() - self.beginn),
                "ergebnis": self.ergebnis if self.status == FERTIG else None,
                "fehler": self.fehler,
            }


class Auftraege:
    def __init__(self) -> None:
        self._nummern = itertools.count(1)
        self._auftraege: dict[int, Auftrag] = {}
        self._sperre = threading.Lock()

    def laufend(self) -> Auftrag | None:
        with self._sperre:
            return next((a for a in self._auftraege.values() if a.status == LAEUFT), None)

    def starte(self, aufgabe: str, arbeit: Callable[[Auftrag], Any], warten: bool = False,
               bezug: object = None) -> dict:
        """Startet ``arbeit(auftrag)`` im Hintergrund. ``warten`` führt sie sofort aus (Kommandozeile, Tests)."""
        with self._sperre:
            if any(a.status == LAEUFT for a in self._auftraege.values()):
                raise RuntimeError("Das Sprachmodell arbeitet gerade an einem anderen Auftrag (Analyse oder "
                                   "Chat). Bitte warten oder ihn abbrechen.")
            auftrag = Auftrag(next(self._nummern), aufgabe, bezug)
            self._auftraege[auftrag.nr] = auftrag
            for alt in sorted(self._auftraege)[:-_BEHALTEN]:
                if self._auftraege[alt].status != LAEUFT:
                    del self._auftraege[alt]
        if warten:
            self._fuehre_aus(auftrag, arbeit)
        else:
            threading.Thread(target=self._fuehre_aus, args=(auftrag, arbeit), daemon=True,
                             name=f"ki-auftrag-{auftrag.nr}").start()
        return auftrag.als_dict()

    @staticmethod
    def _fuehre_aus(auftrag: Auftrag, arbeit: Callable[[Auftrag], Any]) -> None:
        try:
            with netzprotokoll.anlass(AUFGABEN.get(auftrag.aufgabe, auftrag.aufgabe)):
                ergebnis = arbeit(auftrag)
            status, fehler, text = FERTIG, None, "Fertig"
        except Abgebrochen:
            ergebnis, status, fehler, text = None, ABGEBROCHEN, None, "Abgebrochen"
        except (KiFehler, ValueError, LookupError, OSError, sqlite3.Error) as f:
            log.warning("Auftrag %s fehlgeschlagen: %s", auftrag.nr, f)
            ergebnis, status, fehler, text = None, FEHLER, str(f), "Fehlgeschlagen"
        except Exception as f:  # ein Fehler im Hintergrund darf den Kern nicht beenden
            log.exception("Unerwarteter Fehler in Auftrag %s", auftrag.nr)
            ergebnis, status, fehler, text = None, FEHLER, f"Unerwarteter Fehler: {f}", "Fehlgeschlagen"
        with auftrag._sperre:
            auftrag.ergebnis, auftrag.fehler, auftrag.text = ergebnis, fehler, text
            auftrag.dauer = time.monotonic() - auftrag.beginn
            auftrag.status = status

    def status(self, auftrag_id: int) -> dict:
        with self._sperre:
            auftrag = self._auftraege.get(int(auftrag_id))
        if auftrag is None:
            raise LookupError(f"Auftrag {auftrag_id} gibt es nicht (mehr).")
        return auftrag.als_dict()

    def abbrechen(self, auftrag_id: int) -> dict:
        with self._sperre:
            auftrag = self._auftraege.get(int(auftrag_id))
        if auftrag is None:
            raise LookupError(f"Auftrag {auftrag_id} gibt es nicht (mehr).")
        auftrag._abbruch.set()
        auftrag.melde("Wird nach dem laufenden Schritt abgebrochen …")
        return auftrag.als_dict()
