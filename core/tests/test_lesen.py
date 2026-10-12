import zipfile

import pytest

from juracore.dokumente import lesen, ocr
from juracore.dokumente.modell import LEER, TEXTEBENE

from .conftest import schreibe_pdf

ZEILE = "Die Beklagte lehnte die Nachbesserung ab und berief sich auf den Gewährleistungsausschluss im"


def _docx(pfad, body: str, fussnoten: str | None = None):
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("word/document.xml", f"<w:document {ns}><w:body>{body}</w:body></w:document>")
        if fussnoten:
            z.writestr("word/footnotes.xml", f"<w:footnotes {ns}>{fussnoten}</w:footnotes>")
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
