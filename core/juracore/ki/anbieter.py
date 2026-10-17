"""Anbindung von Sprachmodellen: lokal (Ollama, LM Studio) und, nur ausdrücklich freigeschaltet, externe Anbieter.

Im Modus „Nur lokal“ darf der Endpunkt nur auf diesem Gerät liegen (localhost,
127.0.0.1, ::1). Andere Adressen werden abgelehnt, bevor eine Verbindung
entsteht; der Kern öffnet dabei selbst keinen Port, er ist nur Client des
lokalen Modellprogramms. Proxy-Einstellungen des Systems werden bewusst
umgangen, damit Dokumentinhalte nicht über einen Proxy laufen.

Der Modus „Externer Anbieter“ (Anthropic, OpenAI, Google, Mistral oder ein
anderer Dienst mit OpenAI-kompatibler Schnittstelle) sendet Fragen und
Dokumenttexte an diesen Anbieter. Er ist nur wählbar, wenn der Schalter
„Externe KI einbinden“ in den Einstellungen bewusst eingeschaltet wurde
(``extern_freigegeben``); ohne ihn bleibt jede Anfrage auf dem Gerät. Externe
Adressen müssen HTTPS verwenden. Die API-Schlüssel liegen in einer eigenen Datei
im Datenverzeichnis und werden nie an die Oberfläche zurückgegeben.

Das Modell antwortet ausschließlich mit JSON nach einem vorgegebenen Schema
(strukturierte Ausgabe). Temperatur 0 und ein fester Startwert machen die
Antworten so reproduzierbar, wie es das Modellprogramm zulässt.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
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

LOKAL = "lokal"
EXTERN = "extern"

ANTHROPIC = "anthropic"
ANDERER = "anderer"
# Externe Anbieter. „vorschlag“ ist nur eine Vorbelegung; die Liste der Modelle liefert der Anbieter selbst.
EXTERNE = {
    ANTHROPIC: {"titel": "Anthropic Claude", "adresse": "https://api.anthropic.com", "vorschlag": "claude-opus-5-5"},
    "openai_cloud": {"titel": "OpenAI", "adresse": "https://api.openai.com/v1", "vorschlag": ""},
    "gemini": {"titel": "Google Gemini", "adresse": "https://generativelanguage.googleapis.com/v1beta/openai",
               "vorschlag": ""},
    "mistral": {"titel": "Mistral AI", "adresse": "https://api.mistral.ai/v1", "vorschlag": "mistral-large-latest"},
    ANDERER: {"titel": "Anderer Anbieter (OpenAI-kompatibel)", "adresse": "", "vorschlag": ""},
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
    # Externe KI: nur nach dem Schalter „Externe KI einbinden“ (freigegeben) und der Wahl „extern“ (aktiv) in Gebrauch.
    aktiv: str = LOKAL
    extern_freigegeben: bool = False
    extern_anbieter: str = ANTHROPIC
    extern_modell: str = ""
    extern_adresse: str = ""  # nur für ANDERER; sonst die feste Adresse des Anbieters
    extern_kontext: int = 32768

    def pruefen(self) -> KiEinstellungen:
        if self.anbieter not in ANBIETER:
            raise ValueError(f"Unbekannter Anbieter: {self.anbieter!r}")
        self.endpunkt = pruefe_lokal(self.endpunkt)
        self.modell = self.modell.strip()
        self.kontext = _pruefe_kontext(self.kontext)
        if self.extern_anbieter not in EXTERNE:
            raise ValueError(f"Unbekannter externer Anbieter: {self.extern_anbieter!r}")
        self.extern_freigegeben = bool(self.extern_freigegeben)
        self.extern_modell = self.extern_modell.strip()
        self.extern_kontext = _pruefe_kontext(self.extern_kontext)
        if self.extern_anbieter == ANDERER and self.extern_adresse.strip():
            self.extern_adresse = pruefe_extern(self.extern_adresse)
        if self.aktiv not in (LOKAL, EXTERN):
            raise ValueError(f"Unbekannte Wahl des Sprachmodells: {self.aktiv!r}")
        if not self.extern_freigegeben:
            self.aktiv = LOKAL  # ohne den Schalter nie extern
        return self

    @property
    def extern(self) -> bool:
        """Ob Anfragen an einen externen Anbieter gehen (Dokumentinhalte verlassen das Gerät)."""
        return self.aktiv == EXTERN and self.extern_freigegeben

    @property
    def aktives_modell(self) -> str:
        return self.extern_modell if self.extern else self.modell

    @property
    def aktiver_kontext(self) -> int:
        return self.extern_kontext if self.extern else self.kontext

    @property
    def externe_adresse(self) -> str:
        return self.extern_adresse if self.extern_anbieter == ANDERER else EXTERNE[self.extern_anbieter]["adresse"]


def _pruefe_kontext(kontext: object) -> int:
    kontext = int(kontext)  # type: ignore[call-overload]
    if not 2048 <= kontext <= 262144:
        raise ValueError("Der Kontext muss zwischen 2048 und 262144 Token liegen.")
    return kontext


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


def pruefe_extern(adresse: str) -> str:
    """Externe Adressen nur verschlüsselt (HTTPS); liefert die Adresse ohne abschließenden Schrägstrich."""
    adresse = adresse.strip().rstrip("/")
    teile = urlsplit(adresse)
    if teile.scheme != "https" or not teile.hostname:
        raise ValueError(f"Ein externer Anbieter braucht eine HTTPS-Adresse (https://…), nicht {adresse!r}.")
    return adresse


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


# --- API-Schlüssel externer Anbieter ----------------------------------------------------------------
# Eine eigene Datei neben ki.json, damit Einstellungen ohne Schlüssel weitergegeben werden können. Unter Linux und
# macOS nur für den Benutzer lesbar; unter Windows liegt sie im Benutzerprofil (AppData).


def lade_schluessel(pfad: Path, anbieter: str) -> str | None:
    try:
        wert = json.loads(pfad.read_text(encoding="utf-8")).get(anbieter)
    except (OSError, ValueError, AttributeError):
        return None
    return wert if isinstance(wert, str) and wert.strip() else None


def speichere_schluessel(pfad: Path, anbieter: str, wert: str | None) -> None:
    """Hinterlegt den Schlüssel eines Anbieters; ``None`` oder leer löscht ihn."""
    try:
        alle = json.loads(pfad.read_text(encoding="utf-8"))
        alle = alle if isinstance(alle, dict) else {}
    except (OSError, ValueError):
        alle = {}
    if wert and wert.strip():
        alle[anbieter] = wert.strip()
    else:
        alle.pop(anbieter, None)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    neu = pfad.with_suffix(".tmp")
    with open(os.open(neu, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        json.dump(alle, f, ensure_ascii=False, indent=2)
    os.replace(neu, pfad)


class Anbieter(Protocol):
    modell: str

    def modelle(self) -> list[dict]: ...

    def chat(self, system: str, nutzer: str, schema: dict) -> dict: ...


# Ohne Proxy: Anfragen an das lokale Modell sollen nie über einen (Firmen-)Proxy laufen.
_OEFFNER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


# Externe Anbieter dagegen über den Proxy des Systems, wie ein Browser (Kanzleinetze erlauben oft nur diesen Weg).
_OEFFNER_EXTERN = urllib.request.build_opener()


def _fehlertext(roh: str) -> str:
    """Die Meldung aus einer Fehlerantwort (OpenAI, Anthropic, Google und Mistral verpacken sie verschieden)."""
    try:
        wert: Any = json.loads(roh)
    except ValueError:
        return roh[:500]
    if isinstance(wert, list) and wert:
        wert = wert[0]
    if isinstance(wert, dict):
        wert = wert.get("error", wert.get("message", wert))
    if isinstance(wert, dict):
        wert = wert.get("message", wert)
    return str(wert)[:500]


class _Http:
    def __init__(self, endpunkt: str, titel: str, kopf: dict[str, str] | None = None, extern: bool = False):
        self.endpunkt = pruefe_extern(endpunkt) if extern else pruefe_lokal(endpunkt)
        self.titel = titel
        self.kopf = kopf or {}
        self.extern = extern

    def anfrage(self, pfad: str, daten: dict | None = None, timeout: float = 600) -> dict:
        koerper = None if daten is None else json.dumps(daten, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.endpunkt + pfad,
            data=koerper,
            headers={"Content-Type": "application/json", **self.kopf},
            method="GET" if daten is None else "POST",
        )
        oeffner = _OEFFNER_EXTERN if self.extern else _OEFFNER
        try:
            with oeffner.open(req, timeout=timeout) as antwort:
                return json.loads(antwort.read().decode("utf-8"))
        except urllib.error.HTTPError as fehler:
            text = _fehlertext(fehler.read().decode("utf-8", "replace"))
            if self.extern and fehler.code in (401, 403):
                text += " (API-Schlüssel prüfen)"
            raise KiFehler(f"{self.titel} meldet Fehler {fehler.code}: {text}") from fehler
        except (urllib.error.URLError, TimeoutError, ConnectionError) as fehler:
            grund = getattr(fehler, "reason", fehler)
            frage = "Besteht eine Internetverbindung?" if self.extern else "Läuft das Programm?"
            raise KiFehler(f"{self.titel} ist unter {self.endpunkt} nicht erreichbar ({grund}). {frage}") from fehler
        except ValueError as fehler:
            raise KiFehler(f"{self.titel} hat keine gültige JSON-Antwort geliefert.") from fehler


# Höchstlänge einer Antwort in Token. Reicht für jede Aufgabe der Analyse, auch wenn das Programm eine Denkphase
# mitzählt; ein Modell, das sich in einer Wiederholung verfängt, bricht so nach wenigen Minuten ab.
ANTWORT_TOKEN = 8192


def lies_json(text: str, abgeschnitten: bool = False, denken: int = 0) -> dict:
    """Die Antwort als JSON-Objekt; Denkabschnitte (<think>…</think>) und Code-Zäune werden entfernt.

    ``abgeschnitten``: Das Programm meldet, dass die Antwort an der Längengrenze endete.
    ``denken``: Zeichen der Denkphase, soweit das Programm sie getrennt liefert (nur für die Meldung).
    """
    if abgeschnitten:
        anteil = f"; Denkphase {denken} Zeichen, Antwort {len(text)} Zeichen" if denken else f"; {len(text)} Zeichen"
        raise KiFehler(f"Die Antwort des Modells ist abgeschnitten (Längengrenze erreicht{anteil}), kein vollständiges "
                       "JSON.")
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
        self.denkphase = 0  # Zeichen der Denkphase in der letzten Antwort

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
        nachricht = antwort.get("message") or {}
        self.denkphase = len(nachricht.get("thinking") or "")
        return lies_json(nachricht.get("content", ""), antwort.get("done_reason") == "length", self.denkphase)


class OpenAIKompatibel:
    """Lokale Programme mit OpenAI-Schnittstelle (LM Studio, llama.cpp-Server, vLLM auf localhost)."""

    def __init__(self, endpunkt: str, modell: str, kontext: int = 16384):
        self.http = _Http(endpunkt, "LM Studio")
        self.modell = modell
        self.kontext = kontext
        self.denkphase = 0  # Zeichen der Denkphase in der letzten Antwort

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
                # Denkphase aus, wo das Programm die Vorlagenoption kennt (llama.cpp-Server, vLLM). LM Studio
                # schaltet sie nur über den Schalter „Reasoning“ in den Modelleinstellungen ab.
                "chat_template_kwargs": {"enable_thinking": False},
                "stream": False,
                "response_format": {"type": "json_schema", "json_schema": {"name": "antwort", "schema": schema}},
            },
        )
        auswahl = antwort.get("choices") or [{}]
        nachricht = auswahl[0].get("message") or {}
        self.denkphase = len(nachricht.get("reasoning_content") or nachricht.get("reasoning") or "")
        return lies_json(nachricht.get("content") or "", auswahl[0].get("finish_reason") == "length",
                         self.denkphase)


# --- Externe Anbieter --------------------------------------------------------------------------------

# Höchstlänge einer Antwort externer Modelle. Größer als lokal: Aktuelle Modelle denken vor der Antwort, und die
# Denkphase zählt mit.
EXTERN_ANTWORT_TOKEN = 16000


def _streng(schema: Any) -> Any:
    """Das Schema mit ``additionalProperties: false`` an jedem Objekt, wie es die strukturierte Ausgabe verlangt."""
    if isinstance(schema, dict):
        neu = {k: _streng(v) for k, v in schema.items()}
        if neu.get("type") == "object":
            neu.setdefault("additionalProperties", False)
        return neu
    if isinstance(schema, list):
        return [_streng(v) for v in schema]
    return schema


class AnthropicClaude:
    """Anthropic Messages API; die Antwort folgt dem Schema über die strukturierte Ausgabe (output_config.format)."""

    def __init__(self, modell: str, schluessel: str, kontext: int = 32768):
        self.http = _Http(EXTERNE[ANTHROPIC]["adresse"], "Anthropic",
                          {"x-api-key": schluessel, "anthropic-version": "2023-06-01"}, extern=True)
        self.modell = modell
        self.kontext = kontext

    def modelle(self) -> list[dict]:
        antwort = self.http.anfrage("/v1/models?limit=100", timeout=15)
        return [{"name": m.get("id"), "groesse": None, "parameter": m.get("display_name"), "quantisierung": None}
                for m in antwort.get("data", []) if m.get("id")]

    def chat(self, system: str, nutzer: str, schema: dict) -> dict:
        if not self.modell:
            raise KiFehler("Kein Modell gewählt. Bitte unter „Einstellungen“ ein Modell des Anbieters auswählen.")
        antwort = self.http.anfrage("/v1/messages", {
            "model": self.modell,
            "max_tokens": EXTERN_ANTWORT_TOKEN,
            "system": system,
            "messages": [{"role": "user", "content": nutzer}],
            "output_config": {"format": {"type": "json_schema", "schema": _streng(schema)}},
        })
        grund = antwort.get("stop_reason")
        if grund == "refusal":
            raise KiFehler("Anthropic hat die Anfrage abgelehnt (Sicherheitsfilter des Anbieters).")
        text = "".join(b.get("text", "") for b in antwort.get("content") or [] if b.get("type") == "text")
        return lies_json(text, grund == "max_tokens")


class OpenAIExtern:
    """Externe Dienste mit OpenAI-Schnittstelle: OpenAI selbst, Google Gemini, Mistral und andere."""

    def __init__(self, adresse: str, titel: str, modell: str, schluessel: str, kontext: int = 32768,
                 token_feld: str = "max_tokens", temperatur: float | None = 0):
        self.http = _Http(adresse, titel, {"Authorization": f"Bearer {schluessel}"}, extern=True)
        self.titel = titel
        self.modell = modell
        self.kontext = kontext
        self.token_feld = token_feld
        self.temperatur = temperatur

    # Modelle für Bilder, Sprache, Einbettungen usw. taugen nicht für Text-Chat.
    _KEIN_CHAT = re.compile(r"embed|whisper|tts|dall-e|image|audio|moderation|transcribe|realtime|search|ocr",
                            re.I)

    def modelle(self) -> list[dict]:
        antwort = self.http.anfrage("/models", timeout=15)
        namen = sorted({str(m.get("id", "")).removeprefix("models/") for m in antwort.get("data", [])} - {""})
        return [{"name": n, "groesse": None, "parameter": None, "quantisierung": None}
                for n in namen if not self._KEIN_CHAT.search(n)]

    def chat(self, system: str, nutzer: str, schema: dict) -> dict:
        if not self.modell:
            raise KiFehler("Kein Modell gewählt. Bitte unter „Einstellungen“ ein Modell des Anbieters auswählen.")
        daten: dict[str, Any] = {
            "model": self.modell,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": nutzer}],
            self.token_feld: EXTERN_ANTWORT_TOKEN,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "antwort", "schema": _streng(schema), "strict": False}},
        }
        if self.temperatur is not None:
            daten["temperature"] = self.temperatur
        antwort = self.http.anfrage("/chat/completions", daten)
        auswahl = antwort.get("choices") or [{}]
        nachricht = auswahl[0].get("message") or {}
        if nachricht.get("refusal"):
            raise KiFehler(f"{self.titel} hat die Anfrage abgelehnt: {nachricht['refusal']}")
        return lies_json(nachricht.get("content") or "", auswahl[0].get("finish_reason") == "length")


def erzeuge_extern(e: KiEinstellungen, schluessel: str | None) -> Anbieter:
    if not e.extern_freigegeben:
        raise KiFehler("Externe KI ist nicht eingebunden. Der Schalter steht unter „Einstellungen“.")
    if not schluessel:
        raise KiFehler(f"Für {EXTERNE[e.extern_anbieter]['titel']} ist kein API-Schlüssel hinterlegt "
                       "(„Einstellungen“ → „Externe KI“).")
    titel = EXTERNE[e.extern_anbieter]["titel"]
    if e.extern_anbieter == ANTHROPIC:
        return AnthropicClaude(e.extern_modell, schluessel, e.extern_kontext)
    if not e.externe_adresse:
        raise KiFehler("Für den anderen Anbieter fehlt die Adresse (https://…/v1).")
    if e.extern_anbieter == "openai_cloud":
        # Neuere OpenAI-Modelle verlangen max_completion_tokens und lassen keine eigene Temperatur zu.
        return OpenAIExtern(e.externe_adresse, titel, e.extern_modell, schluessel, e.extern_kontext,
                            "max_completion_tokens", None)
    return OpenAIExtern(e.externe_adresse, titel, e.extern_modell, schluessel, e.extern_kontext)


def erzeuge_aktiv(e: KiEinstellungen, schluessel: str | None = None) -> Anbieter:
    """Das gewählte Modell: lokal, oder extern, wenn der Schalter an ist und „extern“ gewählt wurde."""
    e.pruefen()
    return erzeuge_extern(e, schluessel) if e.extern else erzeuge(e)


def denkt(modell: Anbieter) -> int:
    """Zeichen der Denkphase bei einer kleinen Probeanfrage; 0, wenn das Modell ohne Denkphase antwortet.

    Eine Denkphase kostet bei jeder Anfrage Minuten und kann die Antwort an der Längengrenze abschneiden.
    """
    modell.chat("Antworte nur mit JSON.", 'Gib {"ok": true} zurück.',
                {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]})
    return getattr(modell, "denkphase", 0)


def erzeuge(e: KiEinstellungen) -> Anbieter:
    """Das lokale Modell (die Kommandozeile und ki-pruefen arbeiten immer lokal)."""
    e.pruefen()
    klasse = Ollama if e.anbieter == OLLAMA else OpenAIKompatibel
    return klasse(e.endpunkt, e.modell, e.kontext)


def status(e: KiEinstellungen) -> dict:
    """Ob das Modellprogramm läuft, welche Modelle installiert sind und ob das gewählte dabei ist."""
    ergebnis: dict[str, Any] = {
        "anbieter": e.anbieter,
        "endpunkt": e.endpunkt,
        "modell": e.modell,
        "kontext": e.kontext,
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


def status_extern(e: KiEinstellungen, schluessel: str | None, verbindung: bool = False) -> dict:
    """Stand der externen KI. Der Anbieter wird nur mit ``verbindung`` angefragt (Modellliste, keine Inhalte)."""
    ende = schluessel[-4:] if schluessel and len(schluessel) >= 12 else None
    ergebnis: dict[str, Any] = {
        "freigegeben": e.extern_freigegeben,
        "anbieter": e.extern_anbieter,
        "anbieter_titel": EXTERNE[e.extern_anbieter]["titel"],
        "anbieter_liste": [{"id": k, **v} for k, v in EXTERNE.items()],
        "adresse": e.externe_adresse,
        "modell": e.extern_modell,
        "kontext": e.extern_kontext,
        "schluessel_hinterlegt": bool(schluessel),
        "schluessel_ende": ende,
        "geprueft": False,
        "erreichbar": False,
        "modelle": [],
        "bereit": False,
        "hinweis": None,
    }
    if not e.extern_freigegeben:
        ergebnis["hinweis"] = "Externe KI ist nicht eingebunden."
        return ergebnis
    if not schluessel:
        ergebnis["hinweis"] = "Bitte den API-Schlüssel des Anbieters hinterlegen."
        return ergebnis
    if verbindung:
        ergebnis["geprueft"] = True
        try:
            ergebnis["modelle"] = erzeuge_extern(e, schluessel).modelle()
            ergebnis["erreichbar"] = True
        except (KiFehler, ValueError) as fehler:
            ergebnis["hinweis"] = str(fehler)
            return ergebnis
    if not e.extern_modell:
        ergebnis["hinweis"] = "Bitte ein Modell des Anbieters auswählen."
    elif verbindung and ergebnis["modelle"] and e.extern_modell not in {m["name"] for m in ergebnis["modelle"]}:
        ergebnis["hinweis"] = f"Das Modell {e.extern_modell} bietet {ergebnis['anbieter_titel']} unter diesem " \
                              "Schlüssel nicht an."
    else:
        ergebnis["bereit"] = True
    return ergebnis


def gesamtstatus(e: KiEinstellungen, schluessel: str | None, verbindung: bool = False) -> dict:
    """Für die Oberfläche: das gewählte Modell oben, darunter lokal und extern im Einzelnen."""
    lokal = status(e)
    extern = status_extern(e, schluessel, verbindung)
    aktiv = extern if e.extern else lokal
    return {
        "aktiv": EXTERN if e.extern else LOKAL,
        "extern": e.extern,
        "bereit": aktiv["bereit"],
        "modell": aktiv["modell"],
        "titel": aktiv["anbieter_titel"],
        "kontext": e.aktiver_kontext,
        "hinweis": aktiv["hinweis"],
        "lokal": lokal,
        "externe": extern,
    }
