"""Bericht als PDF, ohne Zusatzbibliothek.

Das PDF erfüllt PDF/A-2a (ISO 19005-2, Langzeitarchiv) und PDF/UA-1 (ISO 14289-1, barrierefrei): Gesetzt wird in
der eingebetteten Liberation Sans (``schrift.py``, nur die benutzten Glyphen), die dieselben Zeichenbreiten wie
Helvetica hat und auch Zeichen außerhalb von WinAnsi kennt (etwa „ş“, „ł“, „č“ in Namen). Dazu kommen Strukturbaum
(Überschriften, Absätze, Schmuck und Fußzeile als Artefakt), Sprache, XMP-Metadaten mit Titel und den Kennungen
beider Normen, eine Ausgabebedingung mit sRGB-Profil (``farbprofil.py``) und eine Dateikennung. Einige Zeichen werden
ersetzt (z. B. „→“ durch „->“). Fehlen die Schriftdateien, wird ersatzweise in den nicht eingebetteten
Standardschriften Helvetica gesetzt (dann ohne PDF/A- und PDF/UA-Kennung). Zeilen werden mit den echten
Zeichenbreiten umbrochen. Format A4, Fußzeile mit Titel und „Seite n von m“.
"""

from __future__ import annotations

import hashlib
import re
import zlib
from dataclasses import dataclass

from . import Absatz, Bericht, Eintrag, Kopf, Ueberschrift, _helvetica, farbprofil, schrift

BREITE, HOEHE = 595.28, 841.89
LINKS, RECHTS, OBEN, UNTEN = 62.0, 62.0, 60.0, 64.0
SATZ = BREITE - LINKS - RECHTS

NORMAL, FETT, KURSIV = "F1", "F2", "F3"
_BREITEN = {NORMAL: _helvetica.NORMAL, FETT: _helvetica.FETT, KURSIV: _helvetica.NORMAL}
SCHWARZ, GRAU, ROT = "0 0 0", "0.35 0.35 0.35", "0.7 0.1 0.1"

_ERSATZ = str.maketrans({
    "→": "->", "←": "<-", "≤": "<=", "≥": ">=", "≠": "!=", "−": "-", "‑": "-", "‐": "-", " ": " ",
    "\u202f": " ", "\u200b": "", "\t": " ", "✓": "x", "•": "•", "\u00ad": "",
})


def _kodiere(text: str) -> bytes:
    text = text.translate(_ERSATZ)
    return text.encode("cp1252", errors="replace")


def breite(text: str, schrift: str, groesse: float) -> float:
    """Breite in den Standardschriften (WinAnsi)."""
    tabelle = _BREITEN[schrift]
    return sum(tabelle[b - 32] if b >= 32 else 0 for b in _kodiere(text)) * groesse / 1000


