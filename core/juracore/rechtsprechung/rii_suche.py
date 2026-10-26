"""Suche bei rechtsprechung-im-internet.de: im geladenen Verzeichnis und über die Suche der Seite.

Gericht, Aktenzeichen und Zeitraum sucht die App im Verzeichnis (``rii-toc.xml``), das in der
Wissensbasis liegt; dabei verlässt nichts das Gerät. Für Volltext, Norm oder ECLI gibt es kein
Verzeichnis. Dafür bedient die App die „Erweiterte Suche“ der Seite wie ein Browser, denn eine
dokumentierte Schnittstelle gibt es nicht. Das Vorgehen folgt der Beschreibung von JuraBox Lite
(Abschnitt 5.2c), wo es an der echten Seite ermittelt wurde:

1. Suchmaske laden: Sitzungscookies und im ``<base href>`` eine Zustandskennung.
2. Das GET-Formular ``searchForm`` mit allen Feldern in ihrer Reihenfolge absenden; die Suchwerte
   stehen als Paare ``desc=<Feld>&query=<Wert>``.
3. Trefferliste lesen (25 je Seite, nach Datum absteigend, mit Ausschnitt oder Leitsatz).
4. Weiterblättern über das Formular ``resultListForm`` gegen den ``<base href>`` der letzten Seite.

Jede Suche hat ihre eigene Sitzung; weitergeblättert wird nur auf Knopfdruck und höchstens bis
200 Treffer. Gesendet werden nur die eingegebenen Suchbegriffe.
"""

from __future__ import annotations

import html
import http.cookiejar
import re
import sqlite3
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .verzeichnis import USER_AGENT, dokument_link
from .zitate import normalisiere_az

MASKE = "https://www.rechtsprechung-im-internet.de/jportal/portal/page/bsjrsprod.psml/js_pane/Suchportlet2"
GERICHTE = ("BVerfG", "BGH", "BVerwG", "BFH", "BAG", "BSG", "BPatG")
MAX_TREFFER = 200
JE_SEITE = 25


