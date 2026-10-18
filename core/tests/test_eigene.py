import json

import pytest

from juracore.dokumente import akte
from juracore.eigene import daten as eigene


@pytest.fixture
def con(tmp_path):
    verbindung = akte.oeffne(tmp_path / "akten.sqlite")
    eigene.einrichten(verbindung)
    yield verbindung
    verbindung.close()


ANSCHRIFT = {"strasse": "Musterweg 1", "plz": "10115", "ort": "Berlin"}
ICH = {"anrede": "Frau", "vorname": "Erika", "nachname": "Muster", "berufsbezeichnung": "Rechtsanwältin"}


def test_ohne_profil(con):
    assert eigene.kurzstand(con) == {"text": "Noch nicht eingerichtet", "eingerichtet": False, "fehlend": 1,
                                     "hinweise": 0}
    with pytest.raises(ValueError, match="Organisationsform"):
        eigene.organisation_speichern(con, ANSCHRIFT)


def test_einzelanwalt_in_drei_schritten(con):
    s = eigene.form_setzen(con, "einzelanwalt")
    assert s["fehlend"] == ["Kanzlei: Angaben", "Ihre Person: Angaben"]
    eigene.inhaber_speichern(con, ICH)
    s = eigene.organisation_speichern(con, ANSCHRIFT)
    assert s["fehlend"] == [] and s["hinweise"] == []
    # Leerer Kanzleiname: „Rechtsanwältin Erika Muster“.
    assert s["organisation_name"] == "Rechtsanwältin Erika Muster"
    assert s["organisation"]["daten"]["land"] == "Deutschland"
    assert [b["daten"]["nachname"] for b in s["berufstraeger"]] == ["Muster"]
    assert eigene.kurzstand(con)["text"] == "Profil vollständig"


def test_pflichtfelder_und_plausibilitaet(con):
    eigene.form_setzen(con, "einzelanwalt")
    eigene.inhaber_speichern(con, {**ICH, "email": "kein-at"})
    s = eigene.organisation_speichern(con, {"strasse": "Musterweg 1", "plz": "1011", "ort": ""})
    assert s["fehlend"] == ["Kanzlei: Ort"]
    assert "Kanzlei: Eine deutsche Postleitzahl hat fünf Ziffern." in s["hinweise"]
    assert "Ihre Person: E-Mail sieht nicht wie eine E-Mail-Adresse aus." in s["hinweise"]
    assert eigene.kurzstand(con)["text"] == "1 Angabe fehlt"
    # Ausland: keine Prüfung der deutschen PLZ.
    s = eigene.organisation_speichern(con, {"strasse": "Rue 1", "plz": "1000", "ort": "Bruxelles", "land": "Belgien"})
    assert not any("Postleitzahl" in h for h in s["hinweise"])


def test_auswahlwerte_und_hoechstens_drei_fachanwaltstitel(con):
    eigene.form_setzen(con, "einzelanwalt")
    with pytest.raises(ValueError, match="höchstens 3"):
        eigene.inhaber_speichern(con, {**ICH, "fachanwalt": ["Arbeitsrecht", "Erbrecht", "Strafrecht", "Steuerrecht"]})
    with pytest.raises(ValueError, match="kein zulässiger Wert"):
        eigene.inhaber_speichern(con, {**ICH, "fachanwalt": ["Kochrecht"]})
    with pytest.raises(ValueError, match="kein zulässiger Wert"):
        eigene.inhaber_speichern(con, {**ICH, "berufsbezeichnung": "Zauberer"})
    s = eigene.inhaber_speichern(con, {**ICH, "fachanwalt": ["Arbeitsrecht", "Arbeitsrecht", "Erbrecht"],
                                       "unbekannt": "weg"})
    assert s["inhaber"]["daten"]["fachanwalt"] == ["Arbeitsrecht", "Erbrecht"]
    assert "unbekannt" not in s["inhaber"]["daten"]


def test_kanzlei_berufstraeger_und_briefbogenhinweise(con):
    eigene.form_setzen(con, "kanzlei")
    s = eigene.organisation_speichern(con, {"name": "Muster & Partner", "rechtsform": "GmbH", **ANSCHRIFT})
    assert any("§ 35a Abs. 1 GmbHG" in h and "Registergericht" in h for h in s["hinweise"])
    assert any("Geschäftsführer" in h for h in s["hinweise"])
    s = eigene.inhaber_speichern(con, ICH, {"stellung": "Gesellschafter/Partner", "vertretungsorgan": True})
    org_id = s["organisation"]["id"]
    kollege = eigene.person_speichern(con, org_id, {"vorname": "Max", "nachname": "Beispiel",
                                                    "berufsbezeichnung": "Rechtsanwalt"}, {"stellung": "Angestellt"})
    s = eigene.organisation_speichern(con, {**s["organisation"]["daten"], "registergericht": "AG Charlottenburg",
                                            "registernummer": "HRB 1"})
    assert s["hinweise"] == []
    assert [b["daten"]["vorname"] for b in s["berufstraeger"]] == ["Erika", "Max"]
    # Der Profilinhaber wird aus den Berufsträgern gewählt.
    s = eigene.inhaber_waehlen(con, kollege["id"])
    assert s["inhaber"]["daten"]["vorname"] == "Max"
    with pytest.raises(ValueError, match="Profilinhaber"):
        eigene.loeschen(con, "person", kollege["id"])


