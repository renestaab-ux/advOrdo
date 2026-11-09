import zipfile

import pytest

from juracore.dokumente import akte, lesen, ocr
from juracore.dokumente.modell import LEER, TEXTEBENE

from .conftest import schreibe_pdf

ZEILE = "Die Beklagte lehnte die Nachbesserung ab und berief sich auf den Gewährleistungsausschluss im"


def _docx(pfad, body: str, fussnoten: str | None = None, rahmen: dict[str, str] | None = None):
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("word/document.xml", f"<w:document {ns}><w:body>{body}</w:body></w:document>")
        if fussnoten:
            z.writestr("word/footnotes.xml", f"<w:footnotes {ns}>{fussnoten}</w:footnotes>")
        for name, inhalt in (rahmen or {}).items():
            wurzel = "w:hdr" if name.startswith("header") else "w:ftr"
            z.writestr(f"word/{name}.xml", f"<{wurzel} {ns}>{inhalt}</{wurzel}>")
    return pfad


def _p(text: str, extra: str = "") -> str:
    return f"<w:p>{extra}<w:r><w:t xml:space='preserve'>{text}</w:t></w:r></w:p>"


def test_pdf_mit_textebene(tmp_path):
    pdf = schreibe_pdf(
        tmp_path / "klage.pdf",
        [
            ["Klage", "(1) " + ZEILE, "Kaufvertrag, vgl. §§ 437 Nr. 2, 440 BGB, sowie nach den Grundsätzen des Kfz-", "Handels."],
            ["- 2 -", "(2) Zweite Randnummer mit § 286 Abs. 2 ZPO."],
        ],
    )
    dok = lesen.lies(pdf, ocr=False)
    assert dok.format == "pdf"
    assert dok.lesart == TEXTEBENE
    assert [a.rn for a in dok.abschnitte] == [None, 1, 2]
    assert "Kfz-Handels" in dok.abschnitte[1].text
    assert dok.abschnitte[2].seite == 2
    assert dok.hinweise == []


def test_pdf_bildseite_ohne_ocr_wird_benannt(tmp_path):
    pdf = schreibe_pdf(tmp_path / "scan.pdf", [[ZEILE], []])
    dok = lesen.lies(pdf, ocr=False)
    assert [s.quelle for s in dok.seiten] == [TEXTEBENE, LEER]
    assert dok.hinweise and dok.hinweise[0].startswith("Seite(n) 2 ohne Text")


def test_pdf_passwort_oder_kaputt(tmp_path):
    kaputt = tmp_path / "kaputt.pdf"
    kaputt.write_bytes(b"%PDF-1.4 kein echtes pdf")
    with pytest.raises(ValueError, match="kein lesbares PDF"):
        lesen.lies(kaputt, ocr=False)


def test_docx_absaetze_tabellen_fussnoten(tmp_path):
    body = (
        _p("Kla­ge")
        + _p("(3) Mit Kaufvertrag vom 14.03.2025 erwarb die Klägerin den Pkw nach § 433 BGB.")
        + "<w:tbl><w:tr><w:tc>" + _p("K 1") + "</w:tc><w:tc>" + _p("Kaufvertrag") + "</w:tc></w:tr></w:tbl>"
        + _p("Seite zwei", "<w:pPr><w:pageBreakBefore/></w:pPr>")
    )
    fussnoten = (
        "<w:footnote w:type='separator' w:id='-1'>" + _p("---") + "</w:footnote>"
        "<w:footnote w:id='1'>" + _p("BGH, Urteil vom 12.10.2016") + "</w:footnote>"
    )
    dok = lesen.lies(_docx(tmp_path / "a.docx", body, fussnoten))
    texte = [(a.text, a.art, a.seite, a.rn) for a in dok.abschnitte]
    assert texte == [
        ("Klage", "absatz", 1, None),
        ("(3) Mit Kaufvertrag vom 14.03.2025 erwarb die Klägerin den Pkw nach § 433 BGB.", "absatz", 1, 3),
        ("K 1 | Kaufvertrag", "tabelle", 1, None),
        ("Seite zwei", "absatz", 2, None),
        ("BGH, Urteil vom 12.10.2016", "fussnote", None, None),
    ]


def test_docx_ohne_umbrueche_hat_keine_seiten(tmp_path):
    dok = lesen.lies(_docx(tmp_path / "a.docx", _p("(1) Text")))
    assert dok.abschnitte[0].seite is None
    assert "Randnummer" in dok.hinweise[0]
    assert dok.seitenzahl is None


def test_docx_harter_umbruch_zaehlt_nur_einmal(tmp_path):
    # Word schreibt nach einem harten Umbruch zusätzlich lastRenderedPageBreak an den Anfang der neuen Seite.
    gerendert = "<w:r><w:lastRenderedPageBreak/></w:r>"
    body = (
        _p("Seite eins")
        + "<w:p><w:r><w:br w:type='page'/></w:r></w:p>"
        + _p("Seite zwei", gerendert)
        + _p("Seite drei", "<w:pPr><w:pageBreakBefore/></w:pPr>" + gerendert)
        + "<w:p><w:r><w:t>Lang</w:t></w:r>" + gerendert + "<w:r><w:t>weiter</w:t></w:r></w:p>"  # weicher Umbruch
        + _p("Seite vier")
        + _p("\u200b")  # leerer Absatz mit unsichtbarem Zeichen
    )
    dok = lesen.lies(_docx(tmp_path / "a.docx", body))
    assert [(a.text, a.seite) for a in dok.abschnitte] == [
        ("Seite eins", 1), ("Seite zwei", 2), ("Seite drei", 3), ("Langweiter", 3), ("Seite vier", 4),
    ]
    assert dok.seitenzahl == 4  # erscheint in der Dokumentliste und im Kopf der Dokumentansicht


