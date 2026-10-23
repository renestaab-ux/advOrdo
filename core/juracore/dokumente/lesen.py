"""Liest PDF, DOCX, TXT und Markdown in ein ``Dokument``.

- PDF: Text aus der Textebene (PDFium). Seiten ohne Text werden als Bild
  gerendert und per Tesseract erkannt, sofern verfügbar.
- DOCX: Absätze, Tabellen und Fußnoten direkt aus dem Word-XML. Seitenzahlen
  gibt es nur, wenn die Datei Seitenumbrüche enthält; sonst gelten Randnummern
  bzw. Absatznummern als Fundstelle.
- TXT/Markdown: Absätze sind durch Leerzeilen getrennt.
"""

from __future__ import annotations

import logging
import re
import zipfile
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree as ET

from .aufbereitung import abschnitte_bilden
from .modell import DATEI, LEER, OCR, TEXTEBENE, Abschnitt, Dokument, Seite
from .ocr import OcrNichtVerfuegbar, Tesseract

log = logging.getLogger("juracore.dokumente")

FORMATE = {".pdf": "pdf", ".docx": "docx", ".txt": "txt", ".md": "md", ".markdown": "md"}
OCR_DPI = 300
_MIN_TEXT = 25  # weniger Zeichen auf einer PDF-Seite: als Bildseite behandeln

Fortschritt = Callable[[str], None]


def format_von(pfad: Path) -> str:
    fmt = FORMATE.get(pfad.suffix.lower())
    if fmt is None:
        raise ValueError(f"Dateiformat {pfad.suffix or '(ohne Endung)'} wird nicht unterstützt (PDF, DOCX, TXT, MD).")
    return fmt


def lies(pfad: Path, ocr: Tesseract | None | bool = True) -> Dokument:
    """Liest eine Datei. ``ocr=True`` sucht Tesseract bei Bedarf, ``False``/``None`` liest ohne OCR."""
    pfad = Path(pfad)
    fmt = format_von(pfad)
    if fmt == "pdf":
        return _lies_pdf(pfad, ocr)
    if fmt == "docx":
        return _lies_docx(pfad)
    return _lies_text(pfad, fmt)


# --- PDF -----------------------------------------------------------------------------------------


def _lies_pdf(pfad: Path, ocr: Tesseract | None | bool) -> Dokument:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(pfad)
    except pdfium.PdfiumError as fehler:
        if "password" in str(fehler).lower():
            raise ValueError(f"{pfad.name} ist passwortgeschützt und kann nicht gelesen werden.") from fehler
        raise ValueError(f"{pfad.name} ist kein lesbares PDF: {fehler}") from fehler

    seiten: list[Seite] = []
    hinweise: list[str] = []
    tesseract: Tesseract | None = ocr if isinstance(ocr, Tesseract) else None
    ocr_fehler: str | None = None
    try:
        for i in range(len(pdf)):
            seite = pdf[i]
            text = seite.get_textpage().get_text_bounded()
            if len(text.strip()) >= _MIN_TEXT:
                # PDFium ersetzt den Bindestrich am Zeilenende durch "\x02" und hängt die Folgezeile an.
                # Ob es eine Silbentrennung ("Kilome-terstand") oder ein echter Bindestrich ("Kfz-Technik")
                # ist, entscheidet die Aufbereitung; hier nur die Zeilen wiederherstellen.
                zeilen = text.replace("\r\n", "\n").replace("\x02", "-\n").split("\n")
                seiten.append(Seite(i + 1, TEXTEBENE, zeilen))
                continue
            # Bildseite: Texterkennung.
            if tesseract is None and ocr is True and ocr_fehler is None:
                try:
                    tesseract = Tesseract.finden()
                    tesseract.pruefe_sprache()
                except OcrNichtVerfuegbar as fehler:
                    tesseract, ocr_fehler = None, str(fehler)
            if tesseract is None:
                seiten.append(Seite(i + 1, LEER, []))
                continue
            try:
                zeilen, konfidenz, woerter = tesseract.erkenne_mit_woertern(_seitenbild(seite))
            except OcrNichtVerfuegbar as fehler:
                # Eine fehlgeschlagene Seite soll die übrigen nicht aufhalten.
                log.warning("OCR Seite %s von %s: %s", i + 1, pfad.name, fehler)
                ocr_fehler = str(fehler)
                seiten.append(Seite(i + 1, LEER, []))
                continue
            seiten.append(Seite(i + 1, OCR, list(zeilen), konfidenz, woerter))
    finally:
        pdf.close()

    leer = [s.nr for s in seiten if s.quelle == LEER]
    if leer:
        grund = ocr_fehler or "Texterkennung ist ausgeschaltet."
        hinweise.append(f"Seite(n) {_bereich(leer)} ohne Text: {grund}")
    if any(s.quelle == OCR for s in seiten):
        hinweise.append("Text per Texterkennung gelesen; Erkennungsfehler sind möglich. Im Zweifel am Original prüfen.")
    return Dokument("pdf", seiten, abschnitte_bilden(seiten), hinweise)