class _Standard:
    """Die PDF-Standardschriften Helvetica, Helvetica-Bold und Helvetica-Oblique (WinAnsi)."""

    def breite(self, text: str, schrift: str, groesse: float) -> float:
        return breite(text, schrift, groesse)

    def zeichenkette(self, text: str, schrift: str) -> bytes:
        return _zeichenkette(_kodiere(text))

    def objekte(self, erste_nummer: int) -> tuple[list[bytes], dict[str, int]]:
        objekte = [b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>" % name.encode()
                   for name in ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique")]
        return objekte, {NORMAL: erste_nummer, FETT: erste_nummer + 1, KURSIV: erste_nummer + 2}


class _Eingebettet:
    """Liberation Sans, eingebettet als Teilmenge; für Zeichen außerhalb von WinAnsi."""

    def __init__(self) -> None:
        self.schriften = {NORMAL: schrift.Satzschrift(schrift.TrueType.laden("normal")),
                          FETT: schrift.Satzschrift(schrift.TrueType.laden("fett")),
                          KURSIV: schrift.Satzschrift(schrift.TrueType.laden("kursiv"))}

    @staticmethod
    def _text(text: str) -> str:
        return re.sub(r"[\x00-\x1f]", " ", text.translate(_ERSATZ))

    def breite(self, text: str, schrift_: str, groesse: float) -> float:
        return self.schriften[schrift_].breite(self._text(text)) * groesse / 1000

    def zeichenkette(self, text: str, schrift_: str) -> bytes:
        return self.schriften[schrift_].zeichenkette(self._text(text))

    def objekte(self, erste_nummer: int) -> tuple[list[bytes], dict[str, int]]:
        objekte: list[bytes] = []
        nummern = {}
        for name, s in self.schriften.items():
            nummern[name] = erste_nummer + len(objekte)
            objekte += s.objekte(nummern[name])
        return objekte, nummern


def _schriften(bericht: Bericht) -> _Standard | _Eingebettet:
    """Die eingebettete Schrift (PDF/A und PDF/UA verlangen eingebettete Schriften); nur wenn ihre Dateien fehlen,
    die Standardschriften."""
    return _Eingebettet() if schrift.verfuegbar() else _Standard()


@dataclass
class Lauf:
    text: str
    schrift: str = NORMAL
    groesse: float = 10.0
    farbe: str = SCHWARZ


def _zeichenkette(roh: bytes) -> bytes:
    roh = re.sub(rb"[\x00-\x1f]", b" ", roh)
    return b"(" + roh.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


class Satz:
    """Setzt Absätze untereinander und beginnt bei Bedarf eine neue Seite."""

    def __init__(self, schriften: _Standard | _Eingebettet | None = None) -> None:
        self.schriften = schriften or _Standard()
        self.seiten: list[list[bytes]] = []
        # Struktur für Bildschirmleser (Tagged PDF, PDF/UA-Grundlagen): je Seite die Elemente ihrer MCIDs in
        # Reihenfolge, und je Strukturelement (Absatz, Überschrift) Rolle und seine (Seite, MCID).
        self.mcids: list[list[int]] = []
        self.elemente: list[tuple[str, list[tuple[int, int]]]] = []
        self.y = 0.0
        self.neue_seite()

    def neue_seite(self) -> None:
        self.seiten.append([])
        self.mcids.append([])
        self.y = HOEHE - OBEN

    def platz(self, hoehe: float) -> None:
        if self.y - hoehe < UNTEN and self.y < HOEHE - OBEN - 1:
            self.neue_seite()

    def breite(self, text: str, schrift_: str, groesse: float) -> float:
        return self.schriften.breite(text, schrift_, groesse)

    def _zeilen(self, laeufe: list[Lauf], weite: float) -> list[list[tuple[Lauf, str]]]:
        """Umbruch an Leerzeichen; ein Wort, das allein zu breit ist, wird an Zeichen geteilt."""
        zeilen: list[list[tuple[Lauf, str]]] = [[]]
        x = 0.0
        leer: tuple[Lauf, float] | None = None
        for lauf in laeufe:
            for stueck in re.findall(r"\S+|\s+", lauf.text):
                if stueck.isspace():
                    if zeilen[-1]:
                        leer = (lauf, self.breite(" ", lauf.schrift, lauf.groesse))
                    continue
                w = self.breite(stueck, lauf.schrift, lauf.groesse)
                abstand = leer[1] if leer else 0.0
                if zeilen[-1] and x + abstand + w > weite:
                    zeilen.append([])
                    x, leer, abstand = 0.0, None, 0.0
                while w > weite and len(stueck) > 1:
                    n = len(stueck)
                    while n > 1 and self.breite(stueck[:n], lauf.schrift, lauf.groesse) > weite - x:
                        n -= 1
                    zeilen[-1].append((lauf, stueck[:n]))
                    zeilen.append([])
                    stueck, x = stueck[n:], 0.0
                    w = self.breite(stueck, lauf.schrift, lauf.groesse)
                if leer and zeilen[-1]:
                    zeilen[-1].append((leer[0], " "))
                    x += leer[1]
                zeilen[-1].append((lauf, stueck))
                x += w
                leer = None
        return [z for z in zeilen if z]

    def absatz(self, laeufe: list[Lauf], einzug: float = 0.0, vor: float = 0.0, nach: float = 3.0,
               zusammen: float = 0.0, vorne: Lauf | None = None, vorne_x: float = 0.0, rolle: str = "P") -> None:
        """Ein Absatz, alle Zeilen um ``einzug`` eingerückt; ``vorne`` (Bezeichnung, Spiegelstrich, Nummer) steht in
        der ersten Zeile bei ``vorne_x``. ``zusammen`` hält so viel Folgendes mit dem Anfang auf einer Seite."""
        groesse = max(lauf.groesse for lauf in laeufe)
        zeilenhoehe = groesse * 1.32
        zeilen = self._zeilen(laeufe, SATZ - einzug)
        if not zeilen:
            return
        self.y -= vor
        self.platz(zeilenhoehe * min(len(zeilen), 2) + zusammen)
        element = len(self.elemente)
        self.elemente.append((rolle, []))
        for i, zeile in enumerate(zeilen):
            self.platz(zeilenhoehe)
            self.y -= groesse
            # Jede Zeile ist ein markierter Inhalt des Absatzes; so darf ein Absatz über eine Seite laufen.
            seite = len(self.seiten) - 1
            mcid = len(self.mcids[seite])
            self.mcids[seite].append(element)
            self.elemente[element][1].append((seite, mcid))
            self.seiten[-1].append(b"/%s <</MCID %d>> BDC" % (rolle.encode(), mcid))
            x = LINKS + einzug
            if vorne and i == 0:
                zeile = [(vorne, vorne.text, LINKS + vorne_x), *((lauf, text, None) for lauf, text in zeile)]
            else:
                zeile = [(lauf, text, None) for lauf, text in zeile]
            for lauf, text, an in zeile:
                if an is not None:
                    self.seiten[-1].append(self._text(lauf, text, an))
                    continue
                self.seiten[-1].append(self._text(lauf, text, x))
                x += self.breite(text, lauf.schrift, lauf.groesse)
            self.seiten[-1].append(b"EMC")
            self.y -= zeilenhoehe - groesse
        self.y -= nach

    def _text(self, lauf: Lauf, text: str, x: float) -> bytes:
        return b"BT /%s %.1f Tf %s rg %.2f %.2f Td %s Tj ET" % (
            lauf.schrift.encode(), lauf.groesse, lauf.farbe.encode(), x, self.y,
            self.schriften.zeichenkette(text, lauf.schrift))

    def linie(self) -> None:
        # Schmuck, kein Inhalt: Bildschirmleser übergehen ihn.
        self.seiten[-1].append(b"/Artifact BMC 0.6 0.6 0.6 RG 0.5 w %.2f %.2f m %.2f %.2f l S EMC" % (
            LINKS, self.y + 2, BREITE - RECHTS, self.y + 2))
        self.y -= 4


def nummernspalte(bericht: Bericht) -> float:
    """Breite der Nummernspalte für kompakte Einträge (Datum, Uhrzeit), im ganzen Bericht gleich, damit Titel und
    Zeilen untereinander stehen; 0, wenn kein kompakter Eintrag eine Nummer hat."""
    breiten = [breite(b.nummer, FETT, 10) for b in bericht.bausteine if isinstance(b, Eintrag) and b.kompakt
               and b.nummer]
    return min(130.0, max(breiten) + 10) if breiten else 0.0


def _setze(bericht: Bericht) -> Satz:
    s = Satz(_schriften(bericht))
    nr_spalte = nummernspalte(bericht)
    s.absatz([Lauf(bericht.titel, FETT, 16)], nach=8, rolle="H1")
    for b in bericht.bausteine:
        if isinstance(b, Kopf):
            spalte = min(130.0, max((s.breite(k, FETT, 9.5) for k, _ in b.zeilen), default=0.0) + 14)
            for k, v in b.zeilen:
                s.absatz([Lauf(v, NORMAL, 9.5)], einzug=spalte, nach=1.5, vorne=Lauf(k, FETT, 9.5))
            s.y -= 6
        elif isinstance(b, Ueberschrift):
            if b.ebene == 1:
                s.absatz([Lauf(b.text, FETT, 13)], vor=12, nach=2, zusammen=40, rolle="H2")
                s.linie()
            else:
                s.absatz([Lauf(b.text, FETT, 11.5)], vor=8, nach=3, zusammen=30, rolle="H3")
        elif isinstance(b, Absatz):
            if b.leise:
                s.absatz([Lauf(b.text, NORMAL, 8.5, GRAU)], nach=4)
            else:
                s.absatz([Lauf(b.text, NORMAL, 10)], nach=4)
        elif isinstance(b, Eintrag):
            _eintrag(s, b, nr_spalte)
    return s


def _eintrag(s: Satz, e: Eintrag, nummernspalte: float = 0.0) -> None:
    farbe = ROT if e.dringend else GRAU
    marken = [Lauf(f"  [{', '.join(e.marken)}]", FETT if e.dringend else NORMAL, 8.5, farbe)] if e.marken else []
    if e.kompakt:
        nummer = Lauf(e.nummer, FETT, 10) if e.nummer else None
        einzug = nummernspalte or (max(s.breite(e.nummer, FETT, 10) + 5, 18.0) if e.nummer else 0.0)
        titel = Lauf(e.titel, FETT, 10, ROT) if e.dringend else Lauf(e.titel, NORMAL, 10)
        s.absatz([titel, *marken], einzug=einzug, vor=2, nach=1.5, zusammen=24, vorne=nummer)
        if nummernspalte:
            einzug -= 8  # Zeilen stehen bündig unter dem Titel
    else:
        nummer = [Lauf(f"{e.nummer} ", FETT, 10.5)] if e.nummer else []
        einzug = 0.0
        s.absatz([*nummer, Lauf(e.titel, FETT, 10.5), *marken], vor=6, nach=2, zusammen=24)
    for z in e.zeilen:
        s.absatz([Lauf(z, NORMAL, 9.5)], einzug=einzug + 8, nach=1.5)
    for b in e.belege:
        laeufe = [Lauf(f"{b.vorab} – ", NORMAL, 9)] if b.vorab else []
        laeufe.append(Lauf(b.ort, FETT, 9))
        if b.angenaehert:
            laeufe.append(Lauf(" (Zitat angenähert)", NORMAL, 8.5, GRAU))
        if b.zitat:
            laeufe += [Lauf(": ", NORMAL, 9), Lauf(f"„{b.zitat}“", KURSIV, 9)]
        s.absatz(laeufe, einzug=einzug + 20, nach=1.5, vorne=Lauf("–", NORMAL, 9), vorne_x=einzug + 10)
    s.y -= 3


def schreiben(bericht: Bericht) -> bytes:
    satz = _setze(bericht)
    # Leere Seiten fallen weg; ihre Struktur-Nummern rücken entsprechend auf.
    behalten = [i for i, s in enumerate(satz.seiten) if s] or [0]
    neu_index = {alt: neu for neu, alt in enumerate(behalten)}
    seiten = [satz.seiten[i] if i < len(satz.seiten) else [] for i in behalten]
    gesamt = len(seiten)

    inhalte = []
    for nr, befehle in enumerate(seiten, start=1):
        titel = bericht.titel
        fuss = f"{titel} · Seite {nr} von {gesamt}"
        while satz.breite(fuss, NORMAL, 8) > SATZ and len(titel) > 10:
            titel = titel[:-2]
            fuss = f"{titel} … · Seite {nr} von {gesamt}"
        befehle = [*befehle, b"/Artifact <</Type /Pagination /Subtype /Footer>> BDC "
                   b"BT /F1 8 Tf %s rg %.2f %.2f Td %s Tj ET EMC" % (
                       GRAU.encode(), LINKS, UNTEN - 30, satz.schriften.zeichenkette(fuss, NORMAL))]
        inhalte.append(zlib.compress(b"\n".join(befehle)))

    # Schriften erst jetzt: Eine eingebettete Teilmenge braucht alle Zeichen, auch die der Fußzeilen.
    objekte: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R /Lang (de-DE) >>", b""]
    schrift_objekte, nummern = satz.schriften.objekte(len(objekte) + 1)
    objekte += schrift_objekte
    ressourcen = b"<< /Font << /F1 %d 0 R /F2 %d 0 R /F3 %d 0 R >> >>" % (nummern[NORMAL], nummern[FETT],
                                                                         nummern[KURSIV])
    kinder = []
    seiten_nr: list[int] = []
    for i, inhalt in enumerate(inhalte):
        objekte.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(inhalt) + inhalt + b"\nendstream")
        # /Tabs /S: Tabulatorreihenfolge folgt der Struktur; /StructParents verbindet die Seite mit dem ParentTree.
        objekte.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Resources %s /Contents %d 0 R "
                       b"/StructParents %d /Tabs /S >>" % (BREITE, HOEHE, ressourcen, len(objekte), i))
        kinder.append(b"%d 0 R" % len(objekte))
        seiten_nr.append(len(objekte))
    objekte[1] = b"<< /Type /Pages /Kids [" + b" ".join(kinder) + b"] /Count %d >>" % gesamt

    # Strukturbaum: StructTreeRoot → Document → je Absatz/Überschrift ein Element mit seinen markierten Inhalten.
    wurzel = len(objekte) + 1
    dokument = wurzel + 1
    eltern = wurzel + 2
    erstes = wurzel + 3
    element_nr = {}
    teile = []
    for e, (rolle, stellen) in enumerate(satz.elemente):
        mcr = [(neu_index[seite], mcid) for seite, mcid in stellen if seite in neu_index]
        if not mcr:
            continue
        element_nr[e] = erstes + len(teile)
        teile.append(b"<< /Type /StructElem /S /%s /P %d 0 R /K [%s] >>" % (
            rolle.encode(), dokument,
            b" ".join(b"<< /Type /MCR /Pg %d 0 R /MCID %d >>" % (seiten_nr[s], m) for s, m in mcr)))
    objekte.append(b"<< /Type /StructTreeRoot /K %d 0 R /ParentTree %d 0 R /ParentTreeNextKey %d >>" % (
        dokument, eltern, gesamt))
    objekte.append(b"<< /Type /StructElem /S /Document /P %d 0 R /K [%s] >>" % (
        wurzel, b" ".join(b"%d 0 R" % n for n in element_nr.values())))
    nums = []
    for neu, alt in enumerate(behalten):
        liste = satz.mcids[alt] if alt < len(satz.mcids) else []
        nums.append(b"%d [%s]" % (neu, b" ".join(b"%d 0 R" % element_nr[e] for e in liste)))
    objekte.append(b"<< /Nums [" + b" ".join(nums) + b"] >>")
    objekte += teile
    titel = "".join(c if ord(c) < 0x10000 else "?" for c in bericht.titel)
    normen = b""
    if isinstance(satz.schriften, _Eingebettet):
        objekte.append(_strom_roh(_xmp(titel), b"/Type /Metadata /Subtype /XML"))
        metadaten = len(objekte)
        icc = zlib.compress(farbprofil.srgb())
        objekte.append(b"<< /N 3 /Length %d /Filter /FlateDecode >>\nstream\n" % len(icc) + icc + b"\nendstream")
        objekte.append(b"<< /Type /OutputIntent /S /GTS_PDFA1 /OutputConditionIdentifier (%s) /Info (%s) "
                       b"/DestOutputProfile %d 0 R >>" % (farbprofil.BESCHREIBUNG.encode(),
                                                          farbprofil.BESCHREIBUNG.encode(), len(objekte)))
        normen = b"/Metadata %d 0 R /OutputIntents [%d 0 R] " % (metadaten, len(objekte))
    objekte[0] = (b"<< /Type /Catalog /Pages 2 0 R /Lang (de-DE) /MarkInfo << /Marked true >> /StructTreeRoot %d 0 R "
                  b"%s/ViewerPreferences << /DisplayDocTitle true >> >>" % (wurzel, normen))
    objekte.append(b"<< /Title <FEFF%s> /Creator (advOrdo) /Producer (advOrdo) >>" % titel.encode("utf-16-be").hex()
                   .upper().encode())
    info = len(objekte)

    daten = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
    versaetze = []
    for i, obj in enumerate(objekte, start=1):
        versaetze.append(len(daten))
        daten += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(daten)
    daten += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekte) + 1)
    daten += b"".join(b"%010d 00000 n \n" % v for v in versaetze)
    # Dateikennung (ISO 32000-1, 14.4), aus dem Inhalt abgeleitet: gleiche Berichte ergeben gleiche Dateien.
    kennung = hashlib.md5(daten).hexdigest().upper().encode()
    daten += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R /ID [<%s> <%s>] >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objekte) + 1, info, kennung, kennung, xref)
    return daten


