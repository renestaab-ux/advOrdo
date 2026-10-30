"""Bericht als PDF, ohne Zusatzbibliothek.

Gesetzt wird in den PDF-Standardschriften Helvetica, Helvetica-Bold und Helvetica-Oblique, die jeder PDF-Betrachter
mitbringt; es wird keine Schrift eingebettet. Die Kodierung ist WinAnsi (cp1252): Umlaute, ß, §, „ “, – und €
sind enthalten. Zeichen außerhalb davon werden ersetzt (z. B. „→“ durch „->“), sonst durch „?“. Zeilen werden mit
den echten Zeichenbreiten umbrochen. Format A4, Fußzeile mit Titel und „Seite n von m“.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass

from . import Absatz, Bericht, Eintrag, Kopf, Ueberschrift, _helvetica

BREITE, HOEHE = 595.28, 841.89
LINKS, RECHTS, OBEN, UNTEN = 62.0, 62.0, 60.0, 64.0
SATZ = BREITE - LINKS - RECHTS

NORMAL, FETT, KURSIV = "F1", "F2", "F3"
_BREITEN = {NORMAL: _helvetica.NORMAL, FETT: _helvetica.FETT, KURSIV: _helvetica.NORMAL}
SCHWARZ, GRAU, ROT = "0 0 0", "0.35 0.35 0.35", "0.7 0.1 0.1"

_ERSATZ = str.maketrans({
    "→": "->", "←": "<-", "≤": "<=", "≥": ">=", "≠": "!=", "−": "-", "‑": "-", "‐": "-", " ": " ",
    " ": " ", "​": "", "\t": " ", "✓": "x", "•": "•", "­": "",
})


def _kodiere(text: str) -> bytes:
    text = text.translate(_ERSATZ)
    return text.encode("cp1252", errors="replace")


def breite(text: str, schrift: str, groesse: float) -> float:
    tabelle = _BREITEN[schrift]
    return sum(tabelle[b - 32] if b >= 32 else 0 for b in _kodiere(text)) * groesse / 1000


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

    def __init__(self) -> None:
        self.seiten: list[list[bytes]] = []
        self.y = 0.0
        self.neue_seite()

    def neue_seite(self) -> None:
        self.seiten.append([])
        self.y = HOEHE - OBEN

    def platz(self, hoehe: float) -> None:
        if self.y - hoehe < UNTEN and self.y < HOEHE - OBEN - 1:
            self.neue_seite()

    def _zeilen(self, laeufe: list[Lauf], weite: float) -> list[list[tuple[Lauf, str]]]:
        """Umbruch an Leerzeichen; ein Wort, das allein zu breit ist, wird an Zeichen geteilt."""
        zeilen: list[list[tuple[Lauf, str]]] = [[]]
        x = 0.0
        leer: tuple[Lauf, float] | None = None
        for lauf in laeufe:
            for stueck in re.findall(r"\S+|\s+", lauf.text):
                if stueck.isspace():
                    if zeilen[-1]:
                        leer = (lauf, breite(" ", lauf.schrift, lauf.groesse))
                    continue
                w = breite(stueck, lauf.schrift, lauf.groesse)
                abstand = leer[1] if leer else 0.0
                if zeilen[-1] and x + abstand + w > weite:
                    zeilen.append([])
                    x, leer, abstand = 0.0, None, 0.0
                while w > weite and len(stueck) > 1:
                    n = len(stueck)
                    while n > 1 and breite(stueck[:n], lauf.schrift, lauf.groesse) > weite - x:
                        n -= 1
                    zeilen[-1].append((lauf, stueck[:n]))
                    zeilen.append([])
                    stueck, x = stueck[n:], 0.0
                    w = breite(stueck, lauf.schrift, lauf.groesse)
                if leer and zeilen[-1]:
                    zeilen[-1].append((leer[0], " "))
                    x += leer[1]
                zeilen[-1].append((lauf, stueck))
                x += w
                leer = None
        return [z for z in zeilen if z]

    def absatz(self, laeufe: list[Lauf], einzug: float = 0.0, vor: float = 0.0, nach: float = 3.0,
               zusammen: float = 0.0, vorne: Lauf | None = None, vorne_x: float = 0.0) -> None:
        """Ein Absatz, alle Zeilen um ``einzug`` eingerückt; ``vorne`` (Bezeichnung, Spiegelstrich, Nummer) steht in
        der ersten Zeile bei ``vorne_x``. ``zusammen`` hält so viel Folgendes mit dem Anfang auf einer Seite."""
        groesse = max(lauf.groesse for lauf in laeufe)
        zeilenhoehe = groesse * 1.32
        zeilen = self._zeilen(laeufe, SATZ - einzug)
        if not zeilen:
            return
        self.y -= vor
        self.platz(zeilenhoehe * min(len(zeilen), 2) + zusammen)
        for i, zeile in enumerate(zeilen):
            self.platz(zeilenhoehe)
            self.y -= groesse
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
                x += breite(text, lauf.schrift, lauf.groesse)
            self.y -= zeilenhoehe - groesse
        self.y -= nach

    def _text(self, lauf: Lauf, text: str, x: float) -> bytes:
        return b"BT /%s %.1f Tf %s rg %.2f %.2f Td %s Tj ET" % (
            lauf.schrift.encode(), lauf.groesse, lauf.farbe.encode(), x, self.y, _zeichenkette(_kodiere(text)))

    def linie(self) -> None:
        self.seiten[-1].append(b"0.6 0.6 0.6 RG 0.5 w %.2f %.2f m %.2f %.2f l S" % (
            LINKS, self.y + 2, BREITE - RECHTS, self.y + 2))
        self.y -= 4


def nummernspalte(bericht: Bericht) -> float:
    """Breite der Nummernspalte für kompakte Einträge (Datum, Uhrzeit), im ganzen Bericht gleich, damit Titel und
    Zeilen untereinander stehen; 0, wenn kein kompakter Eintrag eine Nummer hat."""
    breiten = [breite(b.nummer, FETT, 10) for b in bericht.bausteine if isinstance(b, Eintrag) and b.kompakt
               and b.nummer]
    return min(130.0, max(breiten) + 10) if breiten else 0.0


def _setze(bericht: Bericht) -> Satz:
    s = Satz()
    nr_spalte = nummernspalte(bericht)
    s.absatz([Lauf(bericht.titel, FETT, 16)], nach=8)
    for b in bericht.bausteine:
        if isinstance(b, Kopf):
            spalte = min(130.0, max((breite(k, FETT, 9.5) for k, _ in b.zeilen), default=0.0) + 14)
            for k, v in b.zeilen:
                s.absatz([Lauf(v, NORMAL, 9.5)], einzug=spalte, nach=1.5, vorne=Lauf(k, FETT, 9.5))
            s.y -= 6
        elif isinstance(b, Ueberschrift):
            if b.ebene == 1:
                s.absatz([Lauf(b.text, FETT, 13)], vor=12, nach=2, zusammen=40)
                s.linie()
            else:
                s.absatz([Lauf(b.text, FETT, 11.5)], vor=8, nach=3, zusammen=30)
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
        einzug = nummernspalte or (max(breite(e.nummer, FETT, 10) + 5, 18.0) if e.nummer else 0.0)
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
    seiten = [s for s in satz.seiten if s] or [[]]
    gesamt = len(seiten)

    objekte: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R /Lang (de-DE) >>", b""]
    schriften = []
    for name in ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique"):
        objekte.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>" % name.encode())
        schriften.append(len(objekte))
    ressourcen = b"<< /Font << /F1 %d 0 R /F2 %d 0 R /F3 %d 0 R >> >>" % tuple(schriften)
    kinder = []
    for nr, befehle in enumerate(seiten, start=1):
        titel = bericht.titel
        fuss = f"{titel} · Seite {nr} von {gesamt}"
        while breite(fuss, NORMAL, 8) > SATZ and len(titel) > 10:
            titel = titel[:-2]
            fuss = f"{titel} … · Seite {nr} von {gesamt}"
        befehle = [*befehle, b"BT /F1 8 Tf %s rg %.2f %.2f Td %s Tj ET" % (
            GRAU.encode(), LINKS, UNTEN - 30, _zeichenkette(_kodiere(fuss)))]
        inhalt = zlib.compress(b"\n".join(befehle))
        objekte.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(inhalt) + inhalt + b"\nendstream")
        objekte.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Resources %s /Contents %d 0 R >>" % (
            BREITE, HOEHE, ressourcen, len(objekte)))
        kinder.append(b"%d 0 R" % len(objekte))
    objekte[1] = b"<< /Type /Pages /Kids [" + b" ".join(kinder) + b"] /Count %d >>" % gesamt
    titel = "".join(c if ord(c) < 0x10000 else "?" for c in bericht.titel)
    objekte.append(b"<< /Title <FEFF%s> /Creator (JuraBox) /Producer (JuraBox) >>" % titel.encode("utf-16-be").hex()
                   .upper().encode())
    info = len(objekte)

    daten = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    versaetze = []
    for i, obj in enumerate(objekte, start=1):
        versaetze.append(len(daten))
        daten += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(daten)
    daten += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekte) + 1)
    daten += b"".join(b"%010d 00000 n \n" % v for v in versaetze)
    daten += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objekte) + 1, info, xref)
    return daten