def _seitenbild(seite) -> bytes:
    """Rendert eine PDF-Seite als Graustufenbild im PGM-Format (ohne Zusatzbibliothek)."""
    bild = seite.render(scale=OCR_DPI / 72, grayscale=True)
    breite, hoehe, schritt = bild.width, bild.height, bild.stride
    puffer = bytes(bild.buffer)
    zeilen = b"".join(puffer[y * schritt : y * schritt + breite] for y in range(hoehe))
    return b"P5\n%d %d\n255\n" % (breite, hoehe) + zeilen


def _bereich(nummern: list[int | None]) -> str:
    return ", ".join(str(n) for n in nummern)


# --- DOCX ----------------------------------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _lies_docx(pfad: Path) -> Dokument:
    try:
        with zipfile.ZipFile(pfad) as z:
            dokument_xml = z.read("word/document.xml")
            fussnoten_xml = z.read("word/footnotes.xml") if "word/footnotes.xml" in z.namelist() else None
    except (zipfile.BadZipFile, KeyError) as fehler:
        raise ValueError(f"{pfad.name} ist keine lesbare Word-Datei (DOCX): {fehler}") from fehler

    koerper = ET.fromstring(dokument_xml).find(f"{_W}body")
    if koerper is None:
        raise ValueError(f"{pfad.name}: Word-Datei ohne Inhalt.")

    # (Seite, Text, Art) je Absatz; Seiten nur über Umbrüche in der Datei.
    absaetze: list[tuple[int, str, str]] = []
    seite = 1
    for element in _bloecke(koerper):
        if element.tag == f"{_W}p":
            if element.find(f"{_W}pPr/{_W}pageBreakBefore") is not None:
                seite += 1
            text, umbrueche = _absatztext(element)
            if text.strip():
                absaetze.append((seite, text, "absatz"))
            seite += umbrueche
        elif element.tag == f"{_W}tbl":
            for zeile in element.iter(f"{_W}tr"):
                zellen = [
                    " ".join(_absatztext(p)[0] for p in zelle.iter(f"{_W}p")).strip()
                    for zelle in zeile.iter(f"{_W}tc")
                ]
                if any(zellen):
                    absaetze.append((seite, " | ".join(zellen), "tabelle"))

    hat_seiten = seite > 1
    seiten = [Seite(None, DATEI, [])]
    abschnitte: list[Abschnitt] = []
    for s, text, art in absaetze:
        for a in abschnitte_bilden([Seite(s if hat_seiten else None, DATEI, [text, None])]):
            a.nr, a.art = len(abschnitte) + 1, art
            abschnitte.append(a)
    if fussnoten_xml:
        for fn in ET.fromstring(fussnoten_xml).iter(f"{_W}footnote"):
            if fn.get(f"{_W}type") in ("separator", "continuationSeparator", "continuationNotice"):
                continue
            text = " ".join(_absatztext(p)[0] for p in fn.iter(f"{_W}p")).strip()
            if text:
                abschnitte.append(Abschnitt(len(abschnitte) + 1, re.sub(r"\s+", " ", text), art="fussnote"))
    seiten[0].zeilen = [a.text for a in abschnitte]
    hinweise = [] if hat_seiten else ["Word-Datei ohne Seitenumbrüche: Fundstellen nach Randnummer bzw. Absatz."]
    return Dokument("docx", seiten, abschnitte, hinweise)


