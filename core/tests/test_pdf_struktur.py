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


def test_pdf_a_und_ua_kennung_metadaten_und_farbprofil():
    """PDF/A-2a und PDF/UA-1: XMP mit Titel und Kennungen, Ausgabebedingung mit sRGB-Profil, Dateikennung,
    nur eingebettete Schriften."""
    import xml.etree.ElementTree as ET

    from juracore.ausgabe import farbprofil

    datei = pdf.schreiben(Bericht(titel="Anmerkungen <Test> & Co. · Şahin", bausteine=[Absatz("Text")]))
    xmp = re.search(rb"/Type /Metadata /Subtype /XML /Length (\d+) >>\nstream\n", datei)
    assert xmp
    paket = datei[xmp.end(): xmp.end() + int(xmp.group(1))]
    wurzel = ET.fromstring(paket[paket.index(b"<x:xmpmeta"): paket.index(b"</x:xmpmeta>") + 12])
    ns = {"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "dc": "http://purl.org/dc/elements/1.1/",
          "pdfaid": "http://www.aiim.org/pdfa/ns/id/", "pdfuaid": "http://www.aiim.org/pdfua/ns/id/"}
    assert wurzel.find(".//dc:title/rdf:Alt/rdf:li", ns).text == "Anmerkungen <Test> & Co. · Şahin"
    assert wurzel.find(".//pdfaid:part", ns).text == "2"
    assert wurzel.find(".//pdfaid:conformance", ns).text == "A"
    assert wurzel.find(".//pdfuaid:part", ns).text == "1"
    # Titel im Info-Verzeichnis gleich dem in XMP (PDF/A 6.6.3)
    info = re.search(rb"/Title <FEFF([0-9A-F]+)>", datei).group(1)
    assert bytes.fromhex(info.decode()).decode("utf-16-be") == "Anmerkungen <Test> & Co. · Şahin"
    assert b"/OutputIntents [" in datei and b"/S /GTS_PDFA1" in datei
    assert re.search(rb"/ID \[<[0-9A-F]{32}> <[0-9A-F]{32}>\]", datei)
    assert b"/Helvetica" not in datei and datei.count(b"/FontFile2") == 3
    icc = farbprofil.srgb()
    assert int.from_bytes(icc[:4], "big") == len(icc) and icc[36:40] == b"acsp" and icc[12:24] == b"mntrRGB XYZ "
    # Gleicher Bericht, gleiche Datei (keine Zeitstempel)
    assert pdf.schreiben(Bericht(titel="Anmerkungen <Test> & Co. · Şahin", bausteine=[Absatz("Text")])) == datei


def test_ohne_schriftdateien_keine_normkennung(monkeypatch):
    from juracore.ausgabe import schrift

    monkeypatch.setattr(schrift, "verfuegbar", lambda: False)
    datei = pdf.schreiben(_bericht())
    assert b"/Helvetica" in datei and b"pdfaid" not in datei and b"/OutputIntents" not in datei
