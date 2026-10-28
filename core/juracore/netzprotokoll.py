"""Protokoll der Online-Anfragen: jede Verbindung, die der Kern aufbaut, mit Ziel, Zweck und dem, was gesendet wurde.

Die Oberfläche hat keinen Netzzugang (Tauri: ``connect-src ipc:``); alles läuft über den Kern und dort über
``urllib``. ``einrichten`` stellt ``urllib.request.urlopen`` auf einen Öffner mit eigenem HTTP- und HTTPS-Handler um,
und wer einen eigenen Öffner braucht (Cookies, ohne Proxy), baut ihn mit ``oeffner``. So schreibt jede Anfrage
einen Eintrag, auch eine, die scheitert, und eine Weiterleitung als zweiten Eintrag.

Ins Protokoll kommen Adresse und Formularfelder im Wortlaut, weil genau sie das Gerät verlassen. Nie hinein:
API-Schlüssel (sie stehen im Kopf der Anfrage, der nicht protokolliert wird, und werden aus Adressen entfernt),
Prüfzeichen von Formularen und der Text von Anfragen an ein Sprachmodell; dafür nur Anbieter, Modell, Aufgabe und
Umfang. Das Protokoll liegt auf dem Gerät (neben ``ki.json``) und behält die neuesten ``HOECHSTENS`` Einträge.
"""

from __future__ import annotations

import contextlib
import contextvars
import csv
import io
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

DATEINAME = "netzprotokoll.jsonl"
HOECHSTENS = 5000
_KUERZEN_AB = 3 * 1024 * 1024  # Dateigröße, ab der auf die neuesten Einträge gekürzt wird

INTERNET, GERAET, NETZWERK = "internet", "geraet", "netzwerk"
ORTE = {INTERNET: "Internet", GERAET: "Eigener Rechner", NETZWERK: "Lokales Netzwerk"}

# Anlass aus der Bedienung („Zitate der Akte online prüfen“), gilt für alle Anfragen in diesem Ablauf.
_anlass: contextvars.ContextVar[str | None] = contextvars.ContextVar("netz_anlass", default=None)

_datei: Path | None = None
_sperre = threading.Lock()

# Namen von Adress- und Formularfeldern, deren Wert geheim ist oder nur der Sitzung dient.
_GEHEIM = re.compile(r"(?i)^(?:key|api[_-]?key|access[_-]?token|token|auth|password|passwort|secret|"
                     r"__RequestVerificationToken|.*csrf.*)$")


def einrichten(datei: Path | None) -> None:
    """Schreibt ab jetzt in ``datei`` (``None``: nicht mehr) und leitet ``urlopen`` über die Protokoll-Handler."""
    global _datei
    _datei = Path(datei) if datei is not None else None
    urllib.request.install_opener(oeffner())


def oeffner(*handler: urllib.request.BaseHandler) -> urllib.request.OpenerDirector:
    """Wie ``urllib.request.build_opener``, mit Protokoll; eigene HTTP(S)-Handler ersetzen die Standardhandler."""
    return urllib.request.build_opener(*handler, _ProtokollHTTP(), _ProtokollHTTPS())


@contextlib.contextmanager
def anlass(text: str) -> Iterator[None]:
    """Nennt für alle Anfragen in diesem Block (im selben Thread) den Anlass, z. B. „Gesetze laden“."""
    marke = _anlass.set(text)
    try:
        yield
    finally:
        _anlass.reset(marke)


def kennzeichnen(anfrage: urllib.request.Request, zweck: str, gesendet: str | None = None) -> urllib.request.Request:
    """Hängt Zweck und (statt des Inhalts) eine Beschreibung des Gesendeten an die Anfrage; beides wird nicht
    übertragen, nur protokolliert."""
    anfrage.jurabox_zweck = zweck  # type: ignore[attr-defined]
    if gesendet is not None:
        anfrage.jurabox_gesendet = gesendet  # type: ignore[attr-defined]
    return anfrage