def _bloecke(element: ET.Element):
    """Absätze und Tabellen in Dokumentreihenfolge, auch innerhalb von Inhaltssteuerelementen."""
    for kind in element:
        if kind.tag == f"{_W}sdt":
            inhalt = kind.find(f"{_W}sdtContent")
            if inhalt is not None:
                yield from _bloecke(inhalt)
        else:
            yield kind


def _absatztext(p: ET.Element) -> tuple[str, int]:
    """Text eines Word-Absatzes und Zahl der darin enthaltenen Seitenumbrüche."""
    teile: list[str] = []
    umbrueche = 0
    for e in p.iter():
        if e.tag == f"{_W}t" and e.text:
            teile.append(e.text)
        elif e.tag == f"{_W}tab":
            teile.append("\t")
        elif e.tag == f"{_W}noBreakHyphen":
            teile.append("-")
        elif e.tag == f"{_W}br":
            if e.get(f"{_W}type") == "page":
                umbrueche += 1
            teile.append(" ")
        elif e.tag == f"{_W}lastRenderedPageBreak":
            umbrueche += 1
    return "".join(teile), umbrueche


# --- Text und Markdown ---------------------------------------------------------------------------


def _lies_text(pfad: Path, fmt: str) -> Dokument:
    roh = pfad.read_bytes()
    try:
        text = roh.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = roh.decode("cp1252", "replace")  # ältere Windows-Dateien
    zeilen: list[str | None] = []
    for roh_zeile in text.splitlines():
        if not roh_zeile.strip():
            zeilen.append(None)
            continue
        if fmt != "md":
            zeilen.append(roh_zeile)
            continue
        # Markdown: Überschriften, Tabellenzeilen und Listenpunkte sind eigene Absätze.
        eigener_absatz = re.match(r"^\s*(#|\||[-*]\s|\d+\.\s)", roh_zeile)
        zeile = _markdown_bereinigen(roh_zeile)
        if zeile is None:
            continue
        if eigener_absatz:
            zeilen += [None, zeile, None]
        else:
            zeilen.append(zeile)
    # Ohne Seiten: jede Zeile, die nicht durch eine Leerzeile getrennt ist, gehört zum Absatz.
    seite = Seite(None, DATEI, _absatzweise(zeilen))
    return Dokument(fmt, [seite], abschnitte_bilden([seite]), [])


def _absatzweise(zeilen: list[str | None]) -> list[str | None]:
    """Fasst Zeilen zwischen Leerzeilen zu einer Zeile zusammen, damit nur Leerzeilen Absätze trennen."""
    ergebnis: list[str | None] = []
    aktuell: list[str] = []
    for z in [*zeilen, None]:
        if z is None:
            if aktuell:
                ergebnis += [" ".join(aktuell), None]
                aktuell = []
        else:
            aktuell.append(z.strip())
    return ergebnis


def _markdown_bereinigen(zeile: str) -> str | None:
    s = zeile.strip()
    if re.fullmatch(r"[-|: ]{3,}", s):  # Tabellen-Trennzeile, Linie
        return None
    s = re.sub(r"^#{1,6}\s+", "", s)
    s = re.sub(r"^>\s?", "", s).rstrip("\\")  # "\\" am Zeilenende: harter Umbruch
    s = re.sub(r"(\*\*|__)(.+?)\1", r"\2", s)
    return s.strip("|").strip() or None
