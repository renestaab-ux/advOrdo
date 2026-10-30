import io
import sqlite3
from pathlib import Path

import pytest

from juracore import gerichte
from juracore.rpc import Kern

AUSZUG = (Path(__file__).parent / "fixtures" / "gds_gerichte_auszug.xml").read_bytes()


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    return con


def test_lies_genericode_auch_ohne_columnref():
    version, zeilen = gerichte.lies(AUSZUG)
    assert version == "3.7"
    assert ("B2402", "Amtsgericht Biberach an der Riß") in zeilen
    assert ("R2000", "Oberlandesgericht Hamm") in zeilen
    assert len(zeilen) == 5


def test_art_trennt_gerichte_von_staatsanwaltschaft_und_grundbuchamt():
    assert gerichte.art("Oberlandesgericht Hamm") == "gericht"
    assert gerichte.art("Amtsgericht Stuttgart - Mahngericht -") == "gericht"
    assert gerichte.art("Generalstaatsanwaltschaft Hamm") == "staatsanwaltschaft"
    assert gerichte.art("Amtsgericht Achern -Grundbuchamt-") == "sonstige"
    assert gerichte.art("Bundesamt für Justiz") == "sonstige"


def test_import_archiviert_unveraendert_und_nicht_doppelt(tmp_path):
    con = _con()
    sha, pfad = gerichte.archiviere(AUSZUG, tmp_path)
    assert Path(pfad).read_bytes() == AUSZUG
    s = gerichte.importiere(con, AUSZUG, "test", sha, pfad)
    assert s["neu"] and s["eintraege"] == 5 and s["version"] == "3.7"
    assert s["arten"] == {"gericht": 2, "staatsanwaltschaft": 1, "sonstige": 2}
    assert gerichte.importiere(con, AUSZUG, "test", sha, pfad)["neu"] is False
    assert gerichte.namen(con) == ["Amtsgericht Biberach an der Riß", "Oberlandesgericht Hamm"]


def test_leere_oder_fremde_datei_wird_abgelehnt():
    with pytest.raises(ValueError):
        gerichte.lies(b"<foo/>")
    leer = AUSZUG.split(b"<SimpleCodeList>")[0] + b"<SimpleCodeList/></gc:CodeList>"
    with pytest.raises(ValueError):
        gerichte.importiere(_con(), leer, "test", "x", "")


class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_laden_fragt_gueltige_version_und_laedt_genericode(tmp_path):
    abrufe = []

    def oeffnen(anfrage, timeout):
        abrufe.append(anfrage.full_url)
        if anfrage.full_url == gerichte.VERSION_URL:
            return _Antwort(b"<dat:kennung>urn:xoev-de:xjustiz:codeliste:gds.gerichte_3.8</dat:kennung>")
        return _Antwort(AUSZUG)

    k = Kern(tmp_path / "wb.sqlite", tmp_path / "archiv")
    k.diagnose_oeffnen = oeffnen
    s = k.methoden["gerichte.laden"]()
    assert abrufe[1].endswith("gds.gerichte_3.8/genericode")
    assert s["eintraege"] == 5
    assert (tmp_path / "archiv" / "GERICHTE" / f"{s['sha256']}.xml").exists()
    assert k.methoden["gerichte.namen"]() == ["Amtsgericht Biberach an der Riß", "Oberlandesgericht Hamm"]


def test_ohne_versionsauskunft_gilt_die_bekannte_version():
    def oeffnen(anfrage, timeout):
        raise OSError("kein Netz")

    assert gerichte.gueltige_version(oeffnen) == gerichte.VERSION_RUECKFALL


def test_verzeichnis_oeffnen_zeigt_die_suchseite():
    geoeffnet = []
    gerichte.verzeichnis_oeffnen(geoeffnet.append)
    assert geoeffnet == ["https://www.justizadressen.nrw.de/de/justiz/suche"]


def test_browser_oeffnet_nur_https():
    from juracore import programme

    with pytest.raises(ValueError):
        programme.im_browser_oeffnen("file:///etc/passwd")
