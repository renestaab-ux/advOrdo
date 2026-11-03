"""Erzeugte PDFs sind getaggt (EN 301 549 Kap. 10, PDF/UA-Grundlagen): Sprache, Titel, Strukturbaum mit
Überschriften und Absätzen, Schmuck und Fußzeile als Artefakt."""

from __future__ import annotations

import ctypes
import re
import zlib

import pypdfium2 as pdfium
import pypdfium2.raw as roh

from juracore.ausgabe import Absatz, Bericht, Eintrag, Ueberschrift, pdf


def _bericht(absaetze: int = 3) -> Bericht:
    b = Bericht(titel="Widersprüche · Testakte")
    b.bausteine.append(Ueberschrift("Ergebnis"))
    for i in range(absaetze):
        b.bausteine.append(Absatz(f"Absatz {i}: " + "Der Kläger trägt vor, das Fahrzeug sei mangelhaft. " * 6))
    b.bausteine.append(Eintrag(titel="Datum der Übergabe", zeilen=["14.03.2025 laut Kaufvertrag"]))
    return b


def _rollen(datei: bytes) -> list[list[str]]:
    """Rollen der obersten Strukturelemente je Seite, gelesen mit PDFium (wie es ein Bildschirmleser sähe)."""
    dok = pdfium.PdfDocument(datei)
    alle = []
    for i in range(len(dok)):
        seite = dok[i]  # festhalten, sonst schließt PDFium die Seite unter dem Strukturbaum
        baum = roh.FPDF_StructTree_GetForPage(seite.raw)
        rollen = []
        for k in range(roh.FPDF_StructTree_CountChildren(baum)):
            el = roh.FPDF_StructTree_GetChildAtIndex(baum, k)
            puffer = ctypes.create_string_buffer(64)
            n = roh.FPDF_StructElement_GetType(el, puffer, 64)
            rollen.append(puffer.raw[: n].decode("utf-16-le").rstrip("\x00"))
        roh.FPDF_StructTree_Close(baum)
        seite.close()
        alle.append(rollen)
    return alle


def test_pdf_ist_getaggt_mit_sprache_und_titel():
    datei = pdf.schreiben(_bericht())
    assert datei.startswith(b"%PDF-1.7")
    assert b"/MarkInfo << /Marked true >>" in datei
    assert b"/Lang (de-DE)" in datei
    assert b"/DisplayDocTitle true" in datei
    assert b"/StructTreeRoot" in datei
    rollen = _rollen(datei)
    assert rollen[0] == ["Document"]


def test_ueberschriften_absaetze_und_artefakte():
    datei = pdf.schreiben(_bericht())
    assert re.findall(rb"/S /(H1|H2|H3|P) ", datei)[:2] == [b"H1", b"H2"]
    inhalt = b""
    for strom in re.findall(rb"stream\n(.*?)\nendstream", datei, re.S):
        try:
            inhalt += zlib.decompress(strom)
        except zlib.error:
            pass  # eingebettete Schrift
    # Jede markierte Zeile ist geschlossen; Linie und Fußzeile sind Artefakte.
    assert inhalt.count(b" BDC") + inhalt.count(b"/Artifact BMC") == inhalt.count(b"EMC")
    assert b"/Artifact <</Type /Pagination" in inhalt


def test_absatz_ueber_mehrere_seiten_bleibt_ein_element():
    datei = pdf.schreiben(_bericht(absaetze=60))
    dok = pdfium.PdfDocument(datei)
    assert len(dok) >= 2
    assert all(r == ["Document"] for r in _rollen(datei))
    # Ein Element mit Inhalten auf zwei Seiten verweist auf zwei verschiedene /Pg.
    zweiseitig = [e for e in re.findall(rb"/S /P /P \d+ 0 R /K \[(.*?)\] >>", datei)
                  if len(set(re.findall(rb"/Pg (\d+) 0 R", e))) > 1]
    assert zweiseitig