# --- Handler ---------------------------------------------------------------------------------------


def _mitschreiben(anfrage: urllib.request.Request, oeffnen: Callable[[], Any]) -> Any:
    beginn = time.monotonic()
    try:
        antwort = oeffnen()
    except Exception as fehler:
        status = getattr(fehler, "code", None)
        _schreibe(anfrage, status, None if status else _fehlertext(fehler), time.monotonic() - beginn)
        raise
    _schreibe(anfrage, getattr(antwort, "status", None), None, time.monotonic() - beginn)
    return antwort


class _ProtokollHTTP(urllib.request.HTTPHandler):
    def http_open(self, req):  # noqa: ANN001, ANN201 - Signatur von urllib
        return _mitschreiben(req, lambda: super(_ProtokollHTTP, self).http_open(req))


class _ProtokollHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req):  # noqa: ANN001, ANN201 - Signatur von urllib
        return _mitschreiben(req, lambda: super(_ProtokollHTTPS, self).https_open(req))


def _fehlertext(fehler: BaseException) -> str:
    grund = getattr(fehler, "reason", None) or fehler
    return f"{type(grund).__name__}: {grund}"[:300]


# --- Eintrag ---------------------------------------------------------------------------------------


def ohne_geheimnis(adresse: str) -> str:
    """Die Adresse ohne Werte geheimer Parameter (``key=…``) und ohne Zugangsdaten vor dem Rechnernamen."""
    teile = urllib.parse.urlsplit(adresse)
    netz = teile.netloc.rsplit("@", 1)[-1]
    if not teile.query:
        return urllib.parse.urlunsplit(teile._replace(netloc=netz))
    felder = [(k, "***" if _GEHEIM.match(k) else v)
              for k, v in urllib.parse.parse_qsl(teile.query, keep_blank_values=True)]
    abfrage = urllib.parse.urlencode(felder, safe="*/:,", quote_via=urllib.parse.quote)
    return urllib.parse.urlunsplit(teile._replace(netloc=netz, query=abfrage))


def _lesbar(adresse: str) -> str:
    """Adresse mit entschlüsselten Umlauten und Leerzeichen, wie man sie liest."""
    return urllib.parse.unquote(ohne_geheimnis(adresse))


def gesendet(anfrage: urllib.request.Request) -> str:
    """Was außer der Adresse übertragen wird: Formularfelder im Wortlaut, sonst nur der Umfang."""
    beschreibung = getattr(anfrage, "jurabox_gesendet", None)
    if beschreibung is not None:
        return beschreibung
    daten = anfrage.data
    if daten is None:
        return ""
    if not isinstance(daten, bytes | bytearray):
        return "Daten (Umfang unbekannt, Inhalt nicht protokolliert)"
    art = (anfrage.get_header("Content-type") or "application/x-www-form-urlencoded").lower()
    if "x-www-form-urlencoded" in art:
        felder = urllib.parse.parse_qsl(bytes(daten).decode("utf-8", "replace"), keep_blank_values=True)
        sichtbar = [f"{k}={v}" for k, v in felder if v.strip() and not _GEHEIM.match(k)]
        return "Formular: " + ("; ".join(sichtbar) if sichtbar else "keine ausgefüllten Felder")
    return f"{len(daten):,} Bytes (Inhalt nicht protokolliert)".replace(",", ".")


def ort(host: str) -> str:
    from .ki.anbieter import ort as ki_ort  # dort steht, welche Adressen zum eigenen Netz gehören

    return ki_ort(host) or INTERNET


