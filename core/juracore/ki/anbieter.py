"""Anbindung von Sprachmodellen: lokal (Ollama, LM Studio) und, nur ausdrücklich freigeschaltet, externe Anbieter.

Im Modus „Lokal“ darf der Endpunkt nur auf diesem Gerät (localhost, 127.0.0.1,
::1) oder im eigenen Netzwerk liegen: private Adressen (192.168.x.x, 10.x.x.x,
172.16–31.x.x, fc00::/7, fe80::/10) und Rechnernamen ohne Punkt oder mit einer
Endung des Heimnetzes (.local, .lan, .fritz.box, .home.arpa …). Ein Name muss
beim Verbinden auf eine solche Adresse zeigen. Andere Adressen werden
abgelehnt, bevor eine Verbindung entsteht; der Kern öffnet dabei selbst keinen
Port, er ist nur Client des Modellprogramms. Proxy-Einstellungen des Systems
werden bewusst umgangen, damit Dokumentinhalte nicht über einen Proxy laufen.

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

Mit dem Schalter „KI verwenden“ (``abgeschaltet``) lässt sich die KI ganz ausschalten: Dann fragt die App kein
Sprachmodell, weder lokal noch extern, und prüft auch keine Verbindung. Die übrigen Einstellungen bleiben erhalten.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from .. import netzprotokoll

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
    "gemini": {"titel": "Google Gemini", "adresse": "https://generativelanguage.googleapis.com/v1beta",
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
    # Schalter „KI verwenden“: ausgeschaltet fragt die App kein Sprachmodell, die Einstellungen oben bleiben.
    abgeschaltet: bool = False

    def pruefen(self) -> KiEinstellungen:
        self.abgeschaltet = bool(self.abgeschaltet)
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


GERAET = "geraet"  # das Modell läuft auf diesem Rechner
NETZWERK = "netzwerk"  # das Modell läuft auf einem anderen Rechner im eigenen Netzwerk

# Namensendungen, die nur im eigenen Netz aufgelöst werden (mDNS, Router, RFC 8375).
_HEIMNETZ_ENDUNGEN = (".local", ".lan", ".home", ".home.arpa", ".internal", ".localdomain", ".fritz.box",
                      ".speedport.ip")


def _adresse_ort(adresse: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    if adresse.is_loopback:
        return GERAET
    if isinstance(adresse, ipaddress.IPv6Address) and adresse.ipv4_mapped:
        return _adresse_ort(adresse.ipv4_mapped)
    if adresse.is_unspecified or adresse.is_multicast or adresse.is_reserved:
        return None
    netze = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "fc00::/7", "fe80::/10")
    if any(adresse in ipaddress.ip_network(n) for n in netze):
        return NETZWERK
    return None


def ort(host: str) -> str | None:
    """Wo ein Host liegt: ``GERAET``, ``NETZWERK`` oder ``None`` (außerhalb des eigenen Netzes).

    Nur nach der Schreibweise, ohne Namensauflösung; die Auflösung prüft ``_pruefe_aufloesung`` beim Verbinden.
    """
    host = host.strip().strip("[]").lower().rstrip(".")
    if host == "localhost":
        return GERAET
    try:
        return _adresse_ort(ipaddress.ip_address(host.split("%")[0]))
    except ValueError:
        pass
    if not re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*", host):
        return None
    if host.endswith(".localhost"):
        return GERAET
    if "." not in host or host.endswith(_HEIMNETZ_ENDUNGEN):
        return NETZWERK
    return None


def endpunkt_ort(endpunkt: str) -> str:
    """``GERAET`` oder ``NETZWERK`` für einen zulässigen lokalen Endpunkt."""
    return ort(urlsplit(endpunkt).hostname or "") or NETZWERK


def pruefe_lokal(endpunkt: str) -> str:
    """Lässt nur Endpunkte auf diesem Gerät oder im eigenen Netzwerk zu; liefert die Adresse ohne Schrägstrich."""
    endpunkt = endpunkt.strip().rstrip("/")
    teile = urlsplit(endpunkt)
    if teile.scheme not in ("http", "https") or not teile.hostname:
        raise ValueError(f"Ungültiger Endpunkt: {endpunkt!r} (erwartet z. B. http://127.0.0.1:11434 oder "
                         "http://192.168.178.20:1234)")
    if ort(teile.hostname) is None:
        raise ValueError(
            f"Im Modus „Lokal“ muss das Sprachmodell auf diesem Gerät oder im eigenen Netzwerk laufen (etwa "
            f"127.0.0.1, 192.168.x.x, 10.x.x.x oder ein Rechnername wie pc-buero.local), nicht unter "
            f"{teile.hostname}. Dokumentinhalte verlassen das eigene Netz nicht."
        )
    return endpunkt


def _pruefe_aufloesung(endpunkt: str) -> None:
    """Ein Rechnername muss ausschließlich auf Adressen des Geräts oder des eigenen Netzes zeigen."""
    teile = urlsplit(endpunkt)
    host = teile.hostname or ""
    try:
        ipaddress.ip_address(host.split("%")[0])
        return  # eine Adresse hat pruefe_lokal schon beurteilt
    except ValueError:
        pass
    try:
        eintraege = socket.getaddrinfo(host, teile.port or 80, proto=socket.IPPROTO_TCP)
    except OSError as fehler:
        raise KiFehler(f"Der Rechnername {host} lässt sich nicht auflösen ({fehler}). Läuft der Rechner, und "
                       "stimmt der Name? Sonst die IP-Adresse eintragen.") from fehler
    for eintrag in eintraege:
        adresse = ipaddress.ip_address(str(eintrag[4][0]).split("%")[0])
        if _adresse_ort(adresse) is None:
            raise KiFehler(f"Der Rechnername {host} zeigt auf {adresse}, eine Adresse außerhalb des eigenen "
                           "Netzes. Im Modus „Lokal“ wird dorthin nichts gesendet.")


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


def _oeffner(extern: bool) -> urllib.request.OpenerDirector:
    """Externe Anbieter über den Proxy des Systems, wie ein Browser (Kanzleinetze erlauben oft nur diesen Weg); das
    lokale Modell nie über einen (Firmen-)Proxy. Beide mit Protokoll der Online-Anfragen."""
    return netzprotokoll.oeffner() if extern else netzprotokoll.oeffner(urllib.request.ProxyHandler({}))


def _beschreibung(pfad: str, daten: dict | None, koerper: bytes | None) -> str:
    """Was das Protokoll über eine Anfrage an das Modell festhält: Modell und Umfang, nie den Text."""
    if koerper is None:
        return ""
    modell = (daten or {}).get("model") or (m.group(1) if (m := re.search(r"/models/([^/:]+)", pfad)) else "")
    zeichen = f"{len(koerper.decode('utf-8', 'replace')):,}".replace(",", ".")
    return f"Anfrage an {modell or 'das Modell'}: {zeichen} Zeichen (Text nicht protokolliert)"


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


def _warten_laut(fehler: urllib.error.HTTPError, vorgabe: float) -> float:
    """Wartezeit nach „zu viele Anfragen“: die Angabe ``Retry-After`` des Anbieters (höchstens 60 s), sonst die
    Vorgabe."""
    try:
        return min(max(float(fehler.headers.get("Retry-After") or vorgabe), 0.0), 60.0)
    except (TypeError, ValueError, AttributeError):
        return vorgabe


class _Http:
    # Wartezeiten (Sekunden), wenn ein externer Anbieter mit 429 „zu viele Anfragen“ antwortet; danach gilt der Fehler.
    WARTEN_429: tuple[float, ...] = (5.0, 15.0, 30.0)

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
        zweck = f"Sprachmodell ({self.titel})" + (" – Modelle abfragen" if daten is None else "")
        netzprotokoll.kennzeichnen(req, zweck, _beschreibung(pfad, daten, koerper))
        oeffner = _oeffner(self.extern)
        if not self.extern:
            _pruefe_aufloesung(self.endpunkt)
        gewartet = 0
        while True:
            try:
                with oeffner.open(req, timeout=timeout) as antwort:
                    return json.loads(antwort.read().decode("utf-8"))
            except urllib.error.HTTPError as fehler:
                text = _fehlertext(fehler.read().decode("utf-8", "replace"))
                if self.extern and fehler.code == 429 and gewartet < len(self.WARTEN_429):
                    pause = _warten_laut(fehler, self.WARTEN_429[gewartet])
                    log.info("%s: zu viele Anfragen, warte %.0f s", self.titel, pause)
                    time.sleep(pause)
                    gewartet += 1
                    continue
                if self.extern and fehler.code in (401, 403):
                    text += " (API-Schlüssel prüfen)"
                if self.extern and fehler.code == 429:
                    raise KiFehler(
                        f"{self.titel} lässt gerade keine weiteren Anfragen zu (Fehler 429: {text}); JuraBox hat "
                        f"{gewartet}-mal gewartet und es erneut versucht. Kostenlose Tarife erlauben nur wenige "
                        "Anfragen je Minute: einige Minuten warten, eine kleinere Aufgabe wählen (etwa ein Dokument "
                        "statt der ganzen Akte) oder beim Anbieter ein höheres Limit buchen.") from fehler
                raise KiFehler(f"{self.titel} meldet Fehler {fehler.code}: {text}") from fehler
            except (urllib.error.URLError, TimeoutError, ConnectionError) as fehler:
                grund = getattr(fehler, "reason", fehler)
                if isinstance(grund, TimeoutError) or "timed out" in str(grund):
                    raise KiFehler(f"{self.titel} hat nicht innerhalb von {int(timeout / 60)} Minuten geantwortet. "
                                   "Das Modell braucht für diese Anfrage zu lange; weniger Zusatzwissen (etwa ohne "
                                   "Gesetze) oder eine kürzere Frage hilft.") from fehler
                frage = "Besteht eine Internetverbindung?" if self.extern else "Läuft das Programm?"
                raise KiFehler(
                    f"{self.titel} ist unter {self.endpunkt} nicht erreichbar ({grund}). {frage}") from fehler
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
    """Das Schema mit ``additionalProperties: false`` an jedem Objekt, wie es die strukturierte Ausgabe verlangt.

    Längengrenzen (``maxItems``, ``maxLength``) entfallen: Sie bremsen nur lokale Modelle, die sich in Wiederholungen
    verfangen, und nicht jeder externe Anbieter nimmt sie an."""
    if isinstance(schema, dict):
        neu = {k: _streng(v) for k, v in schema.items() if k not in ("maxItems", "maxLength")}
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


class GoogleGemini:
    """Gemini über die eigene Schnittstelle (generateContent) mit JSON-Schema (responseJsonSchema).

    Die OpenAI-kompatible Schnittstelle von Google beantwortete strukturierte Anfragen mit „Fehler 500: Internal
    error encountered“. Meldet Google auch hier einen Serverfehler, folgt ein zweiter Versuch ohne Schema-Zwang: Das
    Schema steht dann in der Anweisung, die Antwort muss trotzdem JSON sein und wird wie jede andere geprüft.
    """

    def __init__(self, modell: str, schluessel: str, kontext: int = 32768):
        self.http = _Http(EXTERNE["gemini"]["adresse"], "Google Gemini", {"x-goog-api-key": schluessel}, extern=True)
        self.modell = modell.removeprefix("models/")
        self.kontext = kontext

    def modelle(self) -> list[dict]:
        antwort = self.http.anfrage("/models?pageSize=1000", timeout=15)
        return [
            {"name": str(m["name"]).removeprefix("models/"), "groesse": None, "parameter": m.get("displayName"),
             "quantisierung": None}
            for m in antwort.get("models", [])
            if m.get("name") and "generateContent" in (m.get("supportedGenerationMethods") or [])
            and not OpenAIExtern._KEIN_CHAT.search(str(m["name"]))
        ]

    def _mit_schema(self, system: str, nutzer: str, schema: dict) -> dict:
        return self.http.anfrage(f"/models/{self.modell}:generateContent", {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": nutzer}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": EXTERN_ANTWORT_TOKEN,
                                 "responseMimeType": "application/json", "responseJsonSchema": _streng(schema)},
        })

    # Wartezeit vor dem einen Wiederholungsversuch nach einem Serverfehler von Google (Sekunden).
    PAUSE = 3.0

    def _schlicht(self, system: str, nutzer: str, schema: dict) -> dict:
        """Ohne Systemanweisung und JSON-Modus: Beides kennen die Gemma-Modelle bei Google nicht.

        Meldet Google einen Serverfehler, folgt nach kurzer Pause ein zweiter Versuch; scheitert auch der, nennt die
        Meldung den Ausweg (ein Gemini-Modell wählen).
        """
        anweisung = (f"{system}\nAntworte ausschließlich mit einem JSON-Objekt nach diesem JSON-Schema, ohne Text "
                     f"davor oder danach:\n{json.dumps(schema, ensure_ascii=False)}\n\n")
        daten = {
            "contents": [{"role": "user", "parts": [{"text": anweisung + nutzer}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": EXTERN_ANTWORT_TOKEN},
        }
        for versuch in (1, 2):
            try:
                return self.http.anfrage(f"/models/{self.modell}:generateContent", daten)
            except KiFehler as fehler:
                if not re.search(r"Fehler 5\d\d", str(fehler)):
                    raise
                if versuch == 2:
                    raise KiFehler(f"{fehler} Google hat die Anfrage zweimal mit einem Serverfehler beantwortet. "
                                   f"Bitte unter „Einstellungen“ ein anderes Modell wählen (etwa gemini-2.5-flash) "
                                   f"oder später erneut fragen.") from fehler
                log.warning("Serverfehler von Google (%s), neuer Versuch", fehler)
                time.sleep(self.PAUSE)
        raise AssertionError("unerreichbar")

    def chat(self, system: str, nutzer: str, schema: dict) -> dict:
        if not self.modell:
            raise KiFehler("Kein Modell gewählt. Bitte unter „Einstellungen“ ein Modell des Anbieters auswählen.")
        if self.modell.startswith("gemma"):
            antwort = self._schlicht(system, nutzer, schema)
        else:
            try:
                antwort = self._mit_schema(system, nutzer, schema)
            except KiFehler as fehler:
                if not re.search(r"Fehler (5\d\d|400)", str(fehler)):
                    raise
                log.warning("Gemini lehnt die Anfrage mit Schema ab (%s), versuche es ohne Schema-Zwang", fehler)
                antwort = self._schlicht(system, nutzer, schema)
        if (antwort.get("promptFeedback") or {}).get("blockReason"):
            raise KiFehler(f"Google Gemini hat die Anfrage abgelehnt ({antwort['promptFeedback']['blockReason']}).")
        kandidat = (antwort.get("candidates") or [{}])[0]
        grund = kandidat.get("finishReason")
        if grund in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
            raise KiFehler(f"Google Gemini hat die Antwort zurückgehalten ({grund}).")
        teile = (kandidat.get("content") or {}).get("parts") or []
        text = "".join(t.get("text", "") for t in teile if not t.get("thought"))
        return lies_json(text, grund == "MAX_TOKENS")


def erzeuge_extern(e: KiEinstellungen, schluessel: str | None) -> Anbieter:
    if not e.extern_freigegeben:
        raise KiFehler("Externe KI ist nicht eingebunden. Der Schalter steht unter „Einstellungen“.")
    if not schluessel:
        raise KiFehler(f"Für {EXTERNE[e.extern_anbieter]['titel']} ist kein API-Schlüssel hinterlegt "
                       "(„Einstellungen“ → „Externe KI“).")
    titel = EXTERNE[e.extern_anbieter]["titel"]
    if e.extern_anbieter == ANTHROPIC:
        return AnthropicClaude(e.extern_modell, schluessel, e.extern_kontext)
    if e.extern_anbieter == "gemini":
        return GoogleGemini(e.extern_modell, schluessel, e.extern_kontext)
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


AUSGESCHALTET = "Die KI ist ausgeschaltet (Einstellungen → Lokales Sprachmodell)."


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
    if e.abgeschaltet:
        ergebnis["hinweis"] = AUSGESCHALTET
        return ergebnis
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
    if e.abgeschaltet:
        ergebnis["hinweis"] = AUSGESCHALTET
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
        "abgeschaltet": e.abgeschaltet,
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
