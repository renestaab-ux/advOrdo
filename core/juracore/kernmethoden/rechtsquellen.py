"""Methoden des Kerns: Gesetze, Zitate, Rechtsprechung und Gerichtsverzeichnis."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .. import db, gerichte, justizadressen
from ..dokumente import akte, urteile
from ..gesetze import quelle, wissensbasis
from ..rechtsprechung import online, verzeichnis

if TYPE_CHECKING:
    from ..rpc import Kern


def methoden(k: Kern) -> dict[str, Callable[..., Any]]:
    return {
        "gesetze.liste": lambda: db.gesetze(k.con),
        "gesetze.verfuegbar": lambda: quelle.verfuegbar(k.eigene_liste, k.pakete_datei),
        "gesetze.voreinstellung": lambda: quelle.voreinstellung(k.eigene_liste),
        "gesetze.pakete": lambda: quelle.pakete(k.eigene_liste, k.pakete_datei),
        "gesetze.paket_schalten": lambda paket, aktiv: quelle.paket_schalten(
                paket, bool(aktiv), k.eigene_liste, k.pakete_datei),
        "gesetze.importieren": k.importieren,
        "gesetze.importieren_datei": k.importieren_datei,
        "gesetze.suche": lambda text, gesetz=None, limit=20: wissensbasis.suche(k.con, text, gesetz, limit),
        "gesetze.norm": lambda gesetz, nummer, fassung_id=None, typ=None: wissensbasis.norm(
                k.con, gesetz, nummer, fassung_id, typ
            ),
        "zitat.aufloesen": lambda zitat, fassung_id=None: wissensbasis.loese_zitat(k.con, zitat, fassung_id),
        "gesetze.vorschlaege": lambda gesetz: wissensbasis.vorschlaege(
                k.con, gesetz, quelle.voreinstellung(k.eigene_liste)),
        "gesetze.schreibweisen": lambda: wissensbasis.schreibweisen(k.con),
        "gesetze.schreibweise_setzen": lambda von, nach: _schreibweise_setzen(k, von, nach),
        "gesetze.schreibweise_loeschen": lambda von: _schreibweise_loeschen(k, von),
        "rechtsprechung.quellen": lambda: online.einstellungen(k.quellen_datei),
        "rechtsprechung.quellen_setzen": lambda neuris: online.einstellungen_setzen(k.quellen_datei, neuris),
        "rechtsprechung.eigene": lambda: urteile.uebersicht(k.akten),
        "rechtsprechung.sammlung": lambda: urteile.sammlung(k.akten),
        "rechtsprechung.suche": lambda suchtext: urteile.suche(k.akten, suchtext),
        "rechtsprechung.vorschlag": lambda pfad: urteile.vorschlag(pfad),
        "rechtsprechung.ergaenzen": lambda pfad, gericht, aktenzeichen=None, datum=None, herkunft=None,
                akte_id=None, art=None: urteile.ergaenzen(k.akten, akte_id, pfad, k.ablage, gericht,
                                                          aktenzeichen, datum, None, herkunft, art=art),
        "rechtsprechung.zuordnen": lambda urteil_id, akte_id: urteile.zuordnen(
                k.akten, urteil_id, akte_id, k.ablage),
        "rechtsprechung.loesen": lambda urteil_id: urteile.loesen(k.akten, urteil_id, k.ablage),
        "rechtsprechung.entfernen": lambda urteil_id: urteile.aus_sammlung_entfernen(
                k.akten, urteil_id, k.ablage),
        "rechtsprechung.recherche": k.recherche_suche,
        "rechtsprechung.recherche_weiter": lambda quelle: k._recherche_ergebnis(
                lambda: k.recherche.weiter(quelle)),
        "rechtsprechung.recherche_oeffnen": lambda quelle, doknr, treffer=None: k._recherche_ergebnis(
                lambda: urteile.vorschau(k.recherche.daten(quelle, doknr), quelle, treffer)),
        "rechtsprechung.recherche_speichern": lambda quelle, doknr, treffer=None: k._recherche_ergebnis(
                lambda: urteile.in_sammlung(k.akten, k.recherche.daten(quelle, doknr), quelle, k.archiv,
                                            treffer)),
        "rechtsprechung.stand": lambda: verzeichnis.stand(k.con),
        "rechtsprechung.laden": k.rechtsprechung_laden,
        "rechtsprechung.laden_datei": k.rechtsprechung_laden_datei,
        "gerichte.stand": lambda: gerichte.stand(k.con),
        "gerichte.laden": k.gerichte_laden,
        "gerichte.laden_datei": k.gerichte_laden_datei,
        "gerichte.namen": lambda: gerichte.namen(k.con),
        "gerichte.verzeichnis_oeffnen": lambda: gerichte.verzeichnis_oeffnen(),
        "gerichte.zustaendig": k.gerichte_zustaendig,
        "gerichte.suche_einstellungen": lambda: justizadressen.einstellungen(k.gerichtssuche_datei),
        "gerichte.suche_einstellungen_setzen": lambda aktiv: justizadressen.einstellungen_setzen(
                k.gerichtssuche_datei, aktiv),
    }


def _schreibweise_setzen(k: Kern, von: str, nach: str) -> dict:
    """Eigene Schreibweise merken und betroffene Zitate in allen Akten sofort neu prüfen."""
    alt = wissensbasis.gemeintes_gesetz(k.con, von)
    neu = wissensbasis.schreibweise_setzen(k.con, von, nach)
    geprueft = akte.normzitate_eines_gesetzes_neu_pruefen(k.akten, k.con, [von, *([alt] if alt else [])])
    return neu | geprueft


def _schreibweise_loeschen(k: Kern, von: str) -> dict:
    wissensbasis.schreibweise_loeschen(k.con, von)
    return akte.normzitate_eines_gesetzes_neu_pruefen(k.akten, k.con, [von])
