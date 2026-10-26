"""Nachrichten auf der Startseite: RSS- und Atom-Feeds, die man in den Einstellungen hinzufügt.

Die Feeds gelten für das Gerät (``nachrichten.json`` neben der Wissensbasis), nicht je
Arbeitsumgebung. Abgerufen werden nur die eingetragenen Adressen; gesendet wird dabei nichts
aus Akten oder Dokumenten. Solange kein Feed eingetragen ist, lädt die App nichts.

Der RPC-Kern beantwortet Anfragen der Reihe nach. Damit ein langsamer Feed die App nicht
anhält, lädt ein eigener Thread im Hintergrund; ``liste`` gibt sofort den letzten Stand zurück
(``nachrichten-cache.json``) und stößt das Laden an, wenn der Stand älter als eine halbe Stunde ist.

Gelesen werden RSS 2.0, RSS 1.0 (RDF) und Atom. Gibt man statt des Feeds die Adresse einer
Webseite an (z. B. die Übersicht https://www.lto.de/rss), sucht die App dort nach dem Feed.
"""

from __future__ import annotations

import html
import json
import logging
import re
import threading
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

log = logging.getLogger("juracore.nachrichten")

USER_AGENT = "JuraBox/0.1 (Nachrichten)"
HOECHSTENS_BYTES = 5 * 1024 * 1024
ZEITLIMIT = 15
VERALTET_NACH = timedelta(minutes=30)
JE_FEED = 30  # so viele Einträge je Feed werden behalten
AUSZUG = 280

# Vorschläge: nur Adressen, die beim Einbau (2026-10-26) als Feed abrufbar waren.
VORSCHLAEGE: list[dict[str, str]] = [
    {"titel": "LTO – Alle Beiträge", "url": "https://www.lto.de/rss/feed.xml",
     "hinweis": "Legal Tribune Online, Nachrichten und Hintergründe"},
    {"titel": "LTO – Nachrichten", "url": "https://www.lto.de/nachrichten-rss/rss/feed.xml",
     "hinweis": "Legal Tribune Online, nur Nachrichten"},
    {"titel": "LTO – Zivil- und Zivilverfahrensrecht",
     "url": "https://www.lto.de/rss/feed.xml?tx_ltorss_pi1[rechtsgebiet]=25",
     "hinweis": "Legal Tribune Online, ein Rechtsgebiet; weitere unter lto.de/rss"},
    {"titel": "beck-aktuell", "url": "https://www.beck-aktuell.de/rss.xml",
     "hinweis": "C.H.Beck, „Heute im Recht“"},
    {"titel": "BAG – Pressemitteilungen", "url": "https://www.bundesarbeitsgericht.de/feed/presse/neueste",
     "hinweis": "Bundesarbeitsgericht"},
    {"titel": "BAG – Entscheidungen", "url": "https://www.bundesarbeitsgericht.de/feed/entscheidung/neueste",
     "hinweis": "Bundesarbeitsgericht, neu veröffentlichte Entscheidungen"},
]

Oeffner = Callable[..., Any]


class KeinFeed(ValueError):
    """Unter der Adresse steht weder ein Feed noch eine Seite, die auf einen verweist."""


# --- Feeds lesen -----------------------------------------------------------------------------------


def _name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _kind(el: ET.Element, *namen: str) -> ET.Element | None:
    for k in el:
        if _name(k.tag) in namen:
            return k
    return None


def _text(el: ET.Element | None) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


class _NurText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.teile: list[str] = []

    def handle_data(self, data: str) -> None:
        self.teile.append(data)


def klartext(roh: str) -> str:
    """HTML einer Beschreibung als einfacher Text, Leerraum zusammengefasst."""
    if "<" in roh:
        p = _NurText()
        p.feed(roh)
        p.close()
        roh = " ".join(p.teile)
    return re.sub(r"\s+", " ", html.unescape(roh)).strip()


def _kuerzen(text: str, laenge: int = AUSZUG) -> str:
    if len(text) <= laenge:
        return text
    return text[:laenge].rsplit(" ", 1)[0].rstrip(" ,.;:") + " …"


