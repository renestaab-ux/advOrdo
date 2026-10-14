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
from ..abgleich import abgleich
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


def _abdeckung(erwartet: dict, treffer_listen: list[list[dict]], texte: dict[tuple[int, int], str]) -> list[str]:
    """Die erwarteten Aussagen (Dokumentkürzel), die das beste einzelne Ergebnis belegt."""
    beste: list[str] = []
    for stellen in treffer_listen:
        belegt = []
        for aussage in erwartet["aussagen"]:
            gesucht = belege.normalisiere(aussage["text"])[0]
            if any(f["dateiname"].startswith(aussage["dok"])
                   and gesucht in belege.normalisiere(texte[(f["dokument_id"], f["abschnitt"])])[0] for f in stellen):
                belegt.append(aussage["dok"])
        if len(belegt) > len(beste):
            beste = belegt
    return beste


def _getroffen(erwartet: dict, treffer_listen: list[list[dict]], texte: dict[tuple[int, int], str]) -> bool:
    """Ein erwarteter Widerspruch gilt als gefunden, wenn ein Ergebnis mindestens zwei seiner Aussagen belegt."""
    return len(_abdeckung(erwartet, treffer_listen, texte)) >= 2


def main(ordner: Path, e: anbieter.KiEinstellungen, erwartungen: Path | None, zusammenfassung: bool) -> int:
    # Pfade vor dem langen Lauf prüfen, nicht erst danach.
    if not Path(ordner).is_dir():
        print(f"Ordner nicht gefunden: {ordner}", file=sys.stderr)
        return 1
    if erwartungen and not Path(erwartungen).is_file():
        print(f"Datei nicht gefunden: {erwartungen} (bitte den vollständigen Pfad angeben)", file=sys.stderr)
        return 1
    beginn = time.monotonic()
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
            # Protokoll mit allen Tatsachenangaben je Dokument (gespeichert, keine neue Anfrage) zum Auswerten.
            ids = [z[0] for z in akten.execute("SELECT id FROM dokument WHERE akte_id = ? ORDER BY id", (akte_id,))]
            protokoll = Path.cwd() / "ki-pruefen-protokoll.json"
            protokoll.write_text(json.dumps(
                {"modell": e.modell, "anbieter": e.anbieter, "kontext": e.kontext,
                 "angaben": [analyse.angaben(i, ziel=False) for i in ids], "ergebnis": ergebnis},
                ensure_ascii=False, indent=1), encoding="utf-8")
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
                modell = [[a["fundstelle"] for a in w["angaben"]] for w in ergebnis["widersprueche"]]
                # Zum Vergleich der regelbasierte Abgleich (Zahlen, Beträge, Daten) aus dem Bereich „Vergleich“.
                regeln = [[f for wert in m["werte"] for f in wert["fundstellen"]]
                          for m in abgleich.abgleich(akten, akte_id)["merkmale"] if m["status"] == "abweichend"]
                soll_w = soll.get("widersprueche", [])
                vom_modell = [w["id"] for w in soll_w if _getroffen(w, modell, texte)]
                vom_abgleich = [w["id"] for w in soll_w if _getroffen(w, regeln, texte)]
                fehlend = [w["id"] for w in soll_w if w["id"] not in vom_modell + vom_abgleich]
                print(f"Erwartete Widersprüche vom Sprachmodell gefunden: {', '.join(vom_modell) or 'keiner'}")
                print(f"Vom regelbasierten Abgleich gefunden: {', '.join(vom_abgleich) or 'keiner'}")
                print(f"Von keinem gefunden: {', '.join(fehlend) or 'keiner'}")
                for w in soll_w:
                    if w["id"] in fehlend:
                        teil = _abdeckung(w, modell, texte)
                        fehlt = [a["dok"] for a in w["aussagen"] if a["dok"] not in teil]
                        if teil:
                            print(f"  {w['id']} teilweise: Fundstelle aus {', '.join(teil)} genannt, "
                                  f"aus {', '.join(fehlt)} nicht")
            print(f"\nDauer: {(time.monotonic() - beginn) / 60:.1f} min. Protokoll: {protokoll}")
        finally:
            akten.close()
            wissen.close()
    return 0