def _strom_roh(inhalt: bytes, schluessel: bytes) -> bytes:
    """Ungepackter Datenstrom; XMP-Metadaten sollen auch ohne PDF-Programm lesbar bleiben."""
    return b"<< %s /Length %d >>\nstream\n" % (schluessel, len(inhalt)) + inhalt + b"\nendstream"


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _xmp(titel: str) -> bytes:
    """XMP-Metadaten: Titel, Programm und die Kennungen für PDF/A-2a und PDF/UA-1. Die Eigenschaft ``pdfuaid:part``
    gehört nicht zu den in PDF/A-2 vordefinierten und wird deshalb als Erweiterungsschema beschrieben (6.6.2.3)."""
    return f"""<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:pdf="http://ns.adobe.com/pdf/1.3/"
 xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"
 xmlns:pdfuaid="http://www.aiim.org/pdfua/ns/id/">
<dc:title><rdf:Alt><rdf:li xml:lang="x-default">{_xml(titel)}</rdf:li></rdf:Alt></dc:title>
<dc:format>application/pdf</dc:format>
<dc:language><rdf:Bag><rdf:li>de-DE</rdf:li></rdf:Bag></dc:language>
<xmp:CreatorTool>advOrdo</xmp:CreatorTool>
<pdf:Producer>advOrdo</pdf:Producer>
<pdfaid:part>2</pdfaid:part>
<pdfaid:conformance>A</pdfaid:conformance>
<pdfuaid:part>1</pdfuaid:part>
</rdf:Description>
<rdf:Description rdf:about="" xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/"
 xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#" xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#">
<pdfaExtension:schemas><rdf:Bag><rdf:li rdf:parseType="Resource">
<pdfaSchema:schema>PDF/UA Universal Accessibility Schema</pdfaSchema:schema>
<pdfaSchema:namespaceURI>http://www.aiim.org/pdfua/ns/id/</pdfaSchema:namespaceURI>
<pdfaSchema:prefix>pdfuaid</pdfaSchema:prefix>
<pdfaSchema:property><rdf:Seq><rdf:li rdf:parseType="Resource">
<pdfaProperty:name>part</pdfaProperty:name>
<pdfaProperty:valueType>Integer</pdfaProperty:valueType>
<pdfaProperty:category>internal</pdfaProperty:category>
<pdfaProperty:description>Teil von ISO 14289, dem die Datei folgt</pdfaProperty:description>
</rdf:li></rdf:Seq></pdfaSchema:property>
</rdf:li></rdf:Bag></pdfaExtension:schemas>
</rdf:Description>
</rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>""".encode()
