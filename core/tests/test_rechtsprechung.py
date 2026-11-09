import json

import pytest

from juracore import db, rpc
from juracore.dokumente import akte
from juracore.rechtsprechung import verzeichnis
from juracore.rechtsprechung.zitate import finde_urteilszitate, normalisiere_az

from .conftest import FIXTURES


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    yield con
    con.close()


# Sätze aus der Testakte Brückner (Klageschrift Rn. 13, Replik Rn. 28).
KLAGE = ("Nach der Rechtsprechung des Bundesgerichtshofs muss der Käufer lediglich darlegen (BGH, Urteil vom "
         "12.10.2016 – VIII ZR 103/15, im Anschluss an EuGH, Urteil vom 04.06.2015 – C-497/13 „Faber“).")
REPLIK = "Die Erklärung ist das „letzte Wort“ des Verkäufers (vgl. BGH, Urteil vom 17.03.2021 – VIII ZR 999/20)."


@pytest.mark.parametrize("text, erwartet", [
    (KLAGE, ["BGH, Urteil vom 12.10.2016 – VIII ZR 103/15", "EuGH, Urteil vom 04.06.2015 – C-497/13"]),
    (REPLIK, ["BGH, Urteil vom 17.03.2021 – VIII ZR 999/20"]),
    ("AG Kleve, Urteil vom 20.07.1998 - 3 C 239/98 - openJur", ["AG Kleve, Urteil vom 20.07.1998 – 3 C 239/98"]),
    ("OLG München, Endurteil v. 18.12.2025 - 14 U 1068/25 e", ["OLG München, Endurteil vom 18.12.2025 – 14 U 1068/25 e"]),
    ("BVerfG, Beschl. v. 1.2.2020 - 1 BvR 123/20", ["BVerfG, Beschluss vom 01.02.2020 – 1 BvR 123/20"]),
    ("OLG Frankfurt am Main, Urt. v. 3.4.2019 – 4 U 12/18", ["OLG Frankfurt am Main, Urteil vom 03.04.2019 – 4 U 12/18"]),
    ("BSG, Urteil vom 01.02.2020 - B 1 KR 2/20 R", ["BSG, Urteil vom 01.02.2020 – B 1 KR 2/20 R"]),
    # Monat ausgeschrieben oder abgekürzt.
    ("„… zu beachten sind“ (BGH, Urteil vom 21. Oktober 2014 – XI ZR 210/13). Fundstelle",
     ["BGH, Urteil vom 21.10.2014 – XI ZR 210/13"]),
    ("LG Köln, Beschl. v. 3. Febr. 2020 - 5 O 1/19", ["LG Köln, Beschluss vom 03.02.2020 – 5 O 1/19"]),
    ("BAG, Urteil vom 1. März 2021, 7 AZR 1/20", ["BAG, Urteil vom 01.03.2021 – 7 AZR 1/20"]),
    ("so auch BGH, VIII ZR 103/15; ferner BGH NJW 2017, 1093", ["BGH – VIII ZR 103/15", "BGH, NJW 2017, 1093"]),
    # Kein Zitat: Gerichtskürzel ohne Aktenzeichen, Datum allein, Gesellschaftsform.
    ("Der BGH hat am 12.10.2016 entschieden; die Autohaus Rehnfeld AG Freiburg haftet.", []),
])
def test_urteilszitate_erkennen(text, erwartet):
    assert [str(z) for z in finde_urteilszitate(text)] == erwartet


def test_fundstelle_im_text():
    z = finde_urteilszitate(REPLIK)[0]
    assert REPLIK[z.treffer[0]:z.treffer[1]] == "BGH, Urteil vom 17.03.2021 – VIII ZR 999/20"
    assert z.datum == "2021-03-17" and z.gerichtstyp == "BGH"
    assert normalisiere_az("VIII  ZR 103 / 15") == normalisiere_az("viii zr 103/15")


def _verzeichnis(con, tmp_path):
    daten = (FIXTURES / "rii_toc_auszug.xml").read_bytes()
    sha, pfad = verzeichnis.archiviere(daten, tmp_path / "archiv")
    return verzeichnis.importiere(con, daten, "rii_toc_auszug.xml", sha, pfad)


