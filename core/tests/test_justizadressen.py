import io
import json
from pathlib import Path

import pytest

from juracore import justizadressen
from juracore.aktenverwaltung import stammdaten
from juracore.dokumente import akte
from juracore.rpc import Kern

AUSZUG = (Path(__file__).parent / "fixtures" / "justizadressen_zivil_auszug.html").read_bytes()


class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_adresse_kodiert_ort_mit_leerzeichen():
    url = justizadressen.adresse("79098", " Freiburg im Breisgau ")
    assert url == f"{justizadressen.BASIS}?plz=79098&ort=Freiburg+im+Breisgau&ang=zivil"


def test_lies_gerichte_mit_anschrift_kontakt_und_xjustiz_id():
    r = justizadressen.lies(AUSZUG.decode())
    assert r["gesucht"] == "Allgemeiner Gerichtsstand, 79098 Freiburg im Breisgau"
    namen = [s["name"] for s in r["stellen"]]
    assert namen[:2] == ["Amtsgericht Freiburg im Breisgau", "Landgericht Freiburg"]
    ag, lg = r["stellen"][0], r["stellen"][1]
    assert ag["xjustiz_id"] == "B1204" and ag["art"] == "gericht"
    assert ag["lieferanschrift"]["strasse"] == "Kaiser-Joseph-Straße 257 a"
    assert ag["postanschrift"]["plz"] == "79098" and ag["postanschrift"]["ort"] == "Freiburg im Breisgau"
    assert ag["telefon"] == "0761 205-0" and ag["fax"] == "0761 205-1800"
    assert ag["email"] == "poststelle@agfreiburg.justiz.bwl.de"
    assert ag["internet"] == "https://amtsgericht-freiburg.justiz-bw.de"
    assert lg["hinweis"] == "Kammer für Handelssachen ist eingerichtet."
    assert {s["art"] for s in r["stellen"]} == {"gericht", "staatsanwaltschaft"}


def test_postfach_geht_als_postanschrift_ins_beteiligtenverzeichnis():
    muster = next(s for s in justizadressen.lies(AUSZUG.decode())["stellen"] if s["name"] == "Landgericht Musterstadt")
    assert muster["postanschrift"]["postfach"] == "Postfach 10 13 49"
    d = justizadressen.beteiligten_daten(muster, "https://beispiel", "2026-10-30T12:00:00+00:00")
    assert d["strasse"] == "Postfach 10 13 49" and d["plz"] == "99998"
    assert "Lieferanschrift: Gerichtsplatz 1, 99999 Musterstadt" in d["notiz"]
    assert "XJustiz-ID: X9999" in d["notiz"] and "abgerufen am 2026-10-30" in d["notiz"]


def test_falsche_eingaben_gehen_nicht_ins_netz(tmp_path):
    def oeffnen(*a, **k):
        raise AssertionError("kein Abruf erwartet")

    k = Kern(tmp_path / "wb.sqlite", tmp_path / "archiv")
    k.diagnose_oeffnen = oeffnen
    with pytest.raises(ValueError):
        k.methoden["gerichte.zustaendig"]("7909", "Freiburg")
    with pytest.raises(ValueError):
        k.methoden["gerichte.zustaendig"]("79098", " ")


def test_abfrage_archiviert_antwort_und_sendet_nur_plz_und_ort(tmp_path):
    abrufe = []

    def oeffnen(anfrage, timeout):
        abrufe.append(anfrage)
        return _Antwort(AUSZUG)

    k = Kern(tmp_path / "wb.sqlite", tmp_path / "archiv")
    k.diagnose_oeffnen = oeffnen
    r = k.methoden["gerichte.zustaendig"]("79098", "Freiburg im Breisgau")
    assert len(abrufe) == 1 and abrufe[0].data is None
    assert abrufe[0].jurabox_gesendet == "PLZ 79098, Ort Freiburg im Breisgau"
    assert Path(r["archiv"]).read_bytes() == AUSZUG
    assert r["stellen"][0]["beteiligter"]["strasse"] == "Kaiser-Joseph-Straße 257 a"
    assert "Quelle: Orts- und Gerichtsverzeichnis der Justiz" in r["stellen"][0]["beteiligter"]["notiz"]


def test_uebernommenes_gericht_kommt_mit_anschrift_in_die_akte(tmp_path):
    k = Kern(tmp_path / "wb.sqlite", tmp_path / "archiv")
    k.diagnose_oeffnen = lambda anfrage, timeout: _Antwort(AUSZUG)
    lg = k.methoden["gerichte.zustaendig"]("79098", "Freiburg im Breisgau")["stellen"][1]
    aid = akte.akte_anlegen(k.akten, "Muster ./. Beispiel")["id"]
    k.methoden["akten.verfahren_speichern"](aid, {"art": "klage", "gericht": lg["name"]},
                                            gericht_daten=lg["beteiligter"])
    bid = next(b["beteiligter_id"] for b in stammdaten.beteiligungen(k.akten, aid) if b["rolle"] == "gericht")
    daten = json.loads(k.akten.execute("SELECT daten FROM beteiligter WHERE id = ?", (bid,)).fetchone()["daten"])
    assert daten["strasse"] == "Konrad-Goldmann-Straße 8" and daten["plz"] == "79100"
    assert daten["kategorie"] == "Gericht" and "XJustiz-ID: B1200" in daten["notiz"]
