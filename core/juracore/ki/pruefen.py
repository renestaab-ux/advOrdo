"""Probelauf auf einer Testakte: ``juracore ki-pruefen <ordner> --erwartungen erwartungen.json``.

Liest den Ordner in eine vorübergehende Akte (nichts landet in den Akten der
App), sucht Widersprüche mit dem eingestellten Sprachmodell und gibt sie mit
Fundstellen aus. Mit ``--erwartungen`` wird gezählt, welche der erwarteten
Widersprüche gefunden wurden; so lassen sich Modelle vergleichen.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from .. import db
from ..dokumente import akte
from . import anbieter, belege
from .analyse import Analyse


class _Ausgabe:
    def __init__(self) -> None:
        self.beginn = time.monotonic()

    def melde(self, text: str, schritt: int | None = None, von: int | None = None) -> None:
        print(f"[{time.monotonic() - self.beginn:6.0f} s] {text}", file=sys.stderr, flush=True)

    def pruefe(self) -> None:
        pass


def _ort(f: dict) -> str:
    teile = [f["dateiname"]]
    if f["seite"]:
        teile.append(f"S. {f['seite']}")
    teile.append(f"Rn. {f['rn']}" if f["rn"] else f"Abschn. {f['abschnitt']}")
    return ", ".join(teile)


def _getroffen(erwartet: dict, ergebnis: dict, texte: dict[tuple[int, int], str]) -> bool:
    """Ein erwarteter Widerspruch gilt als gefunden, wenn ein Ergebnis mindestens zwei seiner Aussagen belegt."""
    for w in ergebnis["widersprueche"]:
        stellen = [a["fundstelle"] for a in w["angaben"]]
        treffer = 0
        for aussage in erwartet["aussagen"]:
            gesucht = belege.normalisiere(aussage["text"])[0]
            if any(f["dateiname"].startswith(aussage["dok"])
                   and gesucht in belege.normalisiere(texte[(f["dokument_id"], f["abschnitt"])])[0] for f in stellen):
                treffer += 1
        if treffer >= 2:
            return True
    return False


def main(ordner: Path, e: anbieter.KiEinstellungen, erwartungen: Path | None, zusammenfassung: bool) -> int:
    stand = anbieter.status(e)
    if not stand["bereit"]:
        print(f"Sprachmodell nicht bereit: {stand['hinweis']}", file=sys.stderr)
        return 1
    print(f"Modell: {e.modell} ({stand['anbieter_titel']}, Kontext {e.kontext})", file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix="jda-ki-") as tmp:
        tmp_pfad = Path(tmp)
        akten = akte.oeffne(tmp_pfad / "akten.sqlite")
        wissen = db.oeffne(tmp_pfad / "wissen.sqlite")
        try:
            akte_id = akte.akte_anlegen(akten, ordner.name)["id"]
            funde = akte.ordner_pruefen(ordner)
            tags = {u["herkunft"]: u["tags"] for u in funde["unterordner"]}
            for datei in funde["dateien"]:
                print(f"Lese {datei['relativ']}", file=sys.stderr)
                akte.importiere(akten, wissen, akte_id, datei["pfad"], tmp_pfad / "ablage",
                                tags=tags[datei["herkunft"]], herkunft=datei["herkunft"] or None)
            analyse = Analyse(akten, anbieter.erzeuge(e), e.kontext, _Ausgabe())
            ergebnis = analyse.widersprueche(akte_id)
            print(f"\n{ergebnis['angaben']} Tatsachenangaben mit Beleg, {ergebnis['verworfen']} ohne auffindbares "
                  f"Zitat verworfen.\n{len(ergebnis['widersprueche'])} mögliche Widersprüche:\n")
            for i, w in enumerate(ergebnis["widersprueche"], 1):
                print(f"{i}. {w['thema']} ({w['art']}; {', '.join(w['einordnung'])})\n   {w['erklaerung']}")
                for a in w["angaben"]:
                    print(f"   - {_ort(a['fundstelle'])}: „{a['fundstelle']['ausschnitt']['wert']}“")
                print()
            if zusammenfassung:
                z = analyse.zusammenfassung_akte(akte_id)
                print("Zusammenfassung der Akte:")
                for a in z["aussagen"]:
                    orte = "; ".join(_ort(f) for f in a["fundstellen"]) or "OHNE BELEG"
                    print(f"- [{a['art']}] {a['text']} ({orte})")
                print()
            if erwartungen:
                soll = json.loads(Path(erwartungen).read_text(encoding="utf-8"))
                texte = {(z["dokument_id"], z["nr"]): z["text"] for z in akten.execute(
                    "SELECT dokument_id, nr, text FROM abschnitt")}
                gefunden = [w["id"] for w in soll.get("widersprueche", []) if _getroffen(w, ergebnis, texte)]
                fehlend = [w["id"] for w in soll.get("widersprueche", []) if w["id"] not in gefunden]
                print(f"Erwartete Widersprüche gefunden: {', '.join(gefunden) or 'keiner'}")
                print(f"Nicht gefunden: {', '.join(fehlend) or 'keiner'}")
        finally:
            akten.close()
            wissen.close()
    return 0
