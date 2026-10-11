"""Abruf von gesetze-im-internet.de, ohne echtes Netz (urlopen wird ersetzt)."""

import io
import urllib.error
import zipfile

import pytest

from juracore.gesetze import quelle, wissensbasis
from juracore.rpc import Kern

from .conftest import FIXTURES


def zip_von(name: str) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("BJNR002190897.xml", (FIXTURES / name).read_bytes())
    return puffer.getvalue()


class Antwort(io.BytesIO):
    headers = {"ETag": '"abc"', "Last-Modified": "Tue, 01 Sep 2026 12:00:00 GMT"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture
def server(monkeypatch):
    """Simuliert gesetze-im-internet.de: kennt nur /hgb/xml.zip."""
    aufrufe = []

    def urlopen(anfrage, timeout):
        aufrufe.append(anfrage)
        if anfrage.full_url == "https://www.gesetze-im-internet.de/hgb/xml.zip":
            if anfrage.get_header("If-none-match") == '"abc"':
                raise urllib.error.HTTPError(anfrage.full_url, 304, "Not Modified", {}, None)
            return Antwort(zip_von("hgb_auszug.xml"))
        raise urllib.error.HTTPError(anfrage.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(quelle.urllib.request, "urlopen", urlopen)
    return aufrufe


def test_hgb_ist_standard():
    assert quelle.pfadkuerzel("hgb") == ("HGB", "hgb")
    assert "HGB" in quelle.BEKANNTE_GESETZE


@pytest.mark.parametrize("kuerzel", ["", "../etc", "bgb/xml", "a b", "x" * 41])
def test_ungueltige_kuerzel(kuerzel):
    with pytest.raises(ValueError):
        quelle.pfadkuerzel(kuerzel)


def test_freies_kuerzel_wird_kleingeschrieben():
    assert quelle.pfadkuerzel("GmbHG") == ("GMBHG", "gmbhg")


def test_hgb_laden_und_zitieren(server, con, tmp_path):
    roh = quelle.lade_gesetz("HGB", tmp_path)
    assert roh.archivpfad.suffix == ".zip"
    ergebnis = wissensbasis.importiere(con, roh)
    assert ergebnis == {"abk": "HGB", "fassung_id": ergebnis["fassung_id"], "neu": True, "normen": 2}

    beleg = wissensbasis.loese_zitat(con, "§ 1 Abs. 2 HGB")
    assert beleg["status"] == "belegt"
    assert beleg["wortlaut"].startswith("Handelsgewerbe ist jeder Gewerbebetrieb")
    assert beleg["fassung"]["quelle"] == "https://www.gesetze-im-internet.de/hgb/xml.zip"

    # Zweiter Abruf ist bedingt; der simulierte Server meldet "unverändert".
    with pytest.raises(quelle.NichtGeaendert):
        quelle.lade_gesetz("HGB", tmp_path)
    assert server[-1].get_header("If-none-match") == '"abc"'


def test_unbekanntes_gesetz_haelt_die_uebrigen_nicht_auf(server, tmp_path):
    kern = Kern(tmp_path / "db.sqlite", tmp_path / "archiv")
    ergebnisse = kern.importieren(["GIBTSNICHT", "HGB", "../x"])
    assert "nicht gefunden" in ergebnisse[0]["fehler"]
    assert ergebnisse[1]["neu"] is True
    assert "Ungültige" in ergebnisse[2]["fehler"]
