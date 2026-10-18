"""Unionsrecht aus EUR-Lex: Verordnungen wie die DSGVO als Gesetz in der Wissensbasis.

EUR-Lex liefert Rechtsakte als HTML-Fassung des Amtsblatts. Die Absätze und Aufzählungen
tragen Klassen wie ``oj-ti-art`` (Artikel), ``oj-sti-art`` (Artikeltitel), ``oj-normal``
(Text) und ``oj-ti-section-1`` (Kapitel, Abschnitt). Ältere Rechtsakte verwenden dieselben
Klassen ohne das Präfix ``oj-``. Aufzählungen ("a)", "1.") stehen als zweispaltige Tabelle.

Der Leser liefert dieselbe Struktur wie der GII-Parser (``GesetzDokument`` mit ``Norm``,
``Absatz``, ``Satz``), damit Zitate wie "Art. 6 Abs. 1 lit. f DSGVO" genauso aufgelöst werden
wie Paragraphen des BGB. Die Erwägungsgründe werden als eigene Einträge gespeichert, damit sie
in der Suche erscheinen.

Gespeichert wird die Fassung des Amtsblatts, also ohne spätere Änderungen und Berichtigungen.
Die Weiterverwendung ist mit Quellenangabe erlaubt (Beschluss 2011/833/EU der Kommission).
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser

from .gii import Absatz, GesetzDokument, Norm
from .saetze import Liste, zerlege_in_saetze

HERKUNFT = "EUR-Lex"
HINWEIS = (
    "Fassung des Amtsblatts der EU (EUR-Lex), ohne spätere Änderungen und Berichtigungen. "
    "© Europäische Union, https://eur-lex.europa.eu"
)
USER_AGENT = "JuraBox/0.1 (Wissensbasis-Import)"
_CELEX = re.compile(r"^[1-9]\d{4}[A-Z]{1,2}\d{4}$")

# Gliederungsebenen in absteigender Ordnung; eine neue Überschrift schließt alle tieferen.
_EBENEN = ("TEIL", "TITEL", "KAPITEL", "ABSCHNITT", "UNTERABSCHNITT")
_ABSATZ_NR = re.compile(r"^\((\d+[a-z]?)\)\s+")
_ERWAEGUNG_NR = re.compile(r"^\((\d+)\)$")
# Gliederungspunkt einer Aufzählung: "a)", "1.", "iv)", "—".
_PUNKT = re.compile(r"^(?:\(?([a-z]{1,2}|[ivx]+|\d+[a-z]?)[).]|([—–-]))$")
_PUNKT_IM_TEXT = re.compile(r"^\(?([a-z]|[ivx]+|\d+)\)\s+")
_SCHLUSS = ("Geschehen zu ", "Diese Verordnung ist in allen ihren Teilen verbindlich")
_LEER = {"br", "col", "img", "hr", "meta", "link", "input", "wbr", "area", "base", "source"}


def adresse(celex: str) -> str:
    return f"https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:{celex}"


def ist_celex(kuerzel: str) -> bool:
    return bool(_CELEX.match(kuerzel))


def ist_eurlex(daten: bytes | str) -> bool:
    """Ob eine Datei die HTML-Fassung eines Rechtsakts aus EUR-Lex ist (und kein GII-XML)."""
    kopf = daten[:2_000_000] if isinstance(daten, str) else daten[:2_000_000].decode("utf-8", "replace")
    return bool(re.search(r"""class=["'][^"']*\b(?:oj-)?ti-art\b""", kopf))


def lade(celex: str, timeout: float = 60) -> tuple[bytes, str]:
    """Lädt die deutsche HTML-Fassung eines Rechtsakts; gesendet wird nur die CELEX-Nummer."""
    if not ist_celex(celex):
        raise ValueError(f"Ungültige CELEX-Nummer: {celex!r}")
    url = adresse(celex)
    anfrage = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Language": "de"}
    )
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            daten = antwort.read()
    except urllib.error.HTTPError as fehler:
        if fehler.code == 404:
            raise ValueError(f"CELEX {celex} wurde bei EUR-Lex nicht gefunden.") from None
        raise
    if not ist_eurlex(daten):
        raise ValueError(
            f"EUR-Lex hat für CELEX {celex} keinen lesbaren Rechtstext geliefert. Die Seite im Browser öffnen "
            f"({url}), als „Webseite, nur HTML“ speichern und unter Gesetze als Datei importieren."
        )
    return daten, url


