"""Apple Intelligence auf diesem Mac („On-Device“) als lokales Sprachmodell.

Apple bietet sein Modell nur über das Swift-Framework „Foundation Models“ an (macOS 26 oder neuer, Apple Silicon,
Apple Intelligence eingeschaltet). Das kleine Hilfsprogramm ``macos/apple-ki`` übersetzt zwischen beiden Welten: Der
Kern startet es je Anfrage, schreibt JSON auf seine Standardeingabe und liest JSON von seiner Standardausgabe. Es wird
kein Port geöffnet und keine Netzwerkverbindung aufgebaut. Das Hilfsprogramm verwendet ausschließlich das Modell auf
dem Gerät; Private Cloud Compute spricht es nicht an, Dokumentinhalte verlassen den Mac also nicht.

Das Modell ist klein und sieht nur wenige tausend Token auf einmal (macOS 26: 4.096). Die Analyse zerlegt die Akte
deshalb in kleinere Stücke; die Antwortlänge ist auf ein Viertel des Kontexts begrenzt.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .anbieter import ANTWORT_TOKEN, KiFehler, lies_json

TITEL = "Apple Intelligence (auf dem Mac)"
MODELL = "apple-on-device"
KONTEXT = 4096  # Kontext des Modells unter macOS 26
PROGRAMM = "advordo-apple-ki"
BAUEN = "macos/apple-ki/bauen.sh"

_GRUENDE = {
    "geraet": "Dieser Mac unterstützt Apple Intelligence nicht (nötig: Apple Silicon und macOS 26 oder neuer).",
    "nicht_eingeschaltet": "Apple Intelligence ist ausgeschaltet. Einschalten unter Systemeinstellungen → "
                           "„Apple Intelligence & Siri“.",
    "nicht_bereit": "Das Modell von Apple Intelligence ist noch nicht bereit (es wird geladen oder vorbereitet). "
                    "Bitte später erneut prüfen.",
    "unbekannt": "Apple Intelligence ist auf diesem Mac nicht verfügbar.",
}


def moeglich(system: str = sys.platform) -> bool:
    """Ob Apple Intelligence auf diesem Betriebssystem überhaupt in Frage kommt."""
    return system == "darwin"


def programm() -> Path | None:
    """Das übersetzte Hilfsprogramm: neben dem gebündelten Kern oder im Projektordner (Entwicklung)."""
    kandidaten = []
    if eigen := os.environ.get("ADVORDO_APPLE_KI"):
        kandidaten.append(Path(eigen))
    kandidaten.append(Path(sys.executable).resolve().parent / PROGRAMM)
    kandidaten.append(Path(__file__).resolve().parents[3] / "macos" / "apple-ki" / "build" / PROGRAMM)
    for pfad in kandidaten:
        if pfad.is_file() and os.access(pfad, os.X_OK):
            return pfad
    return None


def geordnet(schema: Any) -> Any:
    """Das Schema mit der Reihenfolge der Felder in ``x-reihenfolge`` (JSON-Objekte haben keine feste Reihenfolge,
    das Modell soll die Felder aber in dieser Folge erzeugen, etwa erst den Absatz, dann das Zitat)."""
    if isinstance(schema, dict):
        neu = {k: geordnet(v) for k, v in schema.items() if k != "maxLength"}
        if isinstance(schema.get("properties"), dict):
            neu["x-reihenfolge"] = list(schema["properties"])
        return neu
    if isinstance(schema, list):
        return [geordnet(v) for v in schema]
    return schema


class AppleIntelligence:
    """Das Modell von Apple Intelligence auf diesem Mac, über das Hilfsprogramm."""

    titel = TITEL

    def __init__(self, kontext: int = KONTEXT, pfad: Path | None = None, timeout: float = 600):
        self.modell = MODELL
        self.kontext = kontext
        self.pfad = pfad
        self.timeout = timeout
        self.denkphase = 0  # das Modell hat keine getrennte Denkphase

    @property
    def antwort_token(self) -> int:
        """Höchstlänge einer Antwort: ein Viertel des kleinen Kontexts, damit genug Platz für den Text bleibt."""
        return min(ANTWORT_TOKEN, max(512, self.kontext // 4))

    def _aufruf(self, anfrage: dict, timeout: float) -> dict:
        pfad = self.pfad or programm()
        if pfad is None:
            raise KiFehler(f"Das Hilfsprogramm für Apple Intelligence fehlt. Einmalig im Projektordner ausführen: "
                           f"{BAUEN} (braucht die Xcode-Befehlszeilenwerkzeuge: xcode-select --install).")
        try:
            lauf = subprocess.run([str(pfad)], input=json.dumps(anfrage, ensure_ascii=False).encode("utf-8"),
                                  capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as fehler:
            raise KiFehler(f"Apple Intelligence hat nicht innerhalb von {int(timeout / 60)} Minuten geantwortet.") \
                from fehler
        except OSError as fehler:
            raise KiFehler(f"Das Hilfsprogramm für Apple Intelligence lässt sich nicht starten ({fehler}).") from fehler
        try:
            antwort = json.loads(lauf.stdout.decode("utf-8"))
        except ValueError:
            antwort = None
        if not isinstance(antwort, dict):
            rest = lauf.stderr.decode("utf-8", "replace").strip()[-300:]
            raise KiFehler(f"Das Hilfsprogramm für Apple Intelligence ist ohne Antwort beendet (Code "
                           f"{lauf.returncode}){': ' + rest if rest else ''}. Ist macOS 26 oder neuer installiert?")
        return antwort

    def verfuegbarkeit(self) -> dict:
        antwort = self._aufruf({"aktion": "status"}, timeout=30)
        if not antwort.get("ok"):
            raise KiFehler(str(antwort.get("meldung") or "Apple Intelligence meldet einen Fehler."))
        return antwort

    def modelle(self) -> list[dict]:
        stand = self.verfuegbarkeit()
        if not stand.get("verfuegbar"):
            raise KiFehler(_GRUENDE.get(str(stand.get("grund")), _GRUENDE["unbekannt"]))
        if stand.get("deutsch") is False:
            raise KiFehler("Apple Intelligence unterstützt auf diesem Mac kein Deutsch. Die Sprache von Apple "
                           "Intelligence lässt sich unter Systemeinstellungen → „Apple Intelligence & Siri“ wählen.")
        return [{"name": MODELL, "groesse": None, "parameter": "On-Device", "quantisierung": None}]

    def chat(self, system: str, nutzer: str, schema: dict) -> dict:
        anfrage = {"aktion": "chat", "system": system, "nutzer": nutzer, "schema": geordnet(schema),
                   "antwort_token": self.antwort_token}
        antwort = self._aufruf(anfrage, self.timeout)
        if antwort.get("ok") is not True and antwort.get("fehler") == "schema":
            # Was die geführte Ausgabe nicht abbilden kann, wird als Anweisung mitgegeben und danach geprüft.
            anfrage["schema"] = None
            anfrage["system"] = (f"{system}\n\nAntworte ausschließlich mit einem JSON-Objekt nach diesem Schema:\n"
                                 f"{json.dumps(schema, ensure_ascii=False)}")
            antwort = self._aufruf(anfrage, self.timeout)
        if antwort.get("ok") is True:
            return lies_json(str(antwort.get("text") or ""))
        art, meldung = antwort.get("fehler"), str(antwort.get("meldung") or "")
        if art == "kontext":
            # „abgeschnitten“ und „JSON“: Die Analyse teilt das Stück dann und fragt die Hälften einzeln.
            raise KiFehler(f"Text und Antwort passen nicht in den Kontext von Apple Intelligence ({self.kontext} "
                           "Token); die Antwort ist abgeschnitten, kein vollständiges JSON.")
        if art == "json":
            raise KiFehler("Apple Intelligence hat kein gültiges JSON geliefert.")
        if art == "schutz":
            raise KiFehler("Apple Intelligence lehnt diese Anfrage ab (Inhaltsfilter von Apple). Das kommt bei "
                           "Schilderungen von Gewalt oder Straftaten vor; für solche Akten ein anderes Modell wählen.")
        if art == "sprache":
            raise KiFehler("Apple Intelligence unterstützt die Sprache dieses Textes nicht.")
        if art == "nicht_verfuegbar":
            raise KiFehler(_GRUENDE.get(meldung, _GRUENDE["unbekannt"]))
        if art == "nicht_bereit":
            raise KiFehler(_GRUENDE["nicht_bereit"])
        raise KiFehler(f"Apple Intelligence meldet einen Fehler: {meldung or art}")
