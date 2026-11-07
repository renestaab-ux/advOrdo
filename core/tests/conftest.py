from pathlib import Path

import pytest

from juracore import db, schluesselbund
from juracore.gesetze import quelle, wissensbasis

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def ohne_schluesselbund():
    """Tests schreiben nie in den echten Schlüsselbund des Rechners (auch nicht auf den CI-Rechnern)."""
    schluesselbund.setze_bund(None)
    yield
    schluesselbund.setze_bund(None)


@pytest.fixture
def con(tmp_path):
    verbindung = db.oeffne(tmp_path / "test.sqlite")
    archiv = tmp_path / "archiv"
    for name, abk in (("bgb_auszug.xml", "BGB"), ("zpo_auszug.xml", "ZPO")):
        wissensbasis.importiere(verbindung, quelle.lies_datei(FIXTURES / name, archiv, abk))
    yield verbindung
    verbindung.close()


def schreibe_pdf(pfad: Path, seiten: list[list[str]]) -> Path:
    """Schreibt ein einfaches Text-PDF (Helvetica, eine Zeile je Eintrag) für Tests, ohne Zusatzbibliothek."""

    def zeichenkette(text: str) -> bytes:
        roh = text.encode("cp1252")
        return b"(" + roh.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"

    objekte: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # Seitenbaum, wird unten gefüllt
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    kinder = []
    for zeilen in seiten:
        inhalt = b"BT /F1 11 Tf 14 TL 56 790 Td " + b" ".join(zeichenkette(z) + b" Tj T*" for z in zeilen) + b" ET"
        objekte.append(b"<< /Length %d >>\nstream\n" % len(inhalt) + inhalt + b"\nendstream")
        objekte.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> "
            b"/Contents %d 0 R >>" % len(objekte)
        )
        kinder.append(b"%d 0 R" % len(objekte))
    objekte[1] = b"<< /Type /Pages /Kids [" + b" ".join(kinder) + b"] /Count %d >>" % len(kinder)

    daten = b"%PDF-1.4\n"
    versaetze = []
    for i, obj in enumerate(objekte, start=1):
        versaetze.append(len(daten))
        daten += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(daten)
    daten += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekte) + 1)
    daten += b"".join(b"%010d 00000 n \n" % v for v in versaetze)
    daten += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objekte) + 1, xref)
    pfad.write_bytes(daten)
    return pfad