def test_docx_seitenzahl_wird_nachgetragen(tmp_path, con):
    akten = akte.oeffne(tmp_path / "akten.sqlite")
    a = akte.akte_anlegen(akten, "Alt")
    body = _p("eins") + "<w:p><w:r><w:br w:type='page'/></w:r></w:p>" + _p("zwei")
    d = akte.importiere(akten, con, a["id"], _docx(tmp_path / "a.docx", body), tmp_path / "ablage", ocr=False)
    assert akten.execute("SELECT seiten FROM dokument").fetchone()[0] == 2
    # Wie eine Word-Datei, eingelesen vor der Seitenzählung.
    with akten:
        akten.execute("UPDATE dokument SET seiten = NULL WHERE id = ?", (d["dokument_id"],))
    akten.close()
    akten = akte.oeffne(tmp_path / "akten.sqlite")
    assert akten.execute("SELECT seiten FROM dokument").fetchone()[0] == 2
    akten.close()


def test_docx_verschachtelte_tabelle_und_kopfzeilen(tmp_path):
    innen = "<w:tbl><w:tr><w:tc>" + _p("Pos. 1") + "</w:tc><w:tc>" + _p("100,00 EUR") + "</w:tc></w:tr></w:tbl>"
    body = (
        "<w:tbl><w:tr><w:tc>" + _p("Anlage K 2") + "</w:tc><w:tc>" + _p("Rechnung") + innen + "</w:tc></w:tr></w:tbl>"
        + _p("Text")
    )
    rahmen = {
        "header1": _p("Kanzlei Muster · Az. 12/26"),
        "header2": _p("Kanzlei Muster · Az. 12/26"),  # erste Seite, gleicher Text
        "footer1": "<w:tbl><w:tr><w:tc>" + _p("Bank") + "</w:tc><w:tc>" + _p("IBAN DE00") + "</w:tc></w:tr></w:tbl>",
    }
    dok = lesen.lies(_docx(tmp_path / "a.docx", body, rahmen=rahmen))
    assert [(a.text, a.art) for a in dok.abschnitte] == [
        ("Anlage K 2 | Rechnung", "tabelle"),
        ("Pos. 1 | 100,00 EUR", "tabelle"),
        ("Text", "absatz"),
        ("Kanzlei Muster · Az. 12/26", "kopfzeile"),
        ("Bank | IBAN DE00", "kopfzeile"),
    ]


def test_markdown_und_text(tmp_path):
    md = tmp_path / "a.md"
    md.write_text("# Klage\n\n(1) Erste Zeile\nzweite Zeile nach **§ 280 BGB**.\\\n\n| K 1 | Kaufvertrag |\n|---|---|\n", "utf-8")
    assert [a.text for a in lesen.lies(md).abschnitte] == [
        "Klage",
        "(1) Erste Zeile zweite Zeile nach § 280 BGB.",
        "K 1 | Kaufvertrag",
    ]
    txt = tmp_path / "a.txt"
    txt.write_bytes("Erste Zeile\nim selben Absatz\n\nZweiter Absatz für Ärzte".encode("cp1252"))
    assert [a.text for a in lesen.lies(txt).abschnitte] == ["Erste Zeile im selben Absatz", "Zweiter Absatz für Ärzte"]


def test_unbekanntes_format(tmp_path):
    with pytest.raises(ValueError, match="nicht unterstützt"):
        lesen.lies(tmp_path / "a.xlsx")


def test_tsv_der_texterkennung():
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t0\t0\t1\t1\t96.0\tnach\n"
        "5\t1\t1\t1\t1\t2\t0\t0\t1\t1\t90.0\t§\n"
        "5\t1\t1\t1\t2\t1\t0\t0\t1\t1\t84.0\t433\n"
        "4\t1\t1\t1\t2\t0\t0\t0\t1\t1\t-1\t\n"
    )
    assert ocr.lies_tsv(tsv) == (["nach §", "433"], 90.0)


def _tesseract_deutsch():
    try:
        t = ocr.Tesseract.finden()
        t.pruefe_sprache()
        return t
    except ocr.OcrNichtVerfuegbar:
        return None


@pytest.mark.skipif(_tesseract_deutsch() is None, reason="Tesseract mit deutschen Sprachdaten nicht installiert")
def test_texterkennung_auf_seitenbild(tmp_path):
    import pypdfium2 as pdfium

    pdf = schreibe_pdf(tmp_path / "t.pdf", [["Die Klägerin verlangt Rückzahlung nach § 346 Abs. 1 BGB."]])
    seite = pdfium.PdfDocument(pdf)[0]
    zeilen, konfidenz = _tesseract_deutsch().erkenne(lesen._seitenbild(seite))
    assert "Klägerin" in " ".join(zeilen)
    assert konfidenz and konfidenz > 50


def test_wortpositionen_der_texterkennung():
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "1\t1\t0\t0\t0\t0\t0\t0\t1000\t2000\t-1\t\n"
        "5\t1\t1\t1\t2\t1\t100\t240\t50\t20\t84.0\t433\n"
        "5\t1\t1\t1\t1\t1\t100\t200\t200\t20\t96.0\tnach\n"
        "5\t1\t1\t1\t1\t2\t320\t200\t10\t20\t90.0\t§\n"
    )
    assert ocr.lies_woerter(tsv) == [
        ["nach", 0, 0.1, 0.1, 0.2, 0.01],
        ["§", 0, 0.32, 0.1, 0.01, 0.01],
        ["433", 1, 0.1, 0.12, 0.05, 0.01],
    ]
    assert ocr.lies_woerter("level\n") == []
