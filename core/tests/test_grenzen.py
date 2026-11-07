import io
import zipfile

import pytest

from juracore import grenzen, netzprotokoll
from juracore.dokumente import lesen


class Antwort:
    def __init__(self, daten: bytes, laenge: str | None = None):
        self.datei = io.BytesIO(daten)
        self.headers = {"Content-Length": laenge} if laenge else {}
        self.url = "https://beispiel.invalid/x"
        self.geschlossen = False

    def read(self, amt=None):
        return self.datei.read(amt)

    def close(self):
        self.geschlossen = True


def test_antwort_bis_zur_grenze_wird_gelesen():
    assert grenzen.begrenze(Antwort(b"a" * 100), grenze=100).read() == b"a" * 100
    teilweise = grenzen.begrenze(Antwort(b"abc"), grenze=10)
    assert teilweise.read(2) + teilweise.read() == b"abc"


def test_zu_grosse_antwort_bricht_ab():
    with pytest.raises(grenzen.ZuGross, match="größer als"):
        grenzen.begrenze(Antwort(b"a" * 101), grenze=100).read()
    # Ohne Längenangabe gezählt, auch beim Lesen in Stücken
    antwort = grenzen.begrenze(Antwort(b"a" * 101), grenze=100)
    antwort.read(60)
    with pytest.raises(grenzen.ZuGross):
        antwort.read(60)
    assert antwort.geschlossen
    # Mit Längenangabe schon vor dem Lesen
    with pytest.raises(grenzen.ZuGross):
        grenzen.begrenze(Antwort(b"", laenge="5000"), grenze=100)


def test_protokoll_begrenzt_jede_antwort(monkeypatch):
    monkeypatch.setattr(netzprotokoll, "_schreibe", lambda *a: None)
    monkeypatch.setattr(grenzen, "GROESSTE_ANTWORT", 10)
    monkeypatch.setattr(grenzen.begrenze, "__defaults__", (10,))
    antwort = netzprotokoll._mitschreiben(object(), lambda: Antwort(b"x" * 11))
    with pytest.raises(grenzen.ZuGross):
        antwort.read()


def test_zip_bombe_in_word_datei(tmp_path, monkeypatch):
    pfad = tmp_path / "bombe.docx"
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", f"<w:document {ns}><w:body>" + " " * 5000 + "</w:body></w:document>")
    monkeypatch.setattr(grenzen.entpacke, "__defaults__", (1000,))
    with pytest.raises(ValueError, match="größer als"):
        lesen.lies(pfad)


def test_entpacken_prueft_auch_die_tatsaechliche_groesse():
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("a.xml", b"x" * 50)
    with zipfile.ZipFile(puffer) as z:
        assert grenzen.entpacke(z, "a.xml", grenze=50) == b"x" * 50
        info = z.getinfo("a.xml")
        info.file_size = 10  # Verzeichnis lügt
        with pytest.raises((grenzen.ZuGross, zipfile.BadZipFile)):
            grenzen.entpacke(z, info, grenze=20)
