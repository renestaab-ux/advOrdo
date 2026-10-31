"""Abruf von gesetze-im-internet.de, ohne echtes Netz (urlopen wird ersetzt)."""

import io
import urllib.error
import zipfile

import pytest

from juracore import db
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


def test_voreinstellung_zivilrecht():
    gesetze = {g["abk"]: g for g in quelle.voreinstellung()}
    assert {"BGB", "ZPO", "HGB", "GVG", "InsO", "RVG", "GKG", "WEG"} <= set(gesetze)
    assert all(g["titel"] and g["gruppe"] for g in gesetze.values())
    # Abweichende Pfadkürzel werden aus der Liste genommen.
    assert quelle.pfadkuerzel("EGBGB") == ("EGBGB", "bgbeg")
    assert quelle.pfadkuerzel("weg") == ("WEG", "woeigg")
    assert quelle.pfadkuerzel("hgb") == ("HGB", "hgb")


def test_eigene_liste_ersetzt_voreinstellung(tmp_path):
    datei = tmp_path / "gesetze.json"
    datei.write_text('{"gesetze": [{"abk": "HGB", "kuerzel": "hgb", "titel": "HGB", "gruppe": "X"}]}', encoding="utf-8")
    assert [g["abk"] for g in quelle.voreinstellung(datei)] == ["HGB"]
    assert len(quelle.voreinstellung(tmp_path / "fehlt.json")) > 30


def test_eigene_liste_mit_ungueltigem_kuerzel(tmp_path):
    datei = tmp_path / "gesetze.json"
    datei.write_text('{"gesetze": [{"abk": "X", "kuerzel": "../x", "titel": "", "gruppe": ""}]}', encoding="utf-8")
    with pytest.raises(ValueError):
        quelle.voreinstellung(datei)


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


def test_umwg_steht_in_der_voreinstellung():
    assert quelle.pfadkuerzel("UmwG") == ("UMWG", "umwg_1995")


def test_kuerzel_mit_jahreszahl_aus_dem_verzeichnis(monkeypatch, tmp_path):
    """Ein freies Kürzel ohne Treffer wird im Verzeichnis gii-toc.xml als „<kürzel>_<jahr>“ gesucht."""
    aufrufe = []
    verzeichnis = (b'<?xml version="1.0"?><items>'
                   b"<item><title>Gesetz A</title><link>http://www.gesetze-im-internet.de/beispg_1990/xml.zip</link></item>"
                   b"<item><title>Gesetz B</title><link>http://www.gesetze-im-internet.de/beispg_2008/xml.zip</link></item>"
                   b"<item><title>Anderes</title><link>http://www.gesetze-im-internet.de/beispgeg/xml.zip</link></item>"
                   b"</items>")

    def urlopen(anfrage, timeout):
        aufrufe.append(anfrage.full_url)
        if anfrage.full_url == quelle.VERZEICHNIS_URL:
            return Antwort(verzeichnis)
        if anfrage.full_url == "https://www.gesetze-im-internet.de/beispg_2008/xml.zip":
            return Antwort(zip_von("hgb_auszug.xml"))
        raise urllib.error.HTTPError(anfrage.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(quelle.urllib.request, "urlopen", urlopen)
    roh = quelle.lade_gesetz("BeispG", tmp_path, gesetze=[])
    assert roh.abk == "BEISPG" and roh.quelle.endswith("/beispg_2008/xml.zip")
    assert aufrufe == ["https://www.gesetze-im-internet.de/beispg/xml.zip", quelle.VERZEICHNIS_URL,
                       "https://www.gesetze-im-internet.de/beispg_2008/xml.zip"]


def test_unbekanntes_kuerzel_auch_nicht_im_verzeichnis(monkeypatch, tmp_path):
    def urlopen(anfrage, timeout):
        if anfrage.full_url == quelle.VERZEICHNIS_URL:
            return Antwort(b"<items></items>")
        raise urllib.error.HTTPError(anfrage.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(quelle.urllib.request, "urlopen", urlopen)
    with pytest.raises(ValueError, match="nicht gefunden"):
        quelle.lade_gesetz("GIBTSNICHT", tmp_path, gesetze=[])


def test_kuerzel_mit_umlaut_und_bindestrich():
    """gesetze-im-internet.de schreibt Umlaute im Pfad als „_“."""
    assert quelle.pfadkuerzel("AVBFernwärmeV", gesetze=[]) == ("AVBFERNWÄRMEV", "avbfernw_rmev")
    assert quelle.pfadkuerzel("AVB-FernwärmeV", gesetze=[]) == ("AVB-FERNWÄRMEV", "avbfernw_rmev")
    with pytest.raises(ValueError):
        quelle.pfadkuerzel("AVB.FernwärmeV", gesetze=[])


def test_schreibweisen_treffen_dasselbe_gesetz(con):
    roh = quelle.Rohdatei("AVBFERNWÄRMEV", "test", "abc", (FIXTURES / "hgb_auszug.xml").read_bytes(), None)
    wissensbasis.importiere(con, roh, "AVBFernwärmeV")
    for zitat in ("§ 1 AVB-FernwärmeV", "§ 1 AVBFernwärmeV", "§ 1 AVBFERNWÄRMEV", "§ 1 AVBFernwaermeV"):
        assert wissensbasis.loese_zitat(con, zitat)["status"] == "belegt", zitat
    # Erneuter Import unter anderer Schreibweise legt kein zweites Gesetz an.
    wissensbasis.importiere(con, roh, "AVB-FernwärmeV")
    assert [g["abk"] for g in db.gesetze(con) if "FERNW" in g["abk"]] == ["AVBFERNWÄRMEV"]