def zweck(anfrage: urllib.request.Request) -> str:
    """Wozu die Anfrage dient: aus der Kennzeichnung, sonst aus Ziel und Pfad."""
    eigen = getattr(anfrage, "jurabox_zweck", None)
    if eigen:
        return eigen
    teile = urllib.parse.urlsplit(anfrage.full_url)
    host, pfad = (teile.hostname or "").lower(), teile.path
    kennung = anfrage.get_header("User-agent") or ""
    if "(Diagnose)" in kennung:
        return "Verbindung prüfen (Diagnose)"
    if host.endswith("gesetze-im-internet.de"):
        if m := re.fullmatch(r"/([^/]+)/xml\.zip", pfad):
            return f"Gesetz laden ({m.group(1).upper()})"
        return "Gesetze im Internet"
    if host.endswith("eur-lex.europa.eu") or host.endswith("publications.europa.eu"):
        celex = re.search(r"(?:CELEX:|/celex/)([0-9A-Z()]+)", urllib.parse.unquote(anfrage.full_url))
        return "Unionsrecht laden" + (f" (CELEX {celex.group(1)})" if celex else "")
    if host.endswith("rechtsprechung-im-internet.de"):
        if pfad.endswith("rii-toc.xml"):
            return "Verzeichnis der Bundesrechtsprechung laden"
        if "/docs/" in pfad:
            return "Volltext einer Entscheidung laden"
        return "Entscheidungen suchen (rechtsprechung-im-internet.de)"
    if host.endswith("gesetze-bayern.de"):
        if pfad.startswith("/Content/"):
            return "Volltext einer Entscheidung laden (Bayern)"
        if pfad == "/Search" and anfrage.data is not None:
            return "Entscheidungen suchen (Bayern)"
        return "Suchformular öffnen (Bayern)"
    if host.endswith("rechtsinformationen.bund.de"):
        if pfad.endswith(".html"):
            return "Volltext einer Entscheidung laden (NeuRIS)"
        return "Entscheidungen suchen (NeuRIS)"
    if host.endswith("xrepository.de"):
        return "Gerichtsverzeichnis laden"
    return "Abruf"


def eintrag(anfrage: urllib.request.Request, status: int | None, fehler: str | None, dauer: float) -> dict:
    host = (urllib.parse.urlsplit(anfrage.full_url).hostname or "").lower()
    z = zweck(anfrage)
    if (a := _anlass.get()) and a not in z:
        z = a if z in a else f"{a}: {z}"
    return {
        "zeit": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ziel": host,
        "ort": ort(host),
        "zweck": z,
        "methode": anfrage.get_method(),
        "adresse": _lesbar(anfrage.full_url),
        "gesendet": gesendet(anfrage),
        "status": status,
        "fehler": fehler,
        "dauer_ms": round(dauer * 1000),
    }


def _schreibe(anfrage: urllib.request.Request, status: int | None, fehler: str | None, dauer: float) -> None:
    datei = _datei
    if datei is None:
        return
    zeile = json.dumps(eintrag(anfrage, status, fehler, dauer), ensure_ascii=False) + "\n"
    with _sperre:
        try:
            datei.parent.mkdir(parents=True, exist_ok=True)
            with open(datei, "a", encoding="utf-8") as f:
                f.write(zeile)
            if datei.stat().st_size > _KUERZEN_AB:
                _kuerze(datei)
        except OSError:
            pass  # ein volles oder gesperrtes Laufwerk darf keinen Abruf verhindern


def _kuerze(datei: Path) -> None:
    zeilen = datei.read_text(encoding="utf-8").splitlines(keepends=True)[-HOECHSTENS:]
    tmp = datei.with_suffix(".tmp")
    tmp.write_text("".join(zeilen), encoding="utf-8")
    tmp.replace(datei)


# --- Lesen und Ausgeben ----------------------------------------------------------------------------


def _alle(datei: Path) -> list[dict]:
    try:
        text = Path(datei).read_text(encoding="utf-8")
    except OSError:
        return []
    eintraege = []
    for zeile in text.splitlines():
        try:
            e = json.loads(zeile)
        except ValueError:
            continue  # eine halb geschriebene Zeile nach einem Absturz
        if isinstance(e, dict) and e.get("zeit"):
            eintraege.append(e)
    return eintraege[-HOECHSTENS:]


