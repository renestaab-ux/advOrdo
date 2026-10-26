"""Online-Recherche nach Entscheidungen im Bereich „Rechtsprechung“ (wie in JuraBox Lite, Abschnitt 7.6).

Drei Quellen mit je eigener Suchmaske:

- rechtsprechung-im-internet.de: Gericht, Aktenzeichen und Zeitraum im geladenen Verzeichnis (offline);
  Volltext, Norm oder ECLI über die Suche der Seite (``rii_suche``),
- gesetze-bayern.de: Gerichtsbarkeit, Aktenzeichen, Volltext, Zeitraum (``bayern``),
- NeuRIS (nur wenn in den Rechtsquellen eingeschaltet): Gericht, Aktenzeichen, Suchbegriff, Zeitraum (``neuris``).

Gesucht wird nur auf Nutzeraktion; an die Quelle gehen nur die eingegebenen Suchbegriffe. Weitergeblättert
wird nur auf Knopfdruck, insgesamt höchstens ``MAX_TREFFER``. Ein geöffneter Treffer wird geladen und bis zum
Speichern im Speicher gehalten, damit „In die Sammlung“ ihn nicht ein zweites Mal abruft.
"""

from __future__ import annotations

import sqlite3
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

from . import bayern, neuris, rii_suche, verzeichnis
from . import volltext as rii

RII, BAYERN, NEURIS = "rii", "bayern", "neuris"
MAX_TREFFER = rii_suche.MAX_TREFFER
_ZWISCHENSPEICHER = 8


def _leer(*werte: str | None) -> bool:
    return not any((w or "").strip() for w in werte)


class Recherche:
    """Hält die laufende Suche je Quelle (zum Weiterblättern) und die zuletzt geöffneten Volltexte."""

    def __init__(self, wissen: sqlite3.Connection,
                 lader: dict[str, Callable[[str], bytes]] | None = None,
                 sitzung: Callable[[], rii_suche.Sitzung] = rii_suche.Sitzung,
                 diagnose: Path | None = None) -> None:
        self.wissen = wissen
        self.diagnose = diagnose
        self.lader = {RII: rii.lade, BAYERN: bayern.lade, NEURIS: neuris.lade} | (lader or {})
        self._neue_sitzung = sitzung
        self._rii: rii_suche.Sitzung | None = None
        self._neuris: dict | None = None
        self._daten: OrderedDict[tuple[str, str], bytes] = OrderedDict()

    # --- Suche ---------------------------------------------------------------------------------------

    def suche(self, quelle: str, felder: dict, neuris_an: bool = False) -> dict:
        f = {k: (v.strip() if isinstance(v, str) else v) or None for k, v in felder.items()}
        if quelle == RII:
            return self._rii_suche(f)
        if quelle == BAYERN:
            if _leer(f.get("aktenzeichen"), f.get("volltext"), f.get("von"), f.get("bis")):
                raise ValueError("Bitte Aktenzeichen, Volltext oder Zeitraum eingeben.")
            treffer, gesamt = bayern.suche(f.get("aktenzeichen") or "", volltext=f.get("volltext") or "",
                                           von=f.get("von"), bis=f.get("bis"),
                                           gerichtsbarkeit=f.get("gerichtsbarkeit"))
            liste = [t.als_dict() for t in treffer]
            return {"quelle": quelle, "ort": "online", "treffer": liste, "gesamt": gesamt or len(liste),
                    "weitere": False}
        if quelle == NEURIS:
            if not neuris_an:
                raise ValueError("NeuRIS ist ausgeschaltet (Einstellungen → Rechtsquellen).")
            if _leer(f.get("aktenzeichen"), f.get("volltext"), f.get("gericht"), f.get("von"), f.get("bis")):
                raise ValueError("Bitte Gericht, Aktenzeichen, Suchbegriff oder Zeitraum eingeben.")
            self._neuris = {"felder": f, "seite": 0, "geladen": 0}
            return self._neuris_seite()
        raise ValueError(f"Unbekannte Quelle: {quelle!r}")

    def _rii_suche(self, f: dict) -> dict:
        az = f.get("aktenzeichen") or ""
        online = bool(f.get("volltext") or f.get("norm") or az.upper().startswith("ECLI"))
        if not online:
            self._rii = None
            if _leer(f.get("gericht"), az, f.get("von"), f.get("bis")):
                raise ValueError("Bitte Gericht, Aktenzeichen, Zeitraum, Volltext oder Norm eingeben.")
            if verzeichnis.stand(self.wissen) is None:
                raise ValueError("Das Verzeichnis von rechtsprechung-im-internet.de ist noch nicht geladen "
                                 "(Einstellungen → Rechtsquellen). Ohne Verzeichnis sucht die App nur mit Volltext, "
                                 "Norm oder ECLI auf der Seite selbst.")
            ergebnis = rii_suche.lokal(self.wissen, f.get("gericht"), az, f.get("von"), f.get("bis"))
            return {"quelle": RII, "ort": "verzeichnis"} | ergebnis
        self._rii = self._neue_sitzung()
        if self.diagnose is not None:
            self._rii.fehlerseite = self.diagnose / "rii-suchmaske.html"
        ergebnis = self._rii.suche(text=f.get("volltext") or "", norm=f.get("norm") or "", gericht=f.get("gericht"),
                                   aktenzeichen=az, von=f.get("von"), bis=f.get("bis"))
        return {"quelle": RII, "ort": "online"} | ergebnis

    def _neuris_seite(self) -> dict:
        assert self._neuris is not None
        f = self._neuris["felder"]
        treffer, gesamt = neuris.suche(f.get("aktenzeichen") or "", suchbegriff=f.get("volltext") or "",
                                       gericht=f.get("gericht"), von=f.get("von"), bis=f.get("bis"),
                                       seite=self._neuris["seite"])
        self._neuris["geladen"] += len(treffer)
        gesamt = gesamt if gesamt is not None else self._neuris["geladen"]
        weitere = bool(treffer) and self._neuris["geladen"] < min(gesamt, MAX_TREFFER)
        return {"quelle": NEURIS, "ort": "online", "treffer": treffer, "gesamt": gesamt, "weitere": weitere}

    def weiter(self, quelle: str) -> dict:
        """Nächste Trefferseite der laufenden Suche dieser Quelle."""
        if quelle == RII and self._rii is not None:
            return {"quelle": RII, "ort": "online"} | self._rii.weiter()
        if quelle == NEURIS and self._neuris is not None:
            self._neuris["seite"] += 1
            return self._neuris_seite()
        return {"quelle": quelle, "ort": "online", "treffer": [], "gesamt": 0, "weitere": False}

    # --- Volltexte -----------------------------------------------------------------------------------

    def daten(self, quelle: str, doknr: str) -> bytes:
        """Der Volltext eines Treffers; aus dem Zwischenspeicher, sonst von der Quelle."""
        if quelle not in self.lader:
            raise ValueError(f"Unbekannte Quelle: {quelle!r}")
        schluessel = (quelle, doknr)
        if schluessel in self._daten:
            self._daten.move_to_end(schluessel)
            return self._daten[schluessel]
        daten = self.lader[quelle](doknr)
        self._daten[schluessel] = daten
        while len(self._daten) > _ZWISCHENSPEICHER:
            self._daten.popitem(last=False)
        return daten
