"""Landesrecht Bayern aus dem Bürgerservice BAYERN.RECHT (gesetze-bayern.de).

Das Portal bietet für Vorschriften keinen XML-Download wie Gesetze im Internet. Geladen wird
deshalb die Gesamtansicht einer Vorschrift (``/Content/Document/<Kennung>/true``), eine HTML-Seite
mit Inhaltsübersicht und dem Text aller Artikel. Gesendet wird nur die Kennung der Vorschrift
(z. B. ``BayBO``), nichts aus einer Akte. Die Seite wird unverändert unter ihrer SHA-256-Prüfsumme
archiviert.

Der Leser arbeitet zeilenweise auf dem Text der Seite und hängt nicht an Klassennamen: Artikel
beginnen mit einer Zeile „Art. 1“ (Überschrift in der Zeile darunter), Absätze mit „(1)“,
Aufzählungen mit „1.“ oder „a)“, Gliederungen mit „Erster Teil“ oder „Abschnitt I“. Die hochgestellten
Satznummern („¹Dieses Gesetz …“) werden entfernt; die Sätze zählt die Satzzerlegung selbst.
Zeilen, die nur aus einem Verweis bestehen (Inhaltsübersicht, Navigation), werden übergangen.

Nutzung (gesetze-bayern.de/Content/Document/Nutzungshinweise): Vorschriften dürfen uneingeschränkt
weiterverwendet werden; die Datenbank genießt Schutz nach §§ 87a ff. UrhG. Deshalb nur einzelne
Abrufe auf Nutzeraktion mit einer Pause dazwischen, kein Massenabruf.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .. import netzprotokoll
from ..htmlleser import HtmlLeser, leerraum
from .gii import Absatz, GesetzDokument, Norm
from .saetze import Liste, zerlege_in_saetze

BASIS = "https://www.gesetze-bayern.de"
HERKUNFT = "gesetze-bayern.de"
QUELLE = "bayern"
USER_AGENT = "advOrdo/0.1 (Wissensbasis-Import)"
HINWEIS = ("Nichtamtliche Fassung aus dem Bürgerservice BAYERN.RECHT (gesetze-bayern.de). "
           "Maßgeblich ist die Veröffentlichung im Gesetz- und Verordnungsblatt.")
PAUSE = 1.0  # Sekunden zwischen zwei Abrufen

_KENNUNG = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,40}$")
_letzter_abruf = 0.0


def adresse(kennung: str) -> str:
    return f"{BASIS}/Content/Document/{kennung}/true"


def ist_bayern(daten: bytes | str) -> bool:
    """Ob eine Datei die Gesamtansicht einer Vorschrift aus gesetze-bayern.de ist."""
    kopf = daten[:400_000] if isinstance(daten, str) else daten[:400_000].decode("utf-8", "replace")
    return ("gesetze-bayern.de" in kopf or "BAYERN.RECHT" in kopf or "Bürgerservice" in kopf) and (
        "Vollzitat" in kopf or "Text gilt ab" in kopf
    )


def lade(kennung: str, timeout: float = 60) -> tuple[bytes, str]:
    """Lädt die Gesamtansicht einer Vorschrift; zwischen zwei Abrufen liegt mindestens ``PAUSE``."""
    global _letzter_abruf
    if not _KENNUNG.match(kennung):
        raise ValueError(f"Ungültige Kennung einer bayerischen Vorschrift: {kennung!r}")
    warten = _letzter_abruf + PAUSE - time.monotonic()
    if warten > 0:
        time.sleep(warten)
    url = adresse(kennung)
    anfrage = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Language": "de"}
    )
    try:
        with netzprotokoll.anlass(f"Landesrecht Bayern laden ({kennung})"), \
                urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            daten = antwort.read()
    except urllib.error.HTTPError as fehler:
        if fehler.code == 404:
            raise ValueError(f"{kennung} wurde auf gesetze-bayern.de nicht gefunden.") from None
        raise
    finally:
        _letzter_abruf = time.monotonic()
    if not ist_bayern(daten):
        raise ValueError(
            f"gesetze-bayern.de hat für {kennung} keinen lesbaren Gesetzestext geliefert. Die Seite im Browser öffnen "
            f"({url}), als „Webseite, nur HTML“ speichern und unter Gesetze mit „Datei importieren …“ laden."
        )
    return daten, url


def kennzeichen(daten: bytes | str) -> str:
    """Stand der Vorschrift (gilt ab, Vollzitat), um unveränderte Seiten nicht erneut zu speichern.

    Die Seite selbst enthält wechselnde Teile (Sitzung, Prüfzeichen), die Prüfsumme ändert sich also bei jedem
    Abruf. Ob sich die Vorschrift geändert hat, zeigen „Text gilt ab“ und das Vollzitat."""
    dok = parse_bayern_html(daten)
    return " | ".join([dok.builddate or "", *dok.stand, str(len(dok.normen))])


def abk_aus_titel(daten: bytes | str) -> str | None:
    """Abkürzung aus dem Seitentitel („BayBO: Bayerische Bauordnung …“)."""
    text = daten if isinstance(daten, str) else daten[:400_000].decode("utf-8", "replace")
    m = re.search(r"<title[^>]*>\s*([^<:]{1,40}):", text, re.I)
    return m.group(1).strip() if m else None


# --- Seite in Zeilen zerlegen -----------------------------------------------------------------------

_BLOCK = {"p", "div", "br", "li", "ul", "ol", "dl", "dt", "dd", "tr", "td", "th", "table", "section", "article",
          "header", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "nav", "main", "aside", "hr"}
# Kein "form": Die ganze Seite steckt in einem Suchformular.
_UEBERSPRINGEN = {"script", "style", "noscript", "template", "select", "option", "button"}
_LEER = {"br", "img", "hr", "meta", "link", "input", "wbr", "col", "area", "base", "source"}


_ANLAGE = "\x00Anlage"
_HOCH = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


@dataclass
class _Zeile:
    text: str
    ueberschrift: bool = False
    nur_verweis: bool = False


class _Zeilen(HtmlLeser):
    def __init__(self) -> None:
        super().__init__()
        self.zeilen: list[_Zeile] = []
        self.titel = ""
        self._stapel: list[str] = []
        self._klassen: list[set[str]] = []  # Klassen je offenem Element, parallel zu _stapel
        self._teile: list[tuple[str, bool]] = []  # (Text, innerhalb eines Verweises)
        self._sup = ""

    def _im(self, *tags: str) -> bool:
        return any(t in self._stapel for t in tags)

    def _klasse(self, *namen: str) -> bool:
        return any(n in k for k in self._klassen for n in namen)

    def _ausgeben(self) -> None:
        text = leerraum("".join(t for t, _ in self._teile))
        if text:
            sichtbar = [(t, v) for t, v in self._teile if t.strip()]
            self.zeilen.append(_Zeile(
                text,
                ueberschrift=self._im("h1", "h2", "h3", "h4", "h5", "h6"),
                nur_verweis=bool(sichtbar) and all(v for _, v in sichtbar),
            ))
        self._teile = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK:
            self._ausgeben()
        if tag not in _LEER:
            self._stapel.append(tag)
            self._klassen.append(klassen := set(self.attribute(attrs).get("class", "").split()))
            if "annexheading" in klassen:
                self.zeilen.append(_Zeile(_ANLAGE))  # Anlagen sind keine Artikel; der letzte Artikel endet hier

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK:
            self._ausgeben()

    def handle_endtag(self, tag: str) -> None:
        if tag in _LEER:
            return
        if tag in self._stapel:
            while self._stapel:
                self._klassen.pop()
                if self._stapel.pop() == tag:
                    break
        if tag in _BLOCK:
            self._ausgeben()

    def handle_data(self, data: str) -> None:
        if self._im("title"):
            self.titel += data
            return
        if self._im(*_UEBERSPRINGEN) or self._im("head"):
            return
        # Satznummern („<sup class="satznr">1</sup>“), Fußnotenzeichen und Fußnoten gehören nicht zum Normtext.
        if self._klasse("satznr", "footnotelink-down", "footnotelink-up", "fn-container"):
            return
        if self._im("sup") and data.strip().isdigit():
            data = data.translate(_HOCH)  # m² und m³ bleiben lesbar
        self._teile.append((data, self._im("a")))

    def close(self) -> None:
        super().close()
        self._ausgeben()


# --- Zeilen deuten ----------------------------------------------------------------------------------

_ART = re.compile(r"^(Art\.|§)\s*(\d+[a-z]?)(?:\s+(.+))?$")
_ABSATZ = re.compile(r"^\((\d+[a-z]?)\)\s*(.*)$")
_PUNKT_ALLEIN = re.compile(r"^(\d+[a-z]?)\.$|^([a-z]{1,2})\)$")
_PUNKT_TEXT = re.compile(r"^(\d+[a-z]?)\.\s+(.+)$|^([a-z]{1,2})\)\s+(.+)$")
_EBENEN = {"Buch": 0, "Teil": 1, "Kapitel": 2, "Abschnitt": 3, "Unterabschnitt": 4, "Titel": 5}
_GLIEDERUNG = re.compile(
    r"^(?:[A-ZÄÖÜ][a-zäöüß]+(?:te|ter|tes)\s+(?P<a>Buch|Teil|Kapitel|Abschnitt|Unterabschnitt|Titel)"
    r"|(?P<b>Buch|Teil|Kapitel|Abschnitt|Unterabschnitt|Titel)\s+(?:[IVXLC]+|\d+)[a-z]?)\b"
)
# Satznummer ohne Hochstellung, an das erste Wort geklebt: „(1) 1Dieses Gesetz … 2Es gilt …“.
_SATZNUMMER = re.compile(r"(?:(?<=^)|(?<=\) )|(?<=[.:;!?] ))\d{1,2}(?=[A-ZÄÖÜ„])")
_ENDE = {"Impressum", "Datenschutz", "Datenschutzerklärung", "Barrierefreiheit", "Kontakt", "Nutzungshinweise",
         "Nach oben", "Seitenanfang", "Zum Seitenanfang"}
_WEG = {"(aufgehoben)", "(weggefallen)", "aufgehoben", "weggefallen"}


@dataclass
class _Artikel:
    zeichen: str
    nummer: str
    gliederung: list[str]
    titel: str | None = None
    nummern: list[str | None] = field(default_factory=list)
    teile: list[list[str | Liste]] = field(default_factory=list)
    punkt: str | None = None  # Gliederungspunkt einer Aufzählung, dessen Text in der nächsten Zeile steht

    def _absatz(self) -> list[str | Liste]:
        if not self.teile:
            self.nummern.append(None)
            self.teile.append([])
        return self.teile[-1]

    def neuer_absatz(self, nr: str, text: str) -> None:
        self.nummern.append(nr)
        self.teile.append([])
        if text:
            self.text(text)

    def eintrag(self, nr: str, text: str) -> None:
        absatz = self._absatz()
        if absatz and isinstance(absatz[-1], Liste):
            liste = absatz[-1]
            letzte_nr = liste.eintraege[-1][0]
            if not nr.isdigit() and not nr[0].isdigit() and letzte_nr[0].isdigit():
                # Unterpunkt „a)“ unter „1.“: wie bei Gesetze im Internet in den Text der Nummer.
                alt_nr, alt_text = liste.eintraege[-1]
                liste.eintraege[-1] = (alt_nr, f"{alt_text} {nr}) {text}")
                return
            liste.eintraege.append((nr, text))
        else:
            absatz.append(Liste([(nr, text)]))

    def text(self, text: str) -> None:
        absatz = self._absatz()
        if absatz and isinstance(absatz[-1], str):
            absatz[-1] += " " + text
        elif absatz:
            absatz.append("\n" + text)
        else:
            absatz.append(text)


def _ohne_satznummern(text: str) -> str:
    return _SATZNUMMER.sub("", text).strip()


def _builddate(text: str) -> str | None:
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    return f"{m.group(3)}{int(m.group(2)):02d}{int(m.group(1)):02d}" if m else None


def _ist_titel(z: _Zeile) -> bool:
    t = z.text
    if z.ueberschrift or t in _WEG:
        return True
    return len(t) <= 160 and not t.endswith((".", ":", ",", ";")) and not _ABSATZ.match(t) \
        and not _PUNKT_ALLEIN.match(t) and not _PUNKT_TEXT.match(t)


def parse_bayern_html(daten: bytes | str, abk: str = "") -> GesetzDokument:
    """Parst die Gesamtansicht einer Vorschrift aus gesetze-bayern.de."""
    text = daten.decode("utf-8", "replace") if isinstance(daten, bytes) else daten
    leser = _Zeilen.lies(text)

    seitentitel = re.sub(r"\s+", " ", leser.titel).strip()
    langtitel = re.sub(r"^[^:]{1,40}:\s*", "", seitentitel)
    langtitel = re.sub(r"\s*-\s*Bürgerservice.*$", "", langtitel)
    langtitel = re.sub(r"\s*\((?:Art\.|§)[^)]*\)\s*$", "", langtitel).strip() or None
    dokument = GesetzDokument(abk=abk or (abk_aus_titel(text) or ""), langtitel=langtitel, builddate=None, doknr=None)

    artikel: list[_Artikel] = []
    gliederung: list[tuple[int, str]] = []
    gliederung_offen = False  # die Gliederungsüberschrift kann in der nächsten Zeile weitergehen
    titel_offen = False
    for z in leser.zeilen:
        t = z.text
        if dokument.builddate is None and (m := re.match(r"^Text gilt ab:?\s*(.+)$", t)):
            dokument.builddate = _builddate(m.group(1))
            continue
        if t.startswith("Vollzitat") and not dokument.stand:
            dokument.stand = [re.sub(r"^Vollzitat(?: nach RedR)?:?\s*", "", t)]
            continue
        if z.nur_verweis:
            continue
        if artikel and (t in _ENDE or t.startswith("©") or t == _ANLAGE):
            break

        m = _ART.match(t)
        if m and (m.group(3) is None or z.ueberschrift):
            artikel.append(_Artikel(m.group(1), m.group(2), [n for _, n in gliederung], titel=m.group(3)))
            titel_offen = m.group(3) is None
            gliederung_offen = False
            continue
        g = _GLIEDERUNG.match(t)
        if g and len(t) <= 200 and not t.endswith((".", ",", ";")):
            ebene = _EBENEN[g.group("a") or g.group("b")]
            while gliederung and gliederung[-1][0] >= ebene:
                gliederung.pop()
            gliederung.append((ebene, t))
            gliederung_offen = len(t.split()) <= 3
            titel_offen = False
            continue
        if gliederung_offen and _ist_titel(z) and not _ABSATZ.match(t):
            ebene, name = gliederung[-1]
            gliederung[-1] = (ebene, f"{name} {t}")
            gliederung_offen = False
            continue
        gliederung_offen = False
        if not artikel:
            continue
        a = artikel[-1]
        if titel_offen:
            titel_offen = False
            if _ist_titel(z):
                a.titel = t
                continue
        if a.punkt is not None:
            punkt, a.punkt = a.punkt, None
            a.eintrag(punkt, _ohne_satznummern(t))
            continue
        if m := _ABSATZ.match(t):
            a.neuer_absatz(m.group(1), _ohne_satznummern(m.group(2)))
        elif m := _PUNKT_ALLEIN.match(t):
            a.punkt = m.group(1) or m.group(2)
        elif m := _PUNKT_TEXT.match(t):
            a.eintrag(m.group(1) or m.group(3), _ohne_satznummern(m.group(2) or m.group(4)))
        else:
            a.text(_ohne_satznummern(t))

    if not artikel:
        raise ValueError("Keine Vorschrift aus gesetze-bayern.de: keine Artikel gefunden.")
    if not dokument.abk:
        raise ValueError("Die Abkürzung der Vorschrift ließ sich nicht erkennen.")
    gesehen: set[str] = set()
    for i, a in enumerate(artikel, 1):
        bezeichnung = f"{a.zeichen} {a.nummer}"
        if bezeichnung in gesehen:
            continue  # dieselbe Überschrift doppelt (z. B. Kopf und Text) – die erste gilt
        gesehen.add(bezeichnung)
        absaetze = [Absatz(nr=nr, text=_verbinde(teile), saetze=zerlege_in_saetze(teile))
                    for nr, teile in zip(a.nummern, a.teile, strict=True) if teile]
        weg = (a.titel or "").strip() in _WEG or not absaetze or all(x.text.strip() in _WEG for x in absaetze)
        dokument.normen.append(Norm(
            doknr=f"{QUELLE}_{a.nummer}", reihenfolge=i, bezeichnung=bezeichnung,
            typ="artikel" if a.zeichen == "Art." else "paragraph", nummer=a.nummer, titel=a.titel,
            gliederung=a.gliederung, absaetze=absaetze, weggefallen=weg,
        ))
    return dokument


def _verbinde(teile: list[str | Liste]) -> str:
    stuecke = [("\n" + t.als_text() + "\n") if isinstance(t, Liste) else t for t in teile]
    return re.sub(r"[ \t]*\n[ \t]*", "\n", "".join(stuecke)).strip()
