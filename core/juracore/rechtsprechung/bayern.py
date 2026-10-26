"""Entscheidungen bayerischer Gerichte aus dem Bürgerservice BAYERN.RECHT (gesetze-bayern.de).

Das Portal hat kein herunterladbares Verzeichnis und keine Programmierschnittstelle. Gesucht wird
deshalb live über das Suchformular, und nur auf Nutzeraktion: Filter „Rechtsprechung“ setzen
(Sitzungscookie), Formular mit Prüfzeichen (CSRF) laden, Aktenzeichen absenden, Trefferliste lesen.
Gesendet wird nur das Aktenzeichen der zitierten Entscheidung, nichts aus der Akte.

Volltexte gibt es je Entscheidung als ZIP mit einer XML-Datei. Die in der Datei genannte DTD ist
nicht abrufbar; das Format ist der Beschreibung von JuraBox Lite entnommen (dort an echten
Dokumenten ermittelt). Das ZIP wird unverändert unter seiner SHA-256-Prüfsumme archiviert.

Nutzung (gesetze-bayern.de/Content/Document/Nutzungshinweise): Vorschriften und Entscheidungen
dürfen uneingeschränkt weiterverwendet werden; die redaktionellen Leitsätze (C.H.Beck) unterliegen
dem Urheberpersönlichkeitsrecht, die Datenbank dem Schutz nach §§ 87a ff. UrhG. Deshalb nur
einzelne Abrufe, kein Massenabruf.
"""

from __future__ import annotations

import html
import http.cookiejar
import io
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from html.entities import name2codepoint

from .verzeichnis import USER_AGENT
from .volltext import Absatz, Volltext

BASIS = "https://www.gesetze-bayern.de"
HERKUNFT = "gesetze-bayern.de"
HINWEIS = ("Quelle: Bürgerservice BAYERN.RECHT (gesetze-bayern.de). Redaktionell bearbeitete, anonymisierte "
           "Fassung, kein amtlicher Text; redaktionelle Leitsätze urheberrechtlich geschützt.")

# Sitze bayerischer Gerichte, soweit sie in Zitaten als Ort stehen („OLG München“, „LG Traunstein“).
# Mehrdeutige Orte (Neustadt, Landau) fehlen bewusst; solche Zitate prüft man über „Urteil selbst ergänzen“.
ORTE = frozenset("""
Aichach Altötting Amberg Ansbach Aschaffenburg Augsburg Bamberg Bayern Bayreuth Cham Coburg Dachau Deggendorf
Dillingen Ebersberg Eichstätt Erding Erlangen Freising Freyung Fürstenfeldbruck Fürth Garmisch-Partenkirchen
Gemünden Günzburg Hersbruck Hof Ingolstadt Kaufbeuren Kelheim Kempten Kitzingen Kronach Kulmbach Landsberg
Landshut Laufen Lichtenfels Lindau Memmingen Miesbach Mühldorf München Neuburg Neumarkt Neu-Ulm Nördlingen
Nürnberg Nürnberg-Fürth Obernburg Passau Pfaffenhofen Regen Regensburg Rosenheim Schwabach Schwandorf
Schweinfurt Sonthofen Starnberg Straubing Tirschenreuth Traunstein Viechtach Weiden Weilheim Weißenburg
Wolfratshausen Wunsiedel Würzburg
""".split())
_OHNE_ORT = frozenset({"BayObLG", "BayVerfGH", "BayVGH"})

# Kürzel der Entscheidungsart im Portal (kein festes Vokabular; Unbekanntes bleibt, wie es ist).
DOKTYPEN = {"Urt": "Urteil", "Bes": "Beschluss", "EndUrt": "Endurteil", "Beschl": "Beschluss",
            "TUrt": "Teilurteil", "VU": "Versäumnisurteil", "Ent": "Entscheidung", "GB": "Gerichtsbescheid",
            "Hinweisbeschluss": "Hinweisbeschluss"}