def test_verzeichnis_laden_und_archivieren(con, tmp_path):
    stand = _verzeichnis(con, tmp_path)
    assert stand["neu"] is True and stand["eintraege"] == 5  # verbundene Verfahren einzeln
    assert stand["gerichte"]["BGH"] == {"anzahl": 3, "von": "2010-05-12", "bis": "2016-10-12"}
    archiviert = list((tmp_path / "archiv" / "RECHTSPRECHUNG").iterdir())
    assert len(archiviert) == 1 and archiviert[0].read_bytes() == (FIXTURES / "rii_toc_auszug.xml").read_bytes()
    # Dasselbe Verzeichnis noch einmal: kein neuer Stand.
    assert _verzeichnis(con, tmp_path)["neu"] is False


def _pruefe(con, text):
    return verzeichnis.pruefe(con, finde_urteilszitate(text)[0])


def test_zitate_pruefen(con, tmp_path):
    assert _pruefe(con, KLAGE)["status"] == verzeichnis.KEIN_VERZEICHNIS
    _verzeichnis(con, tmp_path)

    belegt = _pruefe(con, KLAGE)
    assert belegt["status"] == verzeichnis.BELEGT
    assert belegt["hinweis"] == "BGH 8. Zivilsenat, 12.10.2016 – VIII ZR 103/15."
    assert "docid=jb-JURE160018467&" in belegt["entscheidung"]["link"]
    assert belegt["entscheidung"]["doknr"] == "JURE160018467"
    assert _pruefe(con, "BGH, VIII ZR 2/10")["status"] == verzeichnis.BELEGT  # ohne Datum, verbundenes Verfahren

    erfunden = _pruefe(con, REPLIK)
    assert erfunden["status"] == verzeichnis.NICHT_GEFUNDEN and "Zitat prüfen" in erfunden["hinweis"]

    falsches_datum = _pruefe(con, "BGH, Urteil vom 13.10.2016 – VIII ZR 103/15")
    assert falsches_datum["status"] == verzeichnis.ABWEICHEND and "12.10.2016" in falsches_datum["hinweis"]
    falsches_gericht = _pruefe(con, "BGH, Urteil vom 14.03.2019 – VIII ZR 77/18")
    assert falsches_gericht["status"] == verzeichnis.ABWEICHEND and "BAG 2. Senat" in falsches_gericht["hinweis"]

    assert _pruefe(con, "EuGH, Urteil vom 04.06.2015 – C-497/13")["status"] == verzeichnis.AUSSERHALB
    assert _pruefe(con, "OLG Hamm, Urteil vom 01.02.2019 – 28 U 1/18")["status"] == verzeichnis.AUSSERHALB
    vor_beginn = _pruefe(con, "BGH, Urteil vom 01.02.2005 – VIII ZR 5/04")
    assert vor_beginn["status"] == verzeichnis.AUSSERHALB and "erst ab 12.05.2010" in vor_beginn["hinweis"]
    assert _pruefe(con, "BFH, Urteil vom 01.02.2019 – IX R 1/18")["status"] == verzeichnis.AUSSERHALB
    assert _pruefe(con, "BGH NJW 2017, 1093")["status"] == verzeichnis.NICHT_PRUEFBAR