def _iso_zu_tag(iso: str | None) -> str:
    if not iso:
        return ""
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def _klartext(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


# --- Verzeichnis (lokal) ---------------------------------------------------------------------------


def lokal(con: sqlite3.Connection, gericht: str | None = None, aktenzeichen: str | None = None,
          von: str | None = None, bis: str | None = None, grenze: int = MAX_TREFFER) -> dict:
    """Sucht im geladenen Verzeichnis nach Gericht, Aktenzeichen (Teil davon) und Zeitraum (ISO)."""
    bedingungen, werte = [], []
    if gericht:
        bedingungen.append("gericht = ?")
        werte.append(gericht)
    if aktenzeichen and (az := normalisiere_az(aktenzeichen)):
        bedingungen.append("az_norm LIKE ? ESCAPE '\\'")
        werte.append("%" + az.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if von:
        bedingungen.append("datum >= ?")
        werte.append(von)
    if bis:
        bedingungen.append("datum <= ?")
        werte.append(bis)
    wo = " WHERE " + " AND ".join(bedingungen) if bedingungen else ""
    try:
        gesamt = con.execute(f"SELECT COUNT(*) FROM entscheidung{wo}", werte).fetchone()[0]
        zeilen = con.execute(f"SELECT * FROM entscheidung{wo} ORDER BY datum DESC, id DESC LIMIT ?",
                             [*werte, grenze]).fetchall()
    except sqlite3.OperationalError:  # Verzeichnis nie geladen
        return {"treffer": [], "gesamt": 0, "weitere": False}
    treffer = [{"quelle": "rii", "doknr": z["doknr"], "gericht": z["gericht"], "spruchkoerper": z["spruchkoerper"],
                "datum": z["datum"], "aktenzeichen": z["aktenzeichen"], "doktyp": None, "titel": None,
                "ausschnitt": None, "link": dokument_link(z["doknr"], z["link"])}
               for z in zeilen if z["doknr"]]
    return {"treffer": treffer, "gesamt": gesamt, "weitere": False}


# --- Formulare -------------------------------------------------------------------------------------


class _Formulare(HTMLParser):
    """Liest ``<base href>`` und die Felder aller Formulare in ihrer Reihenfolge."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.base: str | None = None
        self.formulare: dict[str, dict] = {}
        self._form: dict | None = None
        self._select: dict | None = None
        self._option: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "base" and self.base is None and a.get("href"):
            self.base = a["href"]
        elif tag == "form":
            self._form = {"action": a.get("action", ""), "felder": []}
            if name := a.get("name") or a.get("id"):
                self.formulare.setdefault(name, self._form)
        elif self._form is None:
            return
        elif tag == "input" and a.get("name"):
            self._form["felder"].append({"name": a["name"], "typ": a.get("type", "text").lower(),
                                         "wert": a.get("value", ""), "an": "checked" in a})
        elif tag == "select" and a.get("name"):
            self._select = {"name": a["name"], "typ": "select", "wert": None, "optionen": []}
            self._form["felder"].append(self._select)
        elif tag == "option" and self._select is not None:
            self._option = {"wert": a.get("value"), "text": "", "an": "selected" in a}
            self._select["optionen"].append(self._option)
        elif tag == "textarea" and a.get("name"):
            self._form["felder"].append({"name": a["name"], "typ": "text", "wert": ""})

    def handle_data(self, data: str) -> None:
        if self._option is not None:
            self._option["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "option":
            self._option = None
        elif tag == "select" and self._select is not None:
            optionen = self._select["optionen"]
            for o in optionen:
                o["text"] = " ".join(o["text"].split())
                if o["wert"] is None:
                    o["wert"] = o["text"]
            gewaehlt = next((o for o in optionen if o["an"]), optionen[0] if optionen else None)
            self._select["wert"] = gewaehlt["wert"] if gewaehlt else ""
            self._select = None
        elif tag == "form":
            self._form = None


def lies_formulare(seite: str) -> _Formulare:
    p = _Formulare()
    p.feed(seite)
    return p


def _adresse(base: str, action: str, felder: list[tuple[str, str]]) -> str:
    action = re.sub(r";jsessionid=[^?#]*", "", html.unescape(action))
    ziel = urllib.parse.urljoin(base, action).split("?")[0]
    return ziel + "?" + urllib.parse.urlencode(felder, quote_via=urllib.parse.quote)


def _gericht_option(feld: dict, gericht: str) -> str:
    """Wert der Auswahl „Gericht“ zum Kürzel; die Optionen nennen das Gericht im Text oder im Wert."""
    for o in feld.get("optionen", []):
        if o["wert"] == gericht or o["text"].split(" ")[:1] == [gericht] or o["text"] == gericht:
            return o["wert"]
    raise ValueError(f"Die Seite bietet das Gericht {gericht} in der Suche nicht an.")


def suchadresse(maske: str, text: str = "", norm: str = "", gericht: str | None = None,
                aktenzeichen: str = "", von: str | None = None, bis: str | None = None) -> str:
    """Baut aus der Suchmaske die Adresse der Suche (alle Felder von ``searchForm`` in ihrer Reihenfolge)."""
    f = lies_formulare(maske)
    form = f.formulare.get("searchForm")
    if form is None or not f.base:
        raise ValueError("Die Suchmaske von rechtsprechung-im-internet.de hat sich geändert (kein Suchformular).")
    # Die Seite erwartet die Norm ohne Paragrafenzeichen („823 BGB“, „812 ff. BGB“).
    norm = re.sub(r"^\s*(?:§+|Art\.?)\s*", "", norm)
    werte = {"text": text.strip(), "norm": norm.strip(), "filenumber": aktenzeichen.strip()}
    felder: list[tuple[str, str]] = []
    desc = None
    for feld in form["felder"]:
        name, typ = feld["name"], feld["typ"]
        if typ in ("submit", "image", "button", "reset"):
            continue
        if typ in ("checkbox", "radio") and not feld.get("an"):
            continue
        wert = feld["wert"] or ""
        if name == "desc":
            desc = wert
        elif name == "query" and desc == "court_author":
            wert = _gericht_option(feld, gericht) if gericht else wert
        elif name == "query" and desc in werte:
            wert = werte[desc]
        elif name == "dateFrom":
            wert = _iso_zu_tag(von)
        elif name == "dateTo":
            wert = _iso_zu_tag(bis)
        felder.append((name, wert))
    felder.append(("standardsuche", "suchen"))
    return _adresse(f.base, form["action"], felder)


def weiteradresse(seite: str) -> str | None:
    """Adresse der nächsten Trefferseite (Formular ``resultListForm`` gegen den ``<base href>`` dieser Seite)."""
    f = lies_formulare(seite)
    form = f.formulare.get("resultListForm")
    if form is None or not f.base:
        return None
    behalten = ("action", "tl", "IGNORE", "currentNavigationPosition", "numberofresults")
    felder = [(x["name"], x["wert"] or "") for x in form["felder"] if x["name"] in behalten and x["typ"] == "hidden"]
    felder += [("eventSubmit_doSkipforward.x", "5"), ("eventSubmit_doSkipforward.y", "5")]
    return _adresse(f.base, form["action"], felder)


# --- Trefferliste ----------------------------------------------------------------------------------

_ZEILE = re.compile(r'<tr[^>]*valign="top"[^>]*>', re.I)
_DATUM = re.compile(r"<span[^>]*>\s*(\d{2})\.(\d{2})\.(\d{4})\s*</span>")
_DOKNR = re.compile(r"doc\.id=jb-([A-Z0-9]+)")
_GERICHT_AZ = re.compile(r"<strong>(.*?)</strong>\s*\|\s*([^<|]+)", re.S)
_DOKTYP = re.compile(r"<em>(.*?)</em>", re.S)
_TITEL = re.compile(r"</em>\s*\|\s*<strong>(.*?)</strong>(?:\s*\|\s*([^<]+))?", re.S)
_VORSCHAU = re.compile(r'<span[^>]*class="docPreview"[^>]*>(.*?)(?:</td>|$)', re.S)
_GESAMT = re.compile(r"Treffer\s*(\d[\d.]*)\s*bis\s*(\d[\d.]*)\s*von\s*(\d[\d.]*)")
_KEINE = re.compile(r"Es wurden keine mit Ihrer Suchanfrage")


def lies_trefferliste(seite: str) -> tuple[list[dict], int]:
    """Liest eine Trefferseite: Treffer mit Datum, Dokumentnummer, Gericht, Aktenzeichen, Art und Leitsatz oder
    Ausschnitt, dazu die Gesamtzahl."""
    if _KEINE.search(_klartext(seite)):
        return [], 0
    anfaenge = [m.start() for m in _ZEILE.finditer(seite)]
    treffer = []
    for i, start in enumerate(anfaenge):
        zeile = seite[start:anfaenge[i + 1] if i + 1 < len(anfaenge) else len(seite)]
        doknr = _DOKNR.search(zeile)
        if doknr is None:
            continue
        datum = _DATUM.search(zeile)
        ga = _GERICHT_AZ.search(zeile)
        gericht_voll = _klartext(ga.group(1)) if ga else ""
        kuerzel, _, spruchkoerper = gericht_voll.partition(" ")
        doktyp = _DOKTYP.search(zeile)
        titel = _TITEL.search(zeile)
        vorschau = _VORSCHAU.search(zeile)
        treffer.append({
            "quelle": "rii", "doknr": doknr.group(1), "gericht": kuerzel, "spruchkoerper": spruchkoerper or None,
            "datum": f"{datum.group(3)}-{datum.group(2)}-{datum.group(1)}" if datum else None,
            "aktenzeichen": _klartext(ga.group(2)) if ga else "",
            "doktyp": _klartext(doktyp.group(1)) or None if doktyp else None,
            "titel": _klartext(titel.group(1)) or None if titel else None,
            "normen": _klartext(titel.group(2)) or None if titel and titel.group(2) else None,
            "ausschnitt": _klartext(vorschau.group(1)) or None if vorschau else None,
            "link": dokument_link(doknr.group(1), None),
        })
    gesamt = _GESAMT.search(_klartext(seite))
    return treffer, int(gesamt.group(3).replace(".", "")) if gesamt else len(treffer)


# --- Abruf -----------------------------------------------------------------------------------------


class Sitzung:
    """Eine Suche mit eigener, flüchtiger Sitzung; ``weiter`` lädt die nächste Seite derselben Suche."""

    def __init__(self, timeout: float = 30) -> None:
        self.timeout = timeout
        self._oeffner = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        # Eigene Kennung: Mit manchen Standardkennungen liefert die Seite eine Variante ohne Zustandskennung,
        # dann geht das Weiterblättern nicht (JuraBox Lite, Stolperfalle 1).
        self._oeffner.addheaders = [("User-Agent", USER_AGENT)]
        self._seite: str | None = None
        self.geladen = 0
        self.gesamt = 0

    def _hole(self, url: str) -> str:
        with self._oeffner.open(url, timeout=self.timeout) as antwort:
            return antwort.read().decode(antwort.headers.get_content_charset() or "utf-8", errors="replace")

    def _ergebnis(self, seite: str) -> dict:
        self._seite = seite
        treffer, self.gesamt = lies_trefferliste(seite)
        self.geladen += len(treffer)
        return {"treffer": treffer, "gesamt": self.gesamt, "weitere": self.weitere}

    @property
    def weitere(self) -> bool:
        return self._seite is not None and self.geladen < min(self.gesamt, MAX_TREFFER)

    def suche(self, **felder) -> dict:
        return self._ergebnis(self._hole(suchadresse(self._hole(MASKE), **felder)))

    def weiter(self) -> dict:
        if not self.weitere or self._seite is None or (adresse := weiteradresse(self._seite)) is None:
            return {"treffer": [], "gesamt": self.gesamt, "weitere": False}
        return self._ergebnis(self._hole(adresse))