# --- HTML in einfache Elemente zerlegen -------------------------------------------------------------


@dataclass
class _El:
    tag: str
    klassen: set[str]
    attrs: dict[str, str]
    kinder: list[_El | str] = field(default_factory=list)


class _Baum(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.wurzel = _El("#wurzel", set(), {})
        self._stapel = [self.wurzel]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        # Klassen ohne "oj-", damit alte und neue Rechtsakte gleich gelesen werden.
        el = _El(tag, {k.removeprefix("oj-") for k in a.get("class", "").split()}, a)
        self._stapel[-1].kinder.append(el)
        if tag not in _LEER:
            self._stapel.append(el)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stapel[-1].kinder.append(_El(tag, set(), {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stapel) - 1, 0, -1):
            if self._stapel[i].tag == tag:
                del self._stapel[i:]
                return

    def handle_data(self, data: str) -> None:
        self._stapel[-1].kinder.append(data)


def _text(el: _El | str) -> str:
    if isinstance(el, str):
        return el
    if el.tag == "a" and el.attrs.get("href", "").startswith("#ntc"):
        return ""  # Fußnotenzeichen "(1)" gehört nicht zum Normtext
    if el.tag == "br":
        return " "
    if el.tag in ("script", "style"):
        return ""
    trenner = " " if el.tag in ("p", "td", "div", "tr", "table") else ""
    return trenner + "".join(_text(k) for k in el.kinder) + trenner


def _rein(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace("\xa0", " ")).strip()


def _zellen(tabelle: _El) -> list[list[_El]]:
    zeilen: list[list[_El]] = []

    def lauf(el: _El) -> None:
        for k in el.kinder:
            if isinstance(k, str):
                continue
            if k.tag == "tr":
                zeilen.append([z for z in k.kinder if isinstance(z, _El) and z.tag in ("td", "th")])
            elif k.tag in ("tbody", "thead", "tfoot"):
                lauf(k)

    lauf(tabelle)
    return zeilen


# --- Blöcke in Dokumentreihenfolge ------------------------------------------------------------------


@dataclass
class _Block:
    art: str  # kopf_datum, kopf_abl, titel, gliederung, gliederung_titel, artikel, artikel_titel, text, liste
    text: str = ""
    eintraege: list[tuple[str, str]] = field(default_factory=list)


_P_KLASSEN = {
    "hd-date": "kopf_datum",
    "hd-oj": "kopf_abl",
    "doc-ti": "titel",
    "ti-section-1": "gliederung",
    "ti-section-2": "gliederung_titel",
    "ti-art": "artikel",
    "sti-art": "artikel_titel",
    "normal": "text",
}


def _bloecke(wurzel: _El) -> list[_Block]:
    bloecke: list[_Block] = []

    def lauf(el: _El) -> None:
        for k in el.kinder:
            if isinstance(k, str):
                continue
            if k.klassen & {"note", "signatory"} or k.tag in ("script", "style", "head"):
                continue
            if "final" in k.klassen:
                bloecke.append(_Block("schluss"))
                continue
            if k.tag == "table":
                liste = _als_liste(k)
                if liste is not None:
                    bloecke.append(_Block("liste", eintraege=liste))
                else:
                    lauf(k)  # Kopf des Amtsblatts und andere Tabellen
                continue
            if k.tag == "p":
                art = next((a for c, a in _P_KLASSEN.items() if c in k.klassen), None)
                text = _rein(_text(k))
                if art and text:
                    bloecke.append(_Block(art, text))
                continue
            lauf(k)

    lauf(wurzel)
    return bloecke


def _als_liste(tabelle: _El) -> list[tuple[str, str]] | None:
    """Eine zweispaltige Tabelle mit Gliederungspunkten links ist eine Aufzählung."""
    zeilen = _zellen(tabelle)
    if not zeilen or any(len(z) != 2 for z in zeilen):
        return None
    eintraege = []
    for punkt_zelle, text_zelle in zeilen:
        punkt = _rein(_text(punkt_zelle))
        if _ERWAEGUNG_NR.match(punkt):
            nr = punkt.strip("()")
        else:
            m = _PUNKT.match(punkt)
            if not m:
                return None
            nr = m.group(1) or m.group(2)
        eintraege.append((nr, _rein(_text(text_zelle))))
    return eintraege


# --- Rechtsakt zusammensetzen -----------------------------------------------------------------------


_KLEIN = {"des", "der", "und", "vom", "zur", "zum", "über", "die", "den", "dem", "für", "in"}


def _titelschrift(zeile: str) -> str:
    """"VERORDNUNG (EU) 2016/679 DES EUROPÄISCHEN PARLAMENTS" -> "Verordnung (EU) 2016/679 des Europäischen …"."""
    if re.sub(r"\bNr\.", "", zeile) != re.sub(r"\bNr\.", "", zeile).upper():
        return zeile
    woerter = []
    for w in zeile.split():
        if w.lower() in _KLEIN:
            woerter.append(w.lower())
        elif re.fullmatch(r"\([A-Z]{2,4}\)|EU|EG|EWG|EWR|[\d/.,]+", w):
            woerter.append(w)
        elif w in ("NR.", "Nr."):
            woerter.append("Nr.")
        else:
            woerter.append(w[:1] + w[1:].lower())
    return " ".join(woerter)


def _gliederungsname(text: str) -> tuple[int, str]:
    erstes = text.split()[0].upper()
    ebene = _EBENEN.index(erstes) if erstes in _EBENEN else len(_EBENEN)
    return ebene, (erstes.capitalize() + text[len(erstes):]) if erstes in _EBENEN else text


def _builddate(datum: str | None) -> str | None:
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", datum or "")
    return f"{m.group(3)}{int(m.group(2)):02d}{int(m.group(1)):02d}" if m else None


@dataclass
class _Artikel:
    nummer: str
    titel: str | None = None
    gliederung: list[str] = field(default_factory=list)
    teile: list[list[str | Liste]] = field(default_factory=list)  # je Absatz
    nummern: list[str | None] = field(default_factory=list)

    def hinzu(self, teil: str | Liste) -> None:
        if isinstance(teil, str):
            m = _ABSATZ_NR.match(teil)
            if m:
                self.nummern.append(m.group(1))
                self.teile.append([teil[m.end():]])
                return
            m = _PUNKT_IM_TEXT.match(teil)
            if m and self.teile and not m.group(1).isdigit():
                # Ältere Rechtsakte setzen "a) …" als einfachen Absatz statt als Tabelle.
                teil = Liste([(m.group(1), teil[m.end():])])
        if not self.teile:
            self.nummern.append(None)
            self.teile.append([])
        absatz = self.teile[-1]
        if isinstance(teil, Liste) and absatz and isinstance(absatz[-1], Liste):
            absatz[-1].eintraege.extend(teil.eintraege)
        elif isinstance(teil, str) and absatz:
            absatz.append(("\n" if isinstance(absatz[-1], Liste) else " ") + teil)
        else:
            absatz.append(teil)


def parse_eurlex_html(daten: bytes | str, abk: str = "") -> GesetzDokument:
    """Parst die HTML-Fassung eines Rechtsakts aus EUR-Lex."""
    text = daten.decode("utf-8", "replace") if isinstance(daten, bytes) else daten
    baum = _Baum()
    baum.feed(text)
    baum.close()
    bloecke = _bloecke(baum.wurzel)

    datum = next((b.text for b in bloecke if b.art == "kopf_datum"), None)
    abl = next((b.text for b in bloecke if b.art == "kopf_abl"), None)
    titelzeilen = [b.text for b in bloecke if b.art == "titel" and "Text von Bedeutung" not in b.text]
    dokument = GesetzDokument(
        abk=abk,
        langtitel=" ".join(_titelschrift(z) for z in titelzeilen[:3]) or None,
        builddate=_builddate(datum),
        doknr=None,
    )
    if abl:
        m = re.match(r"([A-Z]+)\s*(\d+)\s*/\s*(\d+)", abl)
        dokument.stand = [f"ABl. {m.group(1)} {m.group(2)} vom {datum}, S. {m.group(3)}" if m and datum else abl]

    erwaegungen: list[tuple[str, str]] = []
    artikel: list[_Artikel] = []
    gliederung: list[tuple[int, str]] = []
    vor_artikeln = True
    for b in bloecke:
        if b.art == "schluss" or (b.art == "text" and b.text.startswith(_SCHLUSS)):
            if artikel:
                break
            continue
        if b.art == "artikel":
            m = re.match(r"^Artikel\s+(\d+[a-z]?)", b.text)
            if not m:
                continue
            vor_artikeln = False
            artikel.append(_Artikel(m.group(1), gliederung=[n for _, n in gliederung]))
        elif vor_artikeln:
            if b.art == "liste":
                erwaegungen += [(nr, t) for nr, t in b.eintraege if nr.isdigit()]
            elif b.art == "text" and (m := _ABSATZ_NR.match(b.text)) and m.group(1).isdigit():
                erwaegungen.append((m.group(1), b.text[m.end():]))
            elif b.art == "gliederung":
                gliederung = [_gliederungsname(b.text)]
            elif b.art == "gliederung_titel" and gliederung:
                ebene, name = gliederung[-1]
                gliederung[-1] = (ebene, f"{name} {b.text}")
        elif b.art == "gliederung":
            ebene, name = _gliederungsname(b.text)
            while gliederung and gliederung[-1][0] >= ebene:
                gliederung.pop()
            gliederung.append((ebene, name))
        elif b.art == "gliederung_titel" and gliederung:
            ebene, name = gliederung[-1]
            gliederung[-1] = (ebene, f"{name} {b.text}")
        elif b.art == "artikel_titel" and artikel and artikel[-1].titel is None and not artikel[-1].teile:
            artikel[-1].titel = b.text
        elif b.art == "text" and artikel:
            artikel[-1].hinzu(b.text)
        elif b.art == "liste" and artikel:
            artikel[-1].hinzu(Liste(b.eintraege))

    if not artikel:
        raise ValueError("Kein Rechtsakt aus EUR-Lex: keine Artikel gefunden.")
    reihenfolge = 0
    for nr, t in erwaegungen:
        reihenfolge += 1
        dokument.normen.append(Norm(
            doknr=f"rct_{nr}", reihenfolge=reihenfolge, bezeichnung=f"Erwägungsgrund {nr}",
            typ="erwaegungsgrund", nummer=nr, titel=None, gliederung=["Erwägungsgründe"],
            absaetze=[Absatz(nr=None, text=t, saetze=zerlege_in_saetze([t]))], weggefallen=False,
        ))
    for a in artikel:
        reihenfolge += 1
        absaetze = [Absatz(nr=nr, text=_verbinde(teile), saetze=zerlege_in_saetze(teile))
                    for nr, teile in zip(a.nummern, a.teile, strict=True)]
        dokument.normen.append(Norm(
            doknr=f"art_{a.nummer}", reihenfolge=reihenfolge, bezeichnung=f"Art. {a.nummer}", typ="artikel",
            nummer=a.nummer, titel=a.titel, gliederung=a.gliederung, absaetze=absaetze,
            weggefallen=not absaetze,
        ))
    return dokument


def _verbinde(teile: list[str | Liste]) -> str:
    stuecke = [("\n" + t.als_text() + "\n") if isinstance(t, Liste) else t for t in teile]
    return re.sub(r"[ \t]*\n[ \t]*", "\n", "".join(stuecke)).strip()
