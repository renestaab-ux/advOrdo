import pypdfium2 as pdfium
import pypdfium2.raw as raw
import pytest

from juracore.dokumente import akte, anmerkungen, pdf_markiert

from .conftest import schreibe_pdf


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    anmerkungen.einrichten(con)
    yield con
    con.close()


def _akte(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "PDF")["id"]
    pdf = schreibe_pdf(tmp_path / "klage.pdf", [
        ["(1) Auf der ersten Seite steht die Mechatronik."],
        ["(2) Die Mechatronik ist defekt.", "Die Mechatronik wurde getauscht."],
    ])
    d = akte.importiere(akten, con, a, pdf, tmp_path / "ablage", ocr=False)["dokument_id"]
    namen = [w[0] for w in anmerkungen.woerter(akten, d, 2)]
    m1 = anmerkungen.anlegen_auf_seite(akten, d, 2, namen.index("defekt."), len(namen) - 2, "rot",
                                       kommentar="**Bestritten** durch die Beklagte")
    m2 = anmerkungen.anlegen_auf_seite(akten, d, 1, 5, 6, "blau", "unterstrichen")
    return a, d, m1, m2


def _annots(pfad):
    pdf = pdfium.PdfDocument(pfad)
    aus = []
    for nr in range(len(pdf)):
        seite = pdf[nr]
        for i in range(raw.FPDFPage_GetAnnotCount(seite)):
            an = raw.FPDFPage_GetAnnot(seite, i)
            n = raw.FPDFAnnot_GetStringValue(an, b"Contents", None, 0)
            puffer = (raw.FPDF_WCHAR * (n // 2))()
            raw.FPDFAnnot_GetStringValue(an, b"Contents", puffer, n)
            text = bytes(puffer)[:-2].decode("utf-16-le") if n > 2 else ""
            aus.append((nr + 1, raw.FPDFAnnot_GetSubtype(an), raw.FPDFAnnot_CountAttachmentPoints(an), text))
            raw.FPDFPage_CloseAnnot(an)
    pdf.close()
    return aus


def test_kopie_mit_markierungen(akten, con, tmp_path):
    a, d, m1, m2 = _akte(akten, con, tmp_path)
    original = akten.execute("SELECT original FROM dokument WHERE id = ?", (d,)).fetchone()[0]
    vorher = open(original, "rb").read()
    r = pdf_markiert.schreiben(akten, d, tmp_path / "aus" / "kopie")
    assert r["pfad"].endswith("kopie.pdf") and r["eingezeichnet"] == 2 and r["fehlend"] == []
    annots = _annots(r["pfad"])
    assert (1, raw.FPDF_ANNOT_UNDERLINE, 1, "Beweis") in annots
    # Über die Zeilengrenze: zwei Rechtecke, die Notiz mit Bedeutung und Kommentar
    assert (2, raw.FPDF_ANNOT_HIGHLIGHT, 2, "Streitig\n\nBestritten durch die Beklagte") in annots
    assert open(original, "rb").read() == vorher  # das Original bleibt unverändert


def test_auswahl_und_schutz_des_originals(akten, con, tmp_path):
    a, d, m1, m2 = _akte(akten, con, tmp_path)
    r = pdf_markiert.schreiben(akten, d, tmp_path / "nur.pdf", [m2["id"]])
    assert [x[0] for x in _annots(r["pfad"])] == [1]
    original = akten.execute("SELECT original FROM dokument WHERE id = ?", (d,)).fetchone()[0]
    with pytest.raises(ValueError):
        pdf_markiert.schreiben(akten, d, original)
    with pytest.raises(LookupError):
        pdf_markiert.schreiben(akten, d, tmp_path / "x.pdf", [m1["id"], 999])


def test_verlorene_stelle_wird_genannt(akten, con, tmp_path):
    a, d, m1, m2 = _akte(akten, con, tmp_path)
    akten.execute("UPDATE anmerkung SET status = 'nicht_gefunden' WHERE id = ?", (m1["id"],))
    akten.commit()
    r = pdf_markiert.schreiben(akten, d, tmp_path / "k.pdf")
    assert r["eingezeichnet"] == 1
    assert r["fehlend"][0]["id"] == m1["id"] and r["fehlend"][0]["grund"] == "nicht mehr im Text"


def test_ganze_akte_in_einen_ordner(akten, con, tmp_path):
    a, d, m1, m2 = _akte(akten, con, tmp_path)
    (tmp_path / "notiz.md").write_text("Die Beklagte bestreitet den Mangel mit Nichtwissen.", encoding="utf-8")
    d2 = akte.importiere(akten, con, a, tmp_path / "notiz.md", tmp_path / "ablage", ocr=False)["dokument_id"]
    anmerkungen.anlegen(akten, d2, 4, 12)
    ziel = tmp_path / "weitergabe"
    ziel.mkdir()
    r1 = pdf_markiert.akte_schreiben(akten, a, ziel)
    r2 = pdf_markiert.akte_schreiben(akten, a, ziel, [m1["id"]])
    assert r1["kein_pdf"] == ["notiz.md"] and r1["dateien"][0]["eingezeichnet"] == 2
    assert r2["dateien"][0]["eingezeichnet"] == 1 and r2["kein_pdf"] == []
    # Nichts wird überschrieben: die zweite Kopie bekommt einen eigenen Namen
    assert r1["dateien"][0]["pfad"] != r2["dateien"][0]["pfad"] and len(list(ziel.iterdir())) == 2
    with pytest.raises(ValueError):
        pdf_markiert.schreiben(akten, d2, tmp_path / "x.pdf")