def datum(roh: str) -> str | None:
    """RFC 822 (RSS) oder ISO 8601 (Atom, dc:date) als ISO-Zeitpunkt in UTC; ``None``, wenn unlesbar."""
    roh = roh.strip()
    if not roh:
        return None
    try:
        d = parsedate_to_datetime(roh)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(roh.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d.astimezone(UTC).isoformat(timespec="seconds")


def _sichere_adresse(adresse: str, basis: str = "") -> str | None:
    adresse = urllib.parse.urljoin(basis, adresse.strip()) if basis else adresse.strip()
    return adresse if urllib.parse.urlsplit(adresse).scheme in ("http", "https") else None


def lies_feed(daten: bytes, adresse: str = "") -> dict:
    """Titel und Einträge eines RSS- oder Atom-Feeds. ``KeinFeed``, wenn es keiner ist."""
    kopf = daten[:4096].lstrip().lower()
    if b"<!entity" in daten.lower():
        # Feeds brauchen keine eigenen Entitäten; so bleibt das Einlesen auch bei böswilligen Dateien klein.
        raise KeinFeed("Der Feed enthält Entitätsdefinitionen und wird deshalb nicht gelesen.")
    if kopf.startswith(b"<!doctype html") or kopf.startswith(b"<html"):
        raise KeinFeed("Unter der Adresse steht eine Webseite, kein Feed.")
    try:
        wurzel = ET.fromstring(daten)
    except ET.ParseError as fehler:
        raise KeinFeed(f"Kein lesbarer Feed ({fehler}).") from fehler

    art = _name(wurzel.tag)
    if art == "feed":  # Atom
        titel = _text(_kind(wurzel, "title"))
        elemente = [k for k in wurzel if _name(k.tag) == "entry"]
    elif art == "rss":
        kanal = _kind(wurzel, "channel")
        if kanal is None:
            raise KeinFeed("RSS ohne channel.")
        titel = _text(_kind(kanal, "title"))
        elemente = [k for k in kanal if _name(k.tag) == "item"]
    elif art == "rdf":  # RSS 1.0: Einträge stehen neben dem channel
        kanal = _kind(wurzel, "channel")
        titel = _text(_kind(wurzel if kanal is None else kanal, "title"))
        elemente = [k for k in wurzel if _name(k.tag) == "item"]
    else:
        raise KeinFeed("Unter der Adresse steht kein RSS- oder Atom-Feed.")

    eintraege = []
    for el in elemente:
        link = None
        for k in el:
            if _name(k.tag) != "link":
                continue
            ziel = k.get("href") if k.get("href") is not None else _text(k)
            if k.get("href") is not None and k.get("rel", "alternate") != "alternate":
                continue
            link = _sichere_adresse(ziel or "", adresse)
            if link:
                break
        if link is None:
            guid = _kind(el, "guid", "id")
            if guid is not None and guid.get("isPermaLink", "true") != "false":
                link = _sichere_adresse(_text(guid), adresse)
        zeit = None
        for name in ("pubdate", "published", "updated", "date", "issued", "modified"):
            zeit = datum(_text(_kind(el, name)))
            if zeit:
                break
        auszug = klartext(_text(_kind(el, "description", "summary", "content", "encoded")))
        eintrag_titel = klartext(_text(_kind(el, "title"))) or _kuerzen(auszug, 100)
        if not eintrag_titel:
            continue
        eintraege.append({"titel": eintrag_titel, "link": link, "datum": zeit, "auszug": _kuerzen(auszug)})
    return {"titel": klartext(titel), "eintraege": eintraege}


class _FeedLinks(HTMLParser):
    """Sammelt in einer Webseite die Verweise auf Feeds: zuerst ``<link rel="alternate">``, dann Links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.alternativ: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "link" and "alternate" in a.get("rel", "").lower() and (
            "rss" in a.get("type", "") or "atom" in a.get("type", "")
        ):
            self.alternativ.append(a.get("href", ""))
        elif tag == "a" and re.search(r"rss|atom|feed|\.xml", a.get("href", ""), re.I):
            self.links.append(a.get("href", ""))


def feed_links(seite: bytes, adresse: str) -> list[str]:
    p = _FeedLinks()
    p.feed(seite.decode("utf-8", "replace"))
    p.close()
    gesehen: list[str] = []
    for ziel in p.alternativ + p.links:
        voll = _sichere_adresse(ziel, adresse)
        if voll and voll != adresse and voll not in gesehen:
            gesehen.append(voll)
    return gesehen


# --- Abruf ---------------------------------------------------------------------------------------


def abrufen(adresse: str, oeffnen: Oeffner = urllib.request.urlopen, timeout: float = ZEITLIMIT) -> bytes:
    if _sichere_adresse(adresse) is None:
        raise ValueError("Bitte eine Adresse angeben, die mit http:// oder https:// beginnt.")
    anfrage = urllib.request.Request(adresse, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9, */*;q=0.5",
    })
    with oeffnen(anfrage, timeout=timeout) as antwort:
        daten = antwort.read(HOECHSTENS_BYTES + 1)
    if len(daten) > HOECHSTENS_BYTES:
        raise ValueError("Der Feed ist größer als 5 MB und wird nicht geladen.")
    return daten


def finde_feed(adresse: str, oeffnen: Oeffner = urllib.request.urlopen) -> tuple[str, dict]:
    """Adresse und Inhalt des Feeds; bei einer Webseite der erste Feed, auf den sie verweist."""
    daten = abrufen(adresse, oeffnen)
    try:
        return adresse, lies_feed(daten, adresse)
    except KeinFeed as fehler:
        kandidaten = feed_links(daten, adresse)
        for ziel in kandidaten[:6]:
            try:
                return ziel, lies_feed(abrufen(ziel, oeffnen), ziel)
            except (KeinFeed, OSError, ValueError):
                continue
        if kandidaten:
            raise KeinFeed("Die Seite verweist auf Feeds, keiner davon war lesbar.") from fehler
        raise


# --- Einstellungen ------------------------------------------------------------------------------


def _lade(datei: Path) -> list[dict]:
    try:
        feeds = json.loads(Path(datei).read_text(encoding="utf-8")).get("feeds", [])
    except (OSError, ValueError, AttributeError):
        return []
    return [f for f in feeds if isinstance(f, dict) and f.get("id") and f.get("url")]


def _speichere(datei: Path, feeds: list[dict]) -> None:
    Path(datei).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(datei).with_suffix(".tmp")
    tmp.write_text(json.dumps({"feeds": feeds}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(datei)


class Nachrichten:
    def __init__(self, datei: Path, cache: Path, oeffnen: Oeffner | None = None, im_hintergrund: bool = True):
        self.datei = Path(datei)
        self.cache = Path(cache)
        self.oeffnen = oeffnen or urllib.request.urlopen
        self.im_hintergrund = im_hintergrund
        self._sperre = threading.Lock()
        self._laeuft: threading.Thread | None = None

    # Einstellungen

    def einstellungen(self) -> dict:
        feeds = _lade(self.datei)
        urls = {f["url"] for f in feeds}
        return {"feeds": feeds, "vorschlaege": [{**v, "eingetragen": v["url"] in urls} for v in VORSCHLAEGE]}

    def hinzufuegen(self, url: str, titel: str = "") -> dict:
        """Prüft die Adresse (lädt den Feed einmal) und trägt ihn ein; der Titel kommt sonst aus dem Feed."""
        url = url.strip()
        if not url:
            raise ValueError("Bitte die Adresse des Feeds angeben.")
        if "://" not in url:
            url = "https://" + url
        feed_url, inhalt = finde_feed(url, self.oeffnen)
        with self._sperre:
            feeds = _lade(self.datei)
            if any(f["url"] in (url, feed_url) for f in feeds):
                raise ValueError("Dieser Feed ist schon eingetragen.")
            neu = {
                "id": uuid.uuid4().hex[:12],
                "titel": titel.strip() or inhalt["titel"] or urllib.parse.urlsplit(feed_url).hostname or feed_url,
                "url": feed_url,
                "hinzugefuegt": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            _speichere(self.datei, [*feeds, neu])
            stand = self._lies_cache()
            stand["feeds"][neu["id"]] = self._feed_stand(neu, inhalt)
            self._schreibe_cache(stand)
        return {**self.einstellungen(), "neu": neu, "eintraege": len(inhalt["eintraege"])}

    def umbenennen(self, feed_id: str, titel: str) -> dict:
        titel = titel.strip()
        if not titel:
            raise ValueError("Der Name darf nicht leer sein.")
        with self._sperre:
            feeds = _lade(self.datei)
            for f in feeds:
                if f["id"] == feed_id:
                    f["titel"] = titel
                    break
            else:
                raise LookupError("Feed nicht gefunden.")
            _speichere(self.datei, feeds)
        return self.einstellungen()

    def entfernen(self, feed_id: str) -> dict:
        with self._sperre:
            feeds = _lade(self.datei)
            rest = [f for f in feeds if f["id"] != feed_id]
            if len(rest) == len(feeds):
                raise LookupError("Feed nicht gefunden.")
            _speichere(self.datei, rest)
            stand = self._lies_cache()
            stand["feeds"].pop(feed_id, None)
            self._schreibe_cache(stand)
        return self.einstellungen()

    # Startseite

    def liste(self, limit: int = 8, aktualisieren: bool = False) -> dict:
        """Neueste Einträge aller Feeds, neueste zuerst. Lädt im Hintergrund nach, wenn der Stand alt ist."""
        feeds = _lade(self.datei)
        with self._sperre:
            stand = self._lies_cache()
        jetzt = datetime.now(UTC)
        veraltet = [f for f in feeds if f["id"] not in stand["feeds"]
                    or _alter(stand["feeds"][f["id"]].get("abgerufen"), jetzt) > VERALTET_NACH]
        if feeds and (aktualisieren or veraltet):
            self._starte(feeds)
            if not self.im_hintergrund:
                with self._sperre:
                    stand = self._lies_cache()

        eintraege: list[dict] = []
        fehler = []
        abgerufen = []
        gesehen: set[str] = set()
        for f in feeds:
            s = stand["feeds"].get(f["id"])
            if not s:
                continue
            if s.get("fehler"):
                fehler.append({"feed_id": f["id"], "titel": f["titel"], "text": s["fehler"]})
            if s.get("abgerufen"):
                abgerufen.append(s["abgerufen"])
            for e in s.get("eintraege", []):
                schluessel = e.get("link") or e["titel"]
                if schluessel in gesehen:
                    continue
                gesehen.add(schluessel)
                eintraege.append({**e, "quelle": f["titel"], "feed_id": f["id"]})
        eintraege.sort(key=lambda e: e.get("datum") or "", reverse=True)
        return {
            "feeds": len(feeds),
            "eintraege": eintraege[: max(1, int(limit))],
            "gesamt": len(eintraege),
            "stand": min(abgerufen) if abgerufen else None,
            "laeuft": self.laeuft(),
            "fehler": fehler,
        }

    def laeuft(self) -> bool:
        return self._laeuft is not None and self._laeuft.is_alive()

    def _starte(self, feeds: list[dict]) -> None:
        if self.laeuft():
            return
        if not self.im_hintergrund:
            self._lade_alle(feeds)
            return
        self._laeuft = threading.Thread(target=self._lade_alle, args=(feeds,), name="nachrichten", daemon=True)
        self._laeuft.start()

    def _lade_alle(self, feeds: list[dict]) -> None:
        def eins(f: dict) -> tuple[str, dict]:
            try:
                return f["id"], self._feed_stand(f, lies_feed(abrufen(f["url"], self.oeffnen), f["url"]))
            except Exception as fehler:  # noqa: BLE001 – ein kaputter Feed darf die anderen nicht aufhalten
                log.info("Feed %s nicht geladen: %s", f["url"], fehler)
                return f["id"], {"abgerufen": datetime.now(UTC).isoformat(timespec="seconds"),
                                 "fehler": _meldung(fehler)}

        with ThreadPoolExecutor(max_workers=4) as pool:
            ergebnisse = list(pool.map(eins, feeds))
        with self._sperre:
            stand = self._lies_cache()
            for feed_id, s in ergebnisse:
                alt = stand["feeds"].get(feed_id, {})
                if s.get("fehler") and alt.get("eintraege"):
                    s["eintraege"] = alt["eintraege"]  # letzten guten Stand behalten
                stand["feeds"][feed_id] = s
            gueltig = {f["id"] for f in _lade(self.datei)}
            stand["feeds"] = {k: v for k, v in stand["feeds"].items() if k in gueltig}
            self._schreibe_cache(stand)

    @staticmethod
    def _feed_stand(feed: dict, inhalt: dict) -> dict:
        return {"abgerufen": datetime.now(UTC).isoformat(timespec="seconds"), "fehler": None,
                "eintraege": inhalt["eintraege"][:JE_FEED]}

    def _lies_cache(self) -> dict:
        try:
            stand = json.loads(self.cache.read_text(encoding="utf-8"))
            if isinstance(stand.get("feeds"), dict):
                return stand
        except (OSError, ValueError, AttributeError):
            pass
        return {"feeds": {}}

    def _schreibe_cache(self, stand: dict) -> None:
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache.with_suffix(".tmp")
        tmp.write_text(json.dumps(stand, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.cache)


def _alter(iso: str | None, jetzt: datetime) -> timedelta:
    try:
        return jetzt - datetime.fromisoformat(iso or "")
    except ValueError:
        return timedelta.max


def _meldung(fehler: Exception) -> str:
    if isinstance(fehler, ValueError):
        return str(fehler)
    grund = getattr(fehler, "reason", None) or getattr(fehler, "code", None) or type(fehler).__name__
    return f"Nicht erreichbar ({grund})."