def liste(datei: Path, nur_internet: bool = False, limit: int | None = 500) -> dict:
    """Neueste Einträge zuerst; ``gesamt`` zählt alle (nach dem Filter)."""
    eintraege = [e for e in _alle(datei) if not nur_internet or e.get("ort") == INTERNET]
    eintraege.reverse()
    seit = eintraege[-1]["zeit"] if eintraege else None
    return {"eintraege": eintraege[:limit] if limit else eintraege, "gesamt": len(eintraege), "seit": seit,
            "hoechstens": HOECHSTENS}


SPALTEN = (("zeit", "Zeit"), ("ort", "Ort"), ("ziel", "Ziel"), ("zweck", "Zweck"), ("methode", "Methode"),
           ("adresse", "Adresse"), ("gesendet", "Gesendet außer der Adresse"), ("ergebnis", "Ergebnis"),
           ("dauer_ms", "Dauer (ms)"))


def ergebnis(e: dict) -> str:
    if e.get("fehler"):
        return f"Fehler: {e['fehler']}"
    return f"HTTP {e['status']}" if e.get("status") else ""


def _zeit(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M:%S")
    except ValueError:
        return iso


def _zeile(e: dict) -> dict[str, str]:
    return {"zeit": _zeit(e["zeit"]), "ort": ORTE.get(e.get("ort") or "", e.get("ort") or ""),
            "ziel": e.get("ziel") or "", "zweck": e.get("zweck") or "", "methode": e.get("methode") or "",
            "adresse": e.get("adresse") or "", "gesendet": e.get("gesendet") or "", "ergebnis": ergebnis(e),
            "dauer_ms": str(e.get("dauer_ms") if e.get("dauer_ms") is not None else "")}


def als_csv(eintraege: list[dict]) -> str:
    """CSV mit Semikolon, wie es Excel in deutscher Einstellung erwartet."""
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    w.writerow([titel for _, titel in SPALTEN])
    for e in eintraege:
        z = _zeile(e)
        w.writerow([z[k] for k, _ in SPALTEN])
    return puffer.getvalue()


def als_text(eintraege: list[dict]) -> str:
    kopf = ["Protokoll der Online-Anfragen von JuraBox",
            f"Erstellt am {datetime.now().strftime('%d.%m.%Y %H:%M')}, {len(eintraege)} Einträge, neueste zuerst.",
            "Kopfzeilen der Anfragen (mit API-Schlüsseln) und Texte an Sprachmodelle werden nicht protokolliert.",
            ""]
    bloecke = []
    for e in eintraege:
        z = _zeile(e)
        zeilen = [f"{z['zeit']}  {z['zweck']}", f"    Ziel:     {z['ziel']} ({z['ort']})",
                  f"    Adresse:  {z['methode']} {z['adresse']}"]
        if z["gesendet"]:
            zeilen.append(f"    Gesendet: {z['gesendet']}")
        zeilen.append(f"    Ergebnis: {z['ergebnis'] or '–'}, {z['dauer_ms']} ms")
        bloecke.append("\n".join(zeilen))
    return "\n".join(kopf) + "\n\n".join(bloecke) + "\n"


def exportieren(datei: Path, pfad: str, nur_internet: bool = False) -> dict:
    """Schreibt das Protokoll als CSV (Endung .csv) oder Text (sonst) an den gewählten Ort."""
    eintraege = liste(datei, nur_internet, limit=None)["eintraege"]
    ziel = Path(pfad)
    text = als_csv(eintraege) if ziel.suffix.lower() == ".csv" else als_text(eintraege)
    # Mit BOM, damit Excel unter Windows die Umlaute richtig liest.
    ziel.write_text(text, encoding="utf-8-sig" if ziel.suffix.lower() == ".csv" else "utf-8")
    return {"pfad": str(ziel), "anzahl": len(eintraege)}
