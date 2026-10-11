from juracore import db
from juracore.gesetze import quelle, wissensbasis

from .conftest import FIXTURES


def test_liste(con):
    gesetze = {g["abk"]: g for g in db.gesetze(con)}
    assert set(gesetze) == {"BGB", "ZPO"}
    assert gesetze["BGB"]["normen"] == 6
    assert gesetze["BGB"]["fassungen"] == 1


def test_zitat_belegt_mit_fassung(con):
    beleg = wissensbasis.loese_zitat(con, "§ 280 Abs. 1 S. 2 BGB")
    assert beleg["status"] == "belegt"
    assert beleg["wortlaut"] == "Dies gilt nicht, wenn der Schuldner die Pflichtverletzung nicht zu vertreten hat."
    assert beleg["fassung"]["builddate"] == "20260901120000"
    assert len(beleg["fassung"]["sha256"]) == 64


def test_zitat_nummer(con):
    beleg = wissensbasis.loese_zitat(con, "§ 253 Abs. 2 Nr. 2 ZPO")
    assert beleg["status"] == "belegt"
    assert beleg["wortlaut"].startswith("2. die bestimmte Angabe des Gegenstandes")


def test_falsche_fundstellen_werden_benannt(con):
    assert wissensbasis.loese_zitat(con, "§ 280 Abs. 4 BGB")["hinweis"] == "§ 280 hat keinen Absatz 4."
    assert wissensbasis.loese_zitat(con, "§ 280 Abs. 1 S. 3 BGB")["status"] == "nicht_gefunden"
    assert wissensbasis.loese_zitat(con, "§ 9999 BGB")["status"] == "nicht_gefunden"
    assert wissensbasis.loese_zitat(con, "§ 1 HGB")["status"] == "unbekanntes_gesetz"
    assert wissensbasis.loese_zitat(con, "§ 1300 BGB")["hinweis"] == "Die Norm ist weggefallen."


def test_suche(con):
    treffer = wissensbasis.suche(con, "Verjährungsfrist")
    assert [t["bezeichnung"] for t in treffer][:2] == ["§ 195", "§ 199"]
    assert wissensbasis.suche(con, "Klageschrift", gesetz="BGB") == []
    assert wissensbasis.suche(con, "klageschrift")[0]["bezeichnung"] == "§ 253"
    # Sonderzeichen in Nutzereingaben dürfen die FTS-Abfrage nicht brechen.
    assert wissensbasis.suche(con, '"§ 280" OR (') is not None


def test_gleiche_datei_ergibt_keine_neue_fassung(con, tmp_path):
    erneut = wissensbasis.importiere(con, quelle.lies_datei(FIXTURES / "bgb_auszug.xml", tmp_path, "BGB"))
    assert erneut["neu"] is False


def test_neue_fassung_alte_bleibt_reproduzierbar(con, tmp_path):
    alt = wissensbasis.loese_zitat(con, "§ 195 BGB")
    geaendert = (
        (FIXTURES / "bgb_auszug.xml")
        .read_text(encoding="utf-8")
        .replace("beträgt drei Jahre.", "beträgt vier Jahre.")
        .replace('builddate="20260901120000"', 'builddate="20261001120000"', 1)
    )
    datei = tmp_path / "bgb_neu.xml"
    datei.write_text(geaendert, encoding="utf-8")
    neu = wissensbasis.importiere(con, quelle.lies_datei(datei, tmp_path / "archiv", "BGB"))
    assert neu["neu"] is True

    aktuell = wissensbasis.loese_zitat(con, "§ 195 BGB")
    assert aktuell["wortlaut"] == "Die regelmäßige Verjährungsfrist beträgt vier Jahre."
    damals = wissensbasis.loese_zitat(con, "§ 195 BGB", fassung_id=alt["fassung"]["id"])
    assert damals["wortlaut"] == "Die regelmäßige Verjährungsfrist beträgt drei Jahre."
    # Die Suche zeigt nur die neueste Fassung.
    assert len(wissensbasis.suche(con, "Verjährungsfrist beträgt")) == 1


def test_roharchiv_unveraendert(tmp_path):
    roh = quelle.lies_datei(FIXTURES / "zpo_auszug.xml", tmp_path, "ZPO")
    assert roh.archivpfad.read_bytes() == (FIXTURES / "zpo_auszug.xml").read_bytes()
    assert roh.archivpfad.name == f"{roh.sha256}.xml"
