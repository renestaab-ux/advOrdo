import base64
import json
import struct
import zlib

import pytest

from juracore.dokumente import akte, ansicht

from .conftest import schreibe_pdf


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    yield con
    con.close()


def _lies_png(daten: bytes) -> tuple[int, int, int, bytes]:
    """Minimaler PNG-Leser für den Test: Breite, Höhe, Farbtyp und entpackte Zeilen."""
    assert daten[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, kopf = 8, b"", None
    while pos < len(daten):
        laenge, art = struct.unpack(">I4s", daten[pos:pos + 8])
        inhalt = daten[pos + 8:pos + 8 + laenge]
        (crc,) = struct.unpack(">I", daten[pos + 8 + laenge:pos + 12 + laenge])
        assert crc == zlib.crc32(art + inhalt) & 0xFFFFFFFF
        if art == b"IHDR":
            kopf = struct.unpack(">IIBBBBB", inhalt)
        elif art == b"IDAT":
            idat += inhalt
        pos += 12 + laenge
    return kopf[0], kopf[1], kopf[3], zlib.decompress(idat)


def test_png_kodierer():
    # 2 × 2 Pixel RGB mit Zeilenabstand 8 (2 Byte Polster je Zeile, wie bei PDFium).
    pixel = bytes([255, 0, 0, 0, 255, 0, 9, 9, 0, 0, 255, 255, 255, 255, 9, 9])
    breite, hoehe, farbtyp, zeilen = _lies_png(ansicht.png(2, 2, pixel, 8))
    assert (breite, hoehe, farbtyp) == (2, 2, 2)
    assert zeilen == b"\x00" + pixel[:6] + b"\x00" + pixel[8:14]
    assert _lies_png(ansicht.png(1, 1, b"\x01\x02\x03\x04", kanaele=4))[2] == 6


def test_seitenbild_aus_dem_abgelegten_original(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Test")
    pdf = schreibe_pdf(tmp_path / "klage.pdf", [["(1) Erste Seite."], ["(2) Zweite Seite."]])
    d = akte.importiere(akten, con, a["id"], pdf, tmp_path / "ablage", ocr=False)["dokument_id"]
    pdf.unlink()  # gerendert wird aus der Kopie der App, nicht aus der Datei des Nutzers

    s = ansicht.seitenbild(akten, d, 2, breite=400)
    assert (s["seite"], s["seiten"], s["breite"]) == (2, 2, 400)
    daten = base64.b64decode(s["bild"].removeprefix("data:image/png;base64,"))
    breite, hoehe, _, zeilen = _lies_png(daten)
    assert (breite, hoehe) == (s["breite"], s["hoehe"]) and hoehe > breite  # Hochformat
    assert len(zeilen) == hoehe * (1 + breite * 3)

    assert ansicht.seitenbild(akten, d, 1, breite=99999)["breite"] == ansicht.MAX_BREITE
    with pytest.raises(ValueError, match="hat 2 Seiten"):
        ansicht.seitenbild(akten, d, 3)


def test_seitenbild_nur_fuer_pdf(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Test")
    (tmp_path / "brief.md").write_text("(1) Text.", encoding="utf-8")
    d = akte.importiere(akten, con, a["id"], tmp_path / "brief.md", tmp_path / "ablage", ocr=False)["dokument_id"]
    with pytest.raises(ValueError, match="kein PDF"):
        ansicht.seitenbild(akten, d, 1)


def test_normen_und_rechtsprechung_je_dokument(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Test")
    ids = []
    for name, text in (("a.md", "(1) Nach § 280 Abs. 1 BGB (BGH, Urteil vom 12.10.2016 – VIII ZR 103/15)."),
                       ("b.md", "(1) Nach § 433 BGB (BGH, Urteil vom 17.03.2021 – VIII ZR 999/20).")):
        (tmp_path / name).write_text(text, encoding="utf-8")
        ids.append(akte.importiere(akten, con, a["id"], tmp_path / name, tmp_path / "ablage", ocr=False)["dokument_id"])
    assert len(akte.normen(akten, a["id"])) == 2
    assert [n["zitat"] for n in akte.normen(akten, a["id"], ids[1])] == ["§ 433 BGB"]
    assert [u["zitat"] for u in akte.rechtsprechung(akten, con, a["id"], ids[0])] == [
        "BGH, Urteil vom 12.10.2016 – VIII ZR 103/15"]


WOERTER = [  # [Wort, Zeile, x, y, b, h] wie aus der Texterkennung
    ["Kosten", 0, 0.1, 0.1, 0.2, 0.02], ["als", 0, 0.32, 0.1, 0.1, 0.02], ["Verzugs-", 0, 0.44, 0.1, 0.4, 0.02],
    ["schaden", 1, 0.1, 0.13, 0.35, 0.02], ["nach", 1, 0.5, 0.13, 0.2, 0.02], ["8", 1, 0.72, 0.13, 0.05, 0.02],
    ["286", 1, 0.8, 0.13, 0.15, 0.02],
]


def test_markierungen_aus_wortpositionen():
    m = ansicht.markierungen_aus_woertern(WOERTER, ["kosten"])
    assert m == [{"x": 0.1, "y": 0.1, "b": 0.2, "h": 0.02}]
    # Silbentrennung am Zeilenende: ein Fund, zwei Rechtecke (je Zeile eines).
    m = ansicht.markierungen_aus_woertern(WOERTER, ["Verzugsschaden"])
    assert [(r["x"], r["y"]) for r in m] == [(0.44, 0.1), (0.1, 0.13)]
    assert m[0]["b"] == pytest.approx(0.35)  # ohne den Trennstrich
    # Teil eines Worts: nur der Anteil der Zeichen.
    (r,) = ansicht.markierungen_aus_woertern(WOERTER, ["schaden"])
    assert (r["x"], r["b"]) == (0.1, 0.35)
    # "§" im (korrigierten) Suchtext findet die Verwechslung "8" der Texterkennung.
    (r,) = ansicht.markierungen_aus_woertern(WOERTER, ["§ 286"])
    assert (r["x"], r["b"]) == (0.72, 0.23)
    assert ansicht.markierungen_aus_woertern(WOERTER, ["Mangel"]) == []


def test_markierungen_im_scan_aus_gespeicherten_woertern(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Test")
    pdf = schreibe_pdf(tmp_path / "scan.pdf", [["(1) Erste Seite."]])
    d = akte.importiere(akten, con, a["id"], pdf, tmp_path / "ablage", ocr=False)["dokument_id"]
    # Wie ein Scan: die Seite stammt aus der Texterkennung, die Textebene des PDFs spielt keine Rolle.
    akten.execute("UPDATE seite SET quelle = 'ocr', woerter = ? WHERE dokument_id = ?", (json.dumps(WOERTER), d))
    s = ansicht.seitenbild(akten, d, 1, breite=400, begriffe=["Verzugsschaden"])
    assert len(s["markierungen"]) == 2
    assert ansicht.seitenbild(akten, d, 1, breite=400, begriffe=["Erste"])["markierungen"] == []
    assert ansicht.seitenbild(akten, d, 1, breite=400)["markierungen"] == []