# Teile im Abschnitt <textdaten>, in der Reihenfolge der Anzeige; Unbekanntes folgt danach.
TEILE = {"leitsatz": "Leitsatz", "tenor": "Tenor", "tatbestand": "Tatbestand",
         "entscheidungsgruende": "Entscheidungsgründe", "gruende": "Gründe"}


def ist_bayerisch(gericht: str) -> bool:
    """Ob ein zitiertes Gericht ein bayerisches ist („OLG München“, „BayObLG“, „VGH München“)."""
    teile = gericht.split()
    if not teile:
        return False
    if teile[0] in _OHNE_ORT:
        return True
    return len(teile) > 1 and teile[1] in ORTE


def adresse(doknr: str) -> str:
    """Leseadresse der Entscheidung im Portal."""
    return f"{BASIS}/Content/Document/{_pruefe_doknr(doknr)}"


def _pruefe_doknr(doknr: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", doknr or ""):
        raise ValueError(f"Ungültige Dokumentnummer: {doknr!r}")
    return doknr


# --- Trefferliste ----------------------------------------------------------------------------------


@dataclass
class Treffer:
    doknr: str
    gericht: str  # „OLG München“
    titel: str  # Schlagworte hinter dem Doppelpunkt
    doktyp: str | None  # „Endurteil“
    datum: str | None  # ISO
    aktenzeichen: str | None

    def als_dict(self) -> dict:
        return {"quelle": "bayern", "doknr": self.doknr, "gericht": self.gericht, "spruchkoerper": None,
                "datum": self.datum, "aktenzeichen": self.aktenzeichen or "", "doktyp": self.doktyp,
                "titel": self.titel, "ausschnitt": None, "link": adresse(self.doknr)}


_TITEL = re.compile(
    r'<p[^>]*class="hltitel"[^>]*>\s*<a[^>]*href="/Content/Document/([^"?]+)[^"]*"[^>]*>(.*?)</a>', re.S)
_UNTERTITEL = re.compile(r'<p[^>]*class="hlSubTitel"[^>]*>(.*?)</p>', re.S)
_GESAMT = re.compile(r"([\d.]+)\s+Treffer")
_UNTER = re.compile(r"^(?P<art>.*?)\s+vom\s+(?P<datum>\d{1,2}\.\d{1,2}\.\d{4})\s*[–—-]\s*(?P<az>.+)$")


def _klartext(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _iso(datum: str) -> str | None:
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", datum)
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def lies_trefferliste(seite: str) -> tuple[list[Treffer], int | None]:
    """Liest die Trefferliste: je Treffer Titelzeile (Gericht: Schlagworte) und Unterzeile (Art vom Datum – Az)."""
    titel = list(_TITEL.finditer(seite))
    treffer = []
    for i, m in enumerate(titel):
        ende = titel[i + 1].start() if i + 1 < len(titel) else len(seite)
        unter = _UNTERTITEL.search(seite, m.end(), ende)
        kopf = _klartext(m.group(2))
        gericht, _, schlagworte = kopf.partition(":")
        art = datum = az = None
        if unter and (u := _UNTER.match(_klartext(unter.group(1)))):
            art, datum, az = u.group("art"), _iso(u.group("datum")), u.group("az").strip()
        treffer.append(Treffer(html.unescape(m.group(1)), gericht.strip(), schlagworte.strip(),
                               DOKTYPEN.get(art, art) if art else None, datum, az))
    gesamt = _GESAMT.search(_klartext(seite))
    return treffer, int(gesamt.group(1).replace(".", "")) if gesamt else (len(treffer) if treffer else None)


# --- Abruf -----------------------------------------------------------------------------------------


_TOKEN = re.compile(r'__RequestVerificationToken"[^>]*value="([^"]+)"')


# Gerichtsbarkeiten, nach denen das Portal filtert (oberste Ebene des Gerichtsbaums).
GERICHTSBARKEITEN = ("Verfassungsgerichtsbarkeit", "Ordentliche Gerichtsbarkeit", "Verwaltungsgerichtsbarkeit",
                     "Finanzgerichtsbarkeit", "Arbeitsgerichtsbarkeit", "Sozialgerichtsbarkeit", "Dienstgericht",
                     "Sonstige Gerichte")


def _tag(iso: str | None) -> str:
    if not iso:
        return ""
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def suche(aktenzeichen: str = "", timeout: float = 30, *, volltext: str = "", von: str | None = None,
          bis: str | None = None, gerichtsbarkeit: str | None = None) -> tuple[list[Treffer], int | None]:
    """Sucht Entscheidungen nach Aktenzeichen, Volltext, Zeitraum (ISO) und Gerichtsbarkeit. Je Suche eine eigene
    Sitzung, weil die Filter je Sitzung gelten. Geliefert wird die erste Seite der Trefferliste."""
    if gerichtsbarkeit is not None and gerichtsbarkeit not in GERICHTSBARKEITEN:
        raise ValueError(f"Unbekannte Gerichtsbarkeit: {gerichtsbarkeit!r}")
    oeffner = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    oeffner.addheaders = [("User-Agent", USER_AGENT)]

    def hole(pfad: str, daten: bytes | None = None) -> str:
        with oeffner.open(BASIS + pfad, data=daten, timeout=timeout) as antwort:
            return antwort.read().decode("utf-8", errors="replace")

    hole("/Search/Filter/DOKTYP/rspr")
    if gerichtsbarkeit:
        hole("/Search/Filter/LEVEL1RSPRTREENODE/" + urllib.parse.quote(gerichtsbarkeit))
    formular = hole("/Search/Hitlist")
    token = _TOKEN.search(formular)
    if token is None:
        raise ValueError("Das Suchformular von gesetze-bayern.de hat sich geändert (kein Prüfzeichen gefunden).")
    felder = {"SearchFields.Aktenzeichen": aktenzeichen.strip(), "SearchFields.Content": volltext.strip(),
              "SearchFields.DatumVon": _tag(von), "SearchFields.DatumBis": _tag(bis),
              "__RequestVerificationToken": html.unescape(token.group(1))}
    # Die Antwort leitet auf die Trefferliste weiter; urllib folgt der Weiterleitung mit GET.
    return lies_trefferliste(hole("/Search", urllib.parse.urlencode(felder).encode()))


def lade(doknr: str, timeout: float = 60) -> bytes:
    """Lädt das ZIP einer Entscheidung."""
    anfrage = urllib.request.Request(f"{BASIS}/Content/Zip/{_pruefe_doknr(doknr)}",
                                     headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
        return antwort.read()


# --- Volltext --------------------------------------------------------------------------------------


_XML_ENTITAETEN = {"amp", "lt", "gt", "quot", "apos"}


def _entitaeten(daten: bytes) -> bytes:
    """HTML-Entitäten (&nbsp; …) in Zeichen übersetzen: Ohne DTD kennt der XML-Leser sie nicht."""
    def ersetze(m: re.Match) -> bytes:
        name = m.group(1).decode()
        if name in _XML_ENTITAETEN or name not in name2codepoint:
            return m.group(0)
        return f"&#{name2codepoint[name]};".encode()
    return re.sub(rb"&([A-Za-z][A-Za-z0-9]*);", ersetze, daten)


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    teile: list[str] = []

    def sammle(e: ET.Element) -> None:
        if e.tag == "br":
            teile.append("\n")
        if e.text:
            teile.append(e.text)
        for k in e:
            sammle(k)
            if k.tail:
                teile.append(k.tail)

    sammle(el)
    return "\n".join(" ".join(z.split()) for z in "".join(teile).split("\n")).strip()


def _absaetze(teil: str, el: ET.Element) -> list[Absatz]:
    """Absätze eines Teils; die Randnummer steht als leeres <rd nr="N"/> vor dem Text im selben <p>."""
    ergebnis = []
    for p in el.iter("p"):
        if any(True for _ in p.iter("p") if _ is not p):
            continue  # nur innerste Absätze
        rd = p.find(".//rd")
        text = _text(p)
        if not text:
            continue
        nr = rd.get("nr") if rd is not None else None
        ergebnis.append(Absatz(teil, int(nr) if nr and nr.isdigit() else None, text))
    if not ergebnis and (text := _text(el)):
        ergebnis.append(Absatz(teil, None, text))
    return ergebnis


def lies(daten: bytes, entscheidung: dict | None = None) -> Volltext:
    """Liest eine Entscheidung (ZIP mit bayportalrsp/<doknr>.xml oder die XML-Datei selbst)."""
    if daten[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(daten)) as z:
            # Neben der Entscheidung liegt META-INF/manifest.xml im Archiv.
            xmls = [n for n in z.namelist() if n.lower().endswith(".xml") and not n.upper().startswith("META-INF/")]
            if len(xmls) != 1:
                raise ValueError(f"Erwartet genau eine XML-Datei im Archiv, gefunden: {xmls}")
            doknr_datei = xmls[0].rsplit("/", 1)[-1][:-4]
            daten = z.read(xmls[0])
    else:
        doknr_datei = None
    try:
        wurzel = ET.fromstring(_entitaeten(daten))
    except ET.ParseError as fehler:
        raise ValueError(f"Die Entscheidung ist kein lesbares XML ({fehler}).") from fehler
    meta, textdaten = wurzel.find(".//metadaten"), wurzel.find(".//textdaten")
    if meta is None or textdaten is None or not meta.findtext("aktenzeichen"):
        raise ValueError("Die Datei ist keine Entscheidung im Format von gesetze-bayern.de.")

    def feld(name: str) -> str | None:
        return _text(meta.find(name)) or None

    gericht_el = meta.find("gericht")
    gericht = " ".join(filter(None, [_text(gericht_el.find("gertyp")), _text(gericht_el.find("gerort"))])) \
        if gericht_el is not None else ""
    doktyp = feld("doktyp")
    datum = feld("entsch-datum")
    normen = [_text(n) for n in meta.findall("norm") if _text(n)]
    vorinstanz = []
    for v in meta.findall("vorinstanz"):
        art, ger, az, dat = (_text(v.find(k)) for k in ("doktyp", "gericht", "az", "datum"))
        vorinstanz.append(", ".join(filter(None, [ger, f"{DOKTYPEN.get(art, art)} vom {dat}" if dat else art,
                                                  f"Az: {az}" if az else ""])))
    v = Volltext(
        doknr=(entscheidung or {}).get("doknr") or doknr_datei or "",
        gericht=gericht or (entscheidung or {}).get("gericht") or "",
        spruchkoerper=feld("spruchkoerper"),
        datum=datum if datum and re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum) else None,
        aktenzeichen=feld("aktenzeichen") or "",
        doktyp=DOKTYPEN.get(doktyp, doktyp) if doktyp else None,
        normen=", ".join(normen) or None,
        vorinstanz=[z for z in vorinstanz if z],
        titel=_text(textdaten.find("titelzeile")) or None,
    )
    bekannt = list(TEILE)
    for name in bekannt:
        for el in textdaten.findall(name):  # Leitsätze stehen mehrfach als eigene Elemente
            v.absaetze.extend(_absaetze(name, el))
    for el in textdaten:
        if el.tag not in bekannt and el.tag != "titelzeile":
            v.absaetze.extend(_absaetze(el.tag, el))
    if not v.absaetze:
        raise ValueError(f"In der Entscheidung {v.aktenzeichen} wurde kein Text gefunden.")
    return v
