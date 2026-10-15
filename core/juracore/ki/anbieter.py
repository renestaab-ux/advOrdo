"""Anbindung lokaler Sprachmodelle: Ollama und Programme mit OpenAI-kompatibler Schnittstelle (LM Studio).

Im Modus „Nur lokal“ darf der Endpunkt nur auf diesem Gerät liegen (localhost,
127.0.0.1, ::1). Andere Adressen werden abgelehnt, bevor eine Verbindung
entsteht; der Kern öffnet dabei selbst keinen Port, er ist nur Client des
lokalen Modellprogramms. Proxy-Einstellungen des Systems werden bewusst
umgangen, damit Dokumentinhalte nicht über einen Proxy laufen.

Das Modell antwortet ausschließlich mit JSON nach einem vorgegebenen Schema
(strukturierte Ausgabe). Temperatur 0 und ein fester Startwert machen die
Antworten so reproduzierbar, wie es das Modellprogramm zulässt.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

log = logging.getLogger("juracore.ki")

OLLAMA = "ollama"
OPENAI = "openai"  # OpenAI-kompatible lokale Schnittstelle, z. B. LM Studio

ANBIETER = {
    OLLAMA: {"titel": "Ollama", "endpunkt": "http://127.0.0.1:11434"},
    OPENAI: {"titel": "LM Studio (OpenAI-kompatibel)", "endpunkt": "http://127.0.0.1:1234"},
}

# Für eine RTX-Karte mit 16 GB: Qwen3 14B (Q4) belegt rund 9 GB und lässt Platz für 16 000 Token Kontext.
EMPFOHLENES_MODELL = "qwen3:14b"


class KiFehler(RuntimeError):
    """Das Sprachmodell ist nicht erreichbar oder hat unbrauchbar geantwortet."""


@dataclass
class KiEinstellungen:
    anbieter: str = OLLAMA
    endpunkt: str = ANBIETER[OLLAMA]["endpunkt"]
    modell: str = ""
    kontext: int = 16384  # Token, die das Modell auf einmal sieht (Eingabe und Antwort)

    def pruefen(self) -> KiEinstellungen:
        if self.anbieter not in ANBIETER:
            raise ValueError(f"Unbekannter Anbieter: {self.anbieter!r}")
        self.endpunkt = pruefe_lokal(self.endpunkt)
        self.modell = self.modell.strip()
        self.kontext = int(self.kontext)
        if not 2048 <= self.kontext <= 262144:
            raise ValueError("Der Kontext muss zwischen 2048 und 262144 Token liegen.")
        return self


def pruefe_lokal(endpunkt: str) -> str:
    """Lässt nur Endpunkte auf diesem Gerät zu; liefert die Adresse ohne abschließenden Schrägstrich."""
    endpunkt = endpunkt.strip().rstrip("/")
    teile = urlsplit(endpunkt)
    if teile.scheme not in ("http", "https") or not teile.hostname:
        raise ValueError(f"Ungültiger Endpunkt: {endpunkt!r} (erwartet z. B. http://127.0.0.1:11434)")
    host = teile.hostname
    lokal = host == "localhost"
    if not lokal:
        try:
            lokal = ipaddress.ip_address(host).is_loopback
        except ValueError:
            lokal = False
    if not lokal:
        raise ValueError(
            f"Im Modus „Nur lokal“ muss das Sprachmodell auf diesem Gerät laufen (localhost oder 127.0.0.1), "
            f"nicht unter {host}. Dokumentinhalte verlassen das Gerät nicht."
        )
    return endpunkt


def lade_einstellungen(pfad: Path) -> KiEinstellungen:
    if not pfad.is_file():
        return KiEinstellungen()
    try:
        roh = json.loads(pfad.read_text(encoding="utf-8"))
        bekannt = {k: v for k, v in roh.items() if k in KiEinstellungen.__dataclass_fields__}
        return KiEinstellungen(**bekannt).pruefen()
    except (ValueError, TypeError) as fehler:
        log.warning("Einstellungen des Sprachmodells unlesbar (%s), nehme Voreinstellung", fehler)
        return KiEinstellungen()


def speichere_einstellungen(pfad: Path, e: KiEinstellungen) -> dict:
    e.pruefen()
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(asdict(e), ensure_ascii=False, indent=2), encoding="utf-8")
    return asdict(e)


class Anbieter(Protocol):
    modell: str

    def modelle(self) -> list[dict]: ...

    def chat(self, system: str, nutzer: str, schema: dict) -> dict: ...


# Ohne Proxy: Anfragen an das lokale Modell sollen nie über einen (Firmen-)Proxy laufen.
_OEFFNER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class _Http:
    def __init__(self, endpunkt: str, titel: str):
        self.endpunkt = pruefe_lokal(endpunkt)
        self.titel = titel

    def anfrage(self, pfad: str, daten: dict | None = None, timeout: float = 600) -> dict:
        koerper = None if daten is None else json.dumps(daten, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.endpunkt + pfad,
            data=koerper,
            headers={"Content-Type": "application/json"},
            method="GET" if daten is None else "POST",
        )
        try:
            with _OEFFNER.open(req, timeout=timeout) as antwort:
                return json.loads(antwort.read().decode("utf-8"))
        except urllib.error.HTTPError as fehler:
            text = fehler.read().decode("utf-8", "replace")
            try:
                text = json.loads(text).get("error", text)
                if isinstance(text, dict):
                    text = text.get("message", str(text))
            except ValueError:
                pass
            raise KiFehler(f"{self.titel} meldet Fehler {fehler.code}: {text}") from fehler
        except (urllib.error.URLError, TimeoutError, ConnectionError) as fehler:
            grund = getattr(fehler, "reason", fehler)
            raise KiFehler(
                f"{self.titel} ist unter {self.endpunkt} nicht erreichbar ({grund}). Läuft das Programm?"
            ) from fehler
        except ValueError as fehler:
            raise KiFehler(f"{self.titel} hat keine gültige JSON-Antwort geliefert.") from fehler


# Höchstlänge einer Antwort in Token. Reicht für jede Aufgabe der Analyse; ein Modell, das sich in einer
# Wiederholung verfängt, bricht so nach Sekunden statt nach Minuten ab und wird erneut gefragt.
ANTWORT_TOKEN = 4096


def lies_json(text: str, abgeschnitten: bool = False) -> dict:
    """Die Antwort als JSON-Objekt; Denkabschnitte (<think>…</think>) und Code-Zäune werden entfernt.

    ``abgeschnitten``: Das Programm meldet, dass die Antwort an der Längengrenze endete.
    """
    if abgeschnitten:
        raise KiFehler("Die Antwort des Modells ist abgeschnitten (Längengrenze erreicht), kein vollständiges JSON.")
    if not text.strip():
        raise KiFehler("Die Antwort des Modells ist leer, kein JSON.")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    try:
        wert = json.loads(text)
    except ValueError:
        start, ende = text.find("{"), text.rfind("}")
        if start >= 0 and ende <= start:
            raise KiFehler("Die Antwort des Modells bricht mitten im JSON ab.") from None
        if start < 0:
            raise KiFehler("Die Antwort des Modells ist kein JSON.") from None
        try:
            wert = json.loads(text[start : ende + 1])
        except ValueError:
            raise KiFehler("Die Antwort des Modells ist kein gültiges JSON.") from None
    if not isinstance(wert, dict):
        raise KiFehler("Die Antwort des Modells ist kein JSON-Objekt.")
    return wert


class Ollama:
    def __init__(self, endpunkt: str, modell: str, kontext: int = 16384):
        self.http = _Http(endpunkt, "Ollama")
        self.modell = modell
        self.kontext = kontext
        self._denkt: bool | None = None

    def modelle(self) -> list[dict]:
        antwort = self.http.anfrage("/api/tags", timeout=5)
        return [
            {
                "name": m.get("name") or m.get("model"),
                "groesse": m.get("size"),
                "parameter": (m.get("details") or {}).get("parameter_size"),
                "quantisierung": (m.get("details") or {}).get("quantization_level"),
            }
            for m in antwort.get("models", [])
        ]

    def _kann_denken(self) -> bool:
        # Denkende Modelle (Qwen3 u. a.) sind ohne Denkphase deutlich schneller; das Schema sichert die Form.
        if self._denkt is None:
            try:
                info = self.http.anfrage("/api/show", {"model": self.modell}, timeout=10)
                self._denkt = "thinking" in (info.get("capabilities") or [])
            except KiFehler:
                self._denkt = False
        return self._denkt

    def chat(self, system: str, nutzer: str, schema: dict) -> dict:
        if not self.modell:
            raise KiFehler("Kein Modell gewählt. Bitte unter „Einstellungen“ ein installiertes Modell auswählen.")
        daten: dict[str, Any] = {
            "model": self.modell,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": nutzer}],
            "stream": False,
            "format": schema,
            "options": {"temperature": 0, "seed": 42, "num_ctx": self.kontext, "num_predict": ANTWORT_TOKEN},
            "keep_alive": "15m",
        }
        if self._kann_denken():
            daten["think"] = False
        antwort = self.http.anfrage("/api/chat", daten)
        return lies_json((antwort.get("message") or {}).get("content", ""), antwort.get("done_reason") == "length")


class OpenAIKompatibel:
    """Lokale Programme mit OpenAI-Schnittstelle (LM Studio, llama.cpp-Server, vLLM auf localhost)."""

    def __init__(self, endpunkt: str, modell: str, kontext: int = 16384):
        self.http = _Http(endpunkt, "LM Studio")
        self.modell = modell
        self.kontext = kontext

    def modelle(self) -> list[dict]:
        antwort = self.http.anfrage("/v1/models", timeout=5)
        return [{"name": m.get("id"), "groesse": None, "parameter": None, "quantisierung": None}
                for m in antwort.get("data", [])]

    def chat(self, system: str, nutzer: str, schema: dict) -> dict:
        if not self.modell:
            raise KiFehler("Kein Modell gewählt. Bitte unter „Einstellungen“ ein geladenes Modell auswählen.")
        antwort = self.http.anfrage(
            "/v1/chat/completions",
            {
                "model": self.modell,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": nutzer}],
                "temperature": 0,
                "seed": 42,
                "max_tokens": ANTWORT_TOKEN,
                "stream": False,
                "response_format": {"type": "json_schema", "json_schema": {"name": "antwort", "schema": schema}},
            },
        )
        auswahl = antwort.get("choices") or [{}]
        inhalt = (auswahl[0].get("message") or {}).get("content") or ""
        return lies_json(inhalt, auswahl[0].get("finish_reason") == "length")


def erzeuge(e: KiEinstellungen) -> Anbieter:
    e.pruefen()
    klasse = Ollama if e.anbieter == OLLAMA else OpenAIKompatibel
    return klasse(e.endpunkt, e.modell, e.kontext)


def status(e: KiEinstellungen) -> dict:
    """Ob das Modellprogramm läuft, welche Modelle installiert sind und ob das gewählte dabei ist."""
    ergebnis: dict[str, Any] = {
        **asdict(e),
        "anbieter_titel": ANBIETER[e.anbieter]["titel"],
        "anbieter_liste": [{"id": k, **v} for k, v in ANBIETER.items()],
        "empfohlen": EMPFOHLENES_MODELL,
        "erreichbar": False,
        "modelle": [],
        "bereit": False,
        "hinweis": None,
    }
    try:
        ergebnis["modelle"] = erzeuge(e).modelle()
        ergebnis["erreichbar"] = True
    except (KiFehler, ValueError) as fehler:
        ergebnis["hinweis"] = str(fehler)
        return ergebnis
    namen = {m["name"] for m in ergebnis["modelle"]}
    namen |= {n.removesuffix(":latest") for n in namen}
    if not namen:
        ergebnis["hinweis"] = f"Noch kein Modell installiert. Vorschlag: ollama pull {EMPFOHLENES_MODELL}"
    elif not e.modell:
        ergebnis["hinweis"] = "Bitte ein Modell auswählen."
    elif e.modell not in namen:
        ergebnis["hinweis"] = f"Das gewählte Modell {e.modell} ist nicht installiert."
    else:
        ergebnis["bereit"] = True
    return ergebnis
