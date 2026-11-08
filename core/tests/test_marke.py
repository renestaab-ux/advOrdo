import base64

import pytest

from juracore.dokumente import akte
from juracore.eigene import daten as eigene
from juracore.eigene import marke

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture
def con(tmp_path):
    verbindung = akte.oeffne(tmp_path / "akten.sqlite")
    eigene.einrichten(verbindung)
    yield verbindung
    verbindung.close()


def test_ohne_logo(tmp_path, con):
    assert marke.lesen(tmp_path, con) == {"logo": None, "kurzbezeichnung": "", "name": "", "druckbild": False,
                                       "hintergrund": "weiss"}


def test_logo_setzen_ersetzen_entfernen(tmp_path, con):
    ordner = tmp_path / "umgebung"
    bild = tmp_path / "Logo Kanzlei.PNG"
    bild.write_bytes(PNG)
    m = marke.logo_setzen(ordner, con, bild)
    assert m["logo"].startswith("data:image/png;base64,")
    assert (ordner / "logo.png").read_bytes() == PNG
    svg = tmp_path / "logo.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    m = marke.logo_setzen(ordner, con, svg)
    assert m["logo"].startswith("data:image/svg+xml;base64,")
    assert sorted(p.name for p in ordner.iterdir()) == ["logo.svg"]
    assert marke.logo_entfernen(ordner, con)["logo"] is None


def test_logo_pruefung(tmp_path, con):
    pdf = tmp_path / "logo.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(ValueError, match="PNG"):
        marke.logo_setzen(tmp_path, con, pdf)
    gross = tmp_path / "gross.png"
    gross.write_bytes(b"0" * (marke.GROESSTE + 1))
    with pytest.raises(ValueError, match="2 MB"):
        marke.logo_setzen(tmp_path, con, gross)


def test_kurzbezeichnung_und_name(tmp_path, con):
    assert marke.kurz_setzen(tmp_path, con, "  Muster   & Partner ")["kurzbezeichnung"] == "Muster & Partner"
    with pytest.raises(ValueError, match="40"):
        marke.kurz_setzen(tmp_path, con, "x" * 41)
    eigene.form_setzen(con, "einzelanwalt")
    eigene.inhaber_speichern(con, {"anrede": "Frau", "vorname": "Erika", "nachname": "Muster",
                                   "berufsbezeichnung": "Rechtsanwältin"})
    eigene.organisation_speichern(con, {"strasse": "Musterweg 1", "plz": "10115", "ort": "Berlin"})
    assert marke.lesen(tmp_path, con)["name"] == "Rechtsanwältin Erika Muster"


def test_hintergrund_neben_kurzbezeichnung(tmp_path, con):
    marke.kurz_setzen(tmp_path, con, "Muster")
    m = marke.hintergrund_setzen(tmp_path, con, "akzent")
    assert (m["hintergrund"], m["kurzbezeichnung"]) == ("akzent", "Muster")
    # Die Kurzbezeichnung zu ändern lässt den Hintergrund stehen.
    assert marke.kurz_setzen(tmp_path, con, "Neu")["hintergrund"] == "akzent"
    with pytest.raises(ValueError, match="weiß"):
        marke.hintergrund_setzen(tmp_path, con, "rot")


def test_hintergrund_unbekannt_oder_kaputt(tmp_path, con):
    (tmp_path / "marke.json").write_text('{"hintergrund": "rot"}', encoding="utf-8")
    assert marke.lesen(tmp_path, con)["hintergrund"] == "weiss"
    (tmp_path / "marke.json").write_text("[1, 2]", encoding="utf-8")
    assert marke.lesen(tmp_path, con)["kurzbezeichnung"] == ""