def test_rechtsabteilung_mit_konzern_und_beauftragter_kanzlei(con):
    eigene.form_setzen(con, "rechtsabteilung")
    eigene.organisation_speichern(con, {"name": "Muster Holding AG", **ANSCHRIFT})
    s = eigene.inhaber_speichern(con, {**ICH, "berufsbezeichnung": "Syndikusrechtsanwältin"})
    assert s["fehlend"] == ["Ihre Person: Zulassungsstatus"]
    s = eigene.inhaber_speichern(con, {**s["inhaber"]["daten"], "zulassungsstatus": "Syndikusrechtsanwalt"})
    assert s["fehlend"] == []

    tochter = eigene.einheit_speichern(con, "konzerngesellschaft", {"name": "Muster Logistik GmbH", "ort": "Hamburg"})
    s = tochter["stand"]
    assert any("§ 130 Nr. 1" in h for h in s["hinweise"])
    s = eigene.einheit_speichern(con, "konzerngesellschaft", {**s["konzerngesellschaften"][0]["daten"],
                                                              "gesetzliche_vertreter": "Hans Beispiel"},
                                 tochter["id"])["stand"]
    assert s["hinweise"] == []

    kanzlei = eigene.einheit_speichern(con, "beauftragte_kanzlei", {"name": "Prozess LLP", "ort": "Frankfurt"})
    eigene.person_speichern(con, kanzlei["id"], {"vorname": "Paula", "nachname": "Prozess", "fachanwalt": ["Arbeitsrecht"]})
    s = eigene.stand(con)
    assert [a["daten"]["nachname"] for a in s["beauftragte_kanzleien"][0]["anwaelte"]] == ["Prozess"]

    kopie = eigene.duplizieren(con, tochter["id"])
    assert kopie["stand"]["konzerngesellschaften"][1]["daten"]["name"] == "Muster Logistik GmbH (Kopie)"

    s = eigene.archivieren(con, "organisation", tochter["id"])
    assert s["konzerngesellschaften"][0]["archiviert"] is True
    assert len(eigene.stand(con, mit_archiv=False)["konzerngesellschaften"]) == 1

    # Mit der Kanzlei verschwinden ihre Anwälte.
    eigene.loeschen(con, "organisation", kanzlei["id"])
    assert con.execute("SELECT COUNT(*) FROM eigene_person").fetchone()[0] == 1


def test_formwechsel(con):
    eigene.form_setzen(con, "einzelanwalt")
    eigene.inhaber_speichern(con, ICH)
    eigene.organisation_speichern(con, ANSCHRIFT)
    # Einzelanwalt → Kanzlei: dieselbe Kanzlei, nur der Name fehlt jetzt noch.
    s = eigene.form_setzen(con, "kanzlei")
    assert s["organisation"] is not None
    assert set(s["fehlend"]) == {"Kanzlei: Name bzw. Kurzbezeichnung", "Kanzlei: Rechtsform"}
    # Kanzlei → Rechtsabteilung: alte Kanzlei archiviert, Person bleibt.
    alt_id = s["organisation"]["id"]
    s = eigene.form_setzen(con, "rechtsabteilung")
    assert s["organisation"] is None and s["inhaber"]["daten"]["vorname"] == "Erika"
    assert eigene.organisation(con, alt_id)["archiviert"] is True


def test_export_import(con, tmp_path):
    eigene.form_setzen(con, "rechtsabteilung")
    eigene.organisation_speichern(con, {"name": "Muster Holding AG", **ANSCHRIFT})
    eigene.inhaber_speichern(con, {**ICH, "zulassungsstatus": "Ohne Zulassung"})
    k = eigene.einheit_speichern(con, "beauftragte_kanzlei", {"name": "Prozess LLP"})
    eigene.person_speichern(con, k["id"], {"vorname": "Paula", "nachname": "Prozess"})
    datei = tmp_path / "profil.json"
    assert eigene.exportieren(con, datei) == {"pfad": str(datei), "organisationen": 2, "personen": 2}
    assert json.loads(datei.read_text(encoding="utf-8"))["format"] == "jurabox-eigene-daten"

    andere = akte.oeffne(tmp_path / "andere.sqlite")
    eigene.einrichten(andere)
    s = eigene.importieren(andere, datei)
    assert s["profil"]["form"] == "rechtsabteilung" and s["profil"]["assistent_fertig"] is True
    assert s["organisation_name"] == "Muster Holding AG"
    assert s["inhaber"]["daten"]["zulassungsstatus"] == "Ohne Zulassung"
    assert s["beauftragte_kanzleien"][0]["anwaelte"][0]["daten"]["vorname"] == "Paula"
    with pytest.raises(ValueError, match="ersetzt"):
        eigene.importieren(andere, datei)
    assert eigene.importieren(andere, datei, ersetzen=True)["fehlend"] == []

    falsch = tmp_path / "falsch.json"
    falsch.write_text('{"format": "etwas"}', encoding="utf-8")
    with pytest.raises(ValueError, match="keine Exportdatei"):
        eigene.importieren(andere, falsch, ersetzen=True)
    andere.close()


def test_aenderungsprotokoll(con):
    eigene.form_setzen(con, "einzelanwalt")
    eigene.inhaber_speichern(con, ICH)
    eigene.inhaber_speichern(con, {**ICH, "nachname": "Neu"})
    letzte = eigene.aenderungen(con, 1)[0]
    assert (letzte["feld"], letzte["alt"], letzte["neu"]) == ("nachname", "Muster", "Neu")


@pytest.mark.parametrize("name", ["einzelanwalt", "kanzlei", "rechtsabteilung"])
def test_testprofile_sind_vollstaendig(con, name):
    from pathlib import Path

    datei = Path(__file__).parents[2] / "testdaten" / "eigene-daten" / f"{name}.json"
    s = eigene.importieren(con, datei)
    assert s["profil"]["form"] == name
    assert s["fehlend"] == [] and s["hinweise"] == []
