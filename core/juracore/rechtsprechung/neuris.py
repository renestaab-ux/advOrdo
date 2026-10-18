"""Rechtsprechung aus dem Rechtsinformationsportal des Bundes (NeuRIS), Testphase.

Offene Schnittstelle ohne Schlüssel unter ``testphase.rechtsinformationen.bund.de/v1`` (laut
Beschreibung von JuraBox Lite: Rate Limit 600 Anfragen je Minute und IP). Enthalten sind die
Entscheidungen der obersten Bundesgerichte, also im Wesentlichen dieselben wie bei
rechtsprechung-im-internet.de; NeuRIS dient hier als zweite Quelle für Zitate, die dort nicht
gefunden wurden, z. B. ganz neue Entscheidungen. Gerichtsentscheidungen sind amtliche Werke
(§ 5 Abs. 1 UrhG). Weil die Schnittstelle noch erprobt wird und sich ändern kann, ist sie in der
App standardmäßig aus und jede Entscheidung trägt den Hinweis „Testphase – ohne Gewähr“.

Gesucht wird nur auf Nutzeraktion und nur mit dem Aktenzeichen der zitierten Entscheidung.
Der Volltext ist semantisches HTML (``section#tenor``, ``section#gruende``, Randnummern in
``dl.border-number``); er wird unverändert unter seiner SHA-256-Prüfsumme archiviert.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .verzeichnis import USER_AGENT
from .volltext import Absatz, Volltext

BASIS = "https://testphase.rechtsinformationen.bund.de/v1"
PORTAL = "https://testphase.rechtsinformationen.bund.de"
HERKUNFT = "rechtsinformationen.bund.de (Testphase)"
HINWEIS = "Quelle: Rechtsinformationsportal des Bundes, Testphase – ohne Gewähr. Kein amtlicher Text."
SEITENGROESSE = 50

# Abschnitte des HTML (id der section) mit den Teilnamen, die auch rechtsprechung-im-internet.de nutzt.
TEILE = {"leitsatz": "leitsatz", "leitsaetze": "leitsatz", "orientierungssatz": "sonstosatz",
         "sonstiger-orientierungssatz": "sonstosatz", "tenor": "tenor", "tatbestand": "tatbestand",
         "entscheidungsgruende": "entscheidungsgruende", "gruende": "gruende",
         "abweichende-meinung": "abwmeinung", "sonstiger-langtext": "sonstlt"}


def _pruefe_doknr(doknr: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", doknr or ""):
        raise ValueError(f"Ungültige Dokumentnummer: {doknr!r}")
    return doknr


def adresse(doknr: str) -> str:
    """Leseadresse der Entscheidung im Portal."""
    return f"{PORTAL}/case-law/{_pruefe_doknr(doknr)}"


def _hole(url: str, timeout: float) -> bytes:
    anfrage = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
        return antwort.read()


# --- Suche -----------------------------------------------------------------------------------------


def lies_treffer(daten: bytes | str | dict) -> tuple[list[dict], int | None]:
    """Liest eine Trefferliste (JSON-LD: ``member[].item``) in die Form der übrigen Quellen."""
    antwort = daten if isinstance(daten, dict) else json.loads(daten)
    treffer = []
    for m in antwort.get("member") or []:
        item = m.get("item") or m
        doknr = item.get("documentNumber")
        if not doknr:
            continue
        aktenzeichen = [a for a in item.get("fileNumbers") or [] if a]
        datum = (item.get("decisionDate") or "")[:10] or None
        treffer.append({
            "quelle": "neuris", "doknr": doknr, "gericht": item.get("courtType") or item.get("courtName") or "",
            "gericht_name": item.get("courtName"), "spruchkoerper": item.get("judicialBody"),
            "datum": datum if datum and re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum) else None,
            "aktenzeichen": ", ".join(aktenzeichen), "aktenzeichen_liste": aktenzeichen,
            "doktyp": item.get("documentType"), "ecli": item.get("ecli"), "titel": item.get("headline"),
            "link": adresse(doknr),
        })
    gesamt = antwort.get("totalItems")
    return treffer, int(gesamt) if isinstance(gesamt, int | str) and str(gesamt).isdigit() else None


def suche(aktenzeichen: str, timeout: float = 30) -> tuple[list[dict], int | None]:
    """Sucht Entscheidungen mit diesem Aktenzeichen."""
    abfrage = urllib.parse.urlencode({"fileNumber": aktenzeichen, "size": SEITENGROESSE, "pageIndex": 0})
    return lies_treffer(_hole(f"{BASIS}/case-law?{abfrage}", timeout))


def lade(doknr: str, timeout: float = 60) -> bytes:
    """Lädt den Volltext (HTML) einer Entscheidung."""
    return _hole(f"{BASIS}/case-law/{_pruefe_doknr(doknr)}.html", timeout)


# --- Volltext --------------------------------------------------------------------------------------


class _Leser(HTMLParser):
    """Sammelt Absätze je Abschnitt: Randnummer aus ``dt``, Text aus ``dd``; sonst je ``p`` ein Absatz."""

    BLOCK = {"p", "dd", "dt", "li", "h1", "h2", "h3", "h4", "td", "div", "blockquote"}
    UEBERGEHEN = {"script", "style", "head", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.absaetze: list[Absatz] = []
        self._teil: str | None = None
        self._section_tiefe: list[str | None] = []
        self._puffer: list[str] = []
        self._rn: int | None = None
        self._in_dd = 0
        self._ueberschrift = 0
        self._uebergehen = 0

    def _abschliessen(self) -> None:
        text = "\n".join(" ".join(z.split()) for z in "".join(self._puffer).split("\n")).strip()
        self._puffer = []
        if text and self._teil:
            self.absaetze.append(Absatz(self._teil, self._rn, text))
        if not self._in_dd:
            self._rn = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag in self.UEBERGEHEN:
            self._uebergehen += 1
        elif tag == "section":
            kennung = (a.get("id") or "").lower()
            teil = TEILE.get(kennung)
            if teil is None and kennung and self._teil is None:
                teil = kennung.replace("-", "")
            self._section_tiefe.append(self._teil)
            if teil:
                self._abschliessen()
                self._teil = teil
        elif tag in ("h1", "h2", "h3", "h4"):
            self._ueberschrift += 1
        elif tag == "dt":
            self._abschliessen()
        elif tag == "dd":
            self._in_dd += 1  # vorher erhöhen, damit die Randnummer aus dem dt erhalten bleibt
            self._abschliessen()
        elif tag == "br":
            self._puffer.append("\n")
        elif tag in self.BLOCK and not self._in_dd:
            self._abschliessen()
        elif tag in self.BLOCK and tag == "p" and self._puffer:
            self._puffer.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.UEBERGEHEN:
            self._uebergehen = max(0, self._uebergehen - 1)
        elif tag == "section":
            self._abschliessen()
            if self._section_tiefe:
                self._teil = self._section_tiefe.pop()
        elif tag in ("h1", "h2", "h3", "h4"):
            self._ueberschrift = max(0, self._ueberschrift - 1)
            self._puffer = []
        elif tag == "dt":
            nr = "".join(self._puffer).strip()
            self._rn = int(nr) if nr.isdigit() else None
            self._puffer = []
        elif tag == "dd":
            self._in_dd = max(0, self._in_dd - 1)
            if not self._in_dd:
                self._abschliessen()
                self._rn = None
        elif tag in self.BLOCK and not self._in_dd:
            self._abschliessen()

    def handle_data(self, data: str) -> None:
        if not self._uebergehen and not self._ueberschrift:
            self._puffer.append(data)


def lies(daten: bytes, entscheidung: dict | None = None) -> Volltext:
    """Liest den HTML-Volltext; Kopfdaten kommen aus dem Treffer der Suche (``entscheidung``)."""
    e = entscheidung or {}
    leser = _Leser()
    try:
        leser.feed(daten.decode("utf-8", errors="replace"))
        leser.close()
    except AssertionError as fehler:  # HTMLParser meldet manche Fehler so
        raise ValueError(f"Die Entscheidung ist kein lesbares HTML ({fehler}).") from fehler
    leser._abschliessen()
    if not leser.absaetze:
        raise ValueError("In der Entscheidung von NeuRIS wurde kein Text gefunden (Format geändert?).")
    return Volltext(
        doknr=e.get("doknr") or "",
        gericht=e.get("gericht") or "",
        spruchkoerper=e.get("spruchkoerper"),
        datum=e.get("datum"),
        aktenzeichen=e.get("aktenzeichen") or "",
        doktyp=e.get("doktyp"),
        normen=None,
        vorinstanz=[],
        titel=e.get("titel"),
        absaetze=leser.absaetze,
    )