def test_rechtsprechung_der_akte(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Brückner")
    for name, text in (("05_Klage.md", f"(13) {KLAGE}"), ("07_Replik.md", f"(28) {REPLIK}\n\n(29) {KLAGE}")):
        (tmp_path / name).write_text(text, encoding="utf-8")
        akte.importiere(akten, con, a["id"], tmp_path / name, tmp_path / "ablage", ocr=False)

    vorher = {e["zitat"]: e["status"] for e in akte.rechtsprechung(akten, con, a["id"])}
    assert set(vorher.values()) == {verzeichnis.KEIN_VERZEICHNIS, verzeichnis.AUSSERHALB}

    # Nach dem Laden des Verzeichnisses: „Zitate neu prüfen“.
    _verzeichnis(con, tmp_path)
    akte.zitate_neu_pruefen(akten, con, a["id"])
    liste = akte.rechtsprechung(akten, con, a["id"])
    assert [(e["zitat"], e["status"]) for e in liste] == [
        ("BGH, Urteil vom 17.03.2021 – VIII ZR 999/20", "nicht_gefunden"),
        ("BGH, Urteil vom 12.10.2016 – VIII ZR 103/15", "belegt"),
        ("EuGH, Urteil vom 04.06.2015 – C-497/13", "ausserhalb"),
    ]
    bgh = liste[1]
    assert [(f["dateiname"], f["rn"]) for f in bgh["fundstellen"]] == [("05_Klage.md", 13), ("07_Replik.md", 29)]
    assert bgh["entscheidung"]["spruchkoerper"] == "8. Zivilsenat"


def test_aeltere_dokumente_werden_nachgetragen(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Alt")
    (tmp_path / "replik.md").write_text(REPLIK, encoding="utf-8")
    d = akte.importiere(akten, con, a["id"], tmp_path / "replik.md", tmp_path / "ablage", ocr=False)["dokument_id"]
    # Wie ein Dokument aus einer Version ohne Rechtsprechungszitate.
    akten.execute("DELETE FROM urteilszitat")
    akten.execute("UPDATE dokument SET urteile_erkannt = NULL WHERE id = ?", (d,))
    assert [e["zitat"] for e in akte.rechtsprechung(akten, con, a["id"])] == [
        "BGH, Urteil vom 17.03.2021 – VIII ZR 999/20"]


def test_aeltere_erkennung_wird_wiederholt(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Alt")
    (tmp_path / "s.md").write_text("Siehe BGH, Urteil vom 21. Oktober 2014 – XI ZR 210/13.", encoding="utf-8")
    d = akte.importiere(akten, con, a["id"], tmp_path / "s.md", tmp_path / "ablage", ocr=False)["dokument_id"]
    # Wie ein Dokument, das eine frühere Erkennung ohne ausgeschriebene Monate durchsucht hat.
    akten.execute("DELETE FROM urteilszitat")
    akten.execute("UPDATE dokument SET urteile_erkannt = 1 WHERE id = ?", (d,))
    assert [e["zitat"] for e in akte.rechtsprechung(akten, con, a["id"])] == [
        "BGH, Urteil vom 21.10.2014 – XI ZR 210/13"]


def test_rpc(tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    antwort = kern.bearbeite(json.dumps({"id": 1, "method": "rechtsprechung.stand"}))
    assert antwort["result"] is None
    antwort = kern.bearbeite(json.dumps({"id": 2, "method": "rechtsprechung.laden_datei",
                                         "params": {"pfad": str(FIXTURES / "rii_toc_auszug.xml")}}))
    assert antwort["result"]["eintraege"] == 5
    antwort = kern.bearbeite(json.dumps({"id": 3, "method": "rechtsprechung.stand"}))
    assert set(antwort["result"]["gerichte"]) == {"BGH", "BVerfG", "BAG"}


def test_unlesbares_verzeichnis(con):
    with pytest.raises(ValueError, match="keine lesbaren Entscheidungen"):
        verzeichnis.importiere(con, b"<html><body>Wartung</body></html>", "x", "abc", "")


def test_gemeinsamer_senat_wird_als_gms_ogb_gefuehrt(tmp_path):
    xml = ("<items><item><gericht>Gemeinsamer Senat der obersten Gerichtshöfe des Bundes</gericht>"
           "<entsch-datum>20100927</entsch-datum><aktenzeichen>GmS-OGB 1/09</aktenzeichen>"
           "<link>http://www.rechtsprechung-im-internet.de/jportal/docs/bsjrs/jb-KORE000000004.zip</link>"
           "</item></items>").encode()
    con = db.oeffne(tmp_path / "wissen.sqlite")
    verzeichnis.importiere(con, xml, "test", "abc", "archiv/x.xml")
    assert set(verzeichnis.stand(con)["gerichte"]) == {"GmS-OGB"}
    (z,) = finde_urteilszitate("GmS-OGB, Beschluss vom 27.09.2010 – GmS-OGB 1/09")
    assert verzeichnis.pruefe(con, z)["status"] == verzeichnis.BELEGT
