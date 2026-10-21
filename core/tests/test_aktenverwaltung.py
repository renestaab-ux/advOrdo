from datetime import date

import pytest

from juracore.aktenverwaltung import beteiligte, einrichten, kollision, stammdaten
from juracore.dokumente import akte
from juracore.eigene import daten as eigene
from juracore.rpc import Kern

HEUTE = date(2026, 10, 19)


@pytest.fixture
def con(tmp_path):
    verbindung = akte.oeffne(tmp_path / "akten.sqlite")
    eigene.einrichten(verbindung)
    einrichten(verbindung)
    yield verbindung
    verbindung.close()


def neue_akte(con, name="Brückner ./. Autohaus Rehnfeld"):
    a = akte.akte_anlegen(con, name)
    stammdaten.vergeben(con, a["id"], heute=HEUTE)
    return a["id"]


def person(con, vorname, nachname, **weiter):
    return beteiligte.speichern(con, "person", {"vorname": vorname, "nachname": nachname, **weiter})["id"]


def firma(con, name, **weiter):
    return beteiligte.speichern(con, "organisation", {"name": name, **weiter})["id"]


# --------------------------------------------------------------------------- Namen


def test_schluessel_ohne_rechtsform_titel_und_reihenfolge():
    assert beteiligte.schluessel("Autohaus Rehnfeld GmbH") == beteiligte.schluessel(
        "Autohaus Rehnfeld Gesellschaft mit beschränkter Haftung")
    assert beteiligte.schluessel("Dr. Lena Brückner") == beteiligte.schluessel("Brückner, Lena") == "brueckner lena"
    assert beteiligte.schluessel("Kornmeier GmbH & Co. KG") == "kornmeier"


def test_aehnlichkeit():
    assert beteiligte.aehnlichkeit("brueckner lena", "brueckner lena") == "gleich"
    assert beteiligte.aehnlichkeit("bau mueller", "bau holding mueller") == "aehnlich"
    assert beteiligte.aehnlichkeit("brueckner lena", "brueckner lenna") == "aehnlich"  # Tippfehler
    assert beteiligte.aehnlichkeit("reiter", "jonas reiter") == "aehnlich"  # nur der Nachname
    assert beteiligte.aehnlichkeit("joanas reiter", "jonas reiter") == "aehnlich"
    assert beteiligte.aehnlichkeit("reiter", "jonas reitter") == "aehnlich"
    assert beteiligte.aehnlichkeit("mueller peter", "mueller karin") is None  # zwei volle Namen, ein Wort gleich
    assert beteiligte.aehnlichkeit("ost", "west") is None


def test_beteiligte_anlegen_suchen_dubletten(con):
    lena = person(con, "Lena", "Brückner", titel="Dr.", fruehere_namen="Lena Kaiser")
    firma(con, "Autohaus Rehnfeld", rechtsform="GmbH", kategorie="Unternehmen")
    assert beteiligte.eintrag(con, lena)["name"] == "Dr. Lena Brückner"
    assert [e["name"] for e in beteiligte.liste(con, "rehn")] == ["Autohaus Rehnfeld GmbH"]
    assert [e["name"] for e in beteiligte.liste(con, "kaiser")] == ["Dr. Lena Brückner"]  # früherer Name
    assert [e["name"] for e in beteiligte.liste(con, "Leena Brückner")] == ["Dr. Lena Brückner"]  # Tippfehler
    assert [e["name"] for e in beteiligte.liste(con, "Brükner")] == ["Dr. Lena Brückner"]
    dubletten = beteiligte.aehnliche(con, "organisation", {"name": "Autohaus Rehnfeld Gesellschaft mbH"})
    assert [(d["name"], d["stufe"]) for d in dubletten] == [("Autohaus Rehnfeld GmbH", "gleich")]
    with pytest.raises(ValueError, match="Nachnamen"):
        beteiligte.speichern(con, "person", {"vorname": "Lena"})
    with pytest.raises(ValueError, match="JJJJ-MM-TT"):
        beteiligte.speichern(con, "person", {"nachname": "X", "geburtsdatum": "1.1.1980"})


def test_liste_zaehlt_akten(con):
    lena = person(con, "Lena", "Brückner")
    stammdaten.beteiligung_hinzufuegen(con, neue_akte(con), "mandant", beteiligter_id=lena)
    person(con, "Karl", "Ohneakte")
    assert {e["name"]: e["akten_anzahl"] for e in beteiligte.liste(con)} == {"Lena Brückner": 1, "Karl Ohneakte": 0}


def test_beziehungen_und_loeschschutz(con):
    gmbh = firma(con, "Autohaus Rehnfeld GmbH")
    gf = person(con, "Klaus", "Rehnfeld")
    # Vertreter gleich beim Anlegen der Organisation: ein vorhandener und ein neuer.
    neu = beteiligte.speichern(con, "organisation", {"name": "Rehnfeld Leasing GmbH"}, vertreter=[
        {"beteiligter_id": gf, "funktion": "Geschäftsführer"},
        {"anrede": "Frau", "titel": "Dr.", "vorname": "Iris", "nachname": "Brandt", "funktion": "Geschäftsführerin"}])
    assert sorted(b["text"] for b in neu["beziehungen"]) == [
        "vertreten durch Frau Dr. Iris Brandt (Geschäftsführerin)", "vertreten durch Klaus Rehnfeld (Geschäftsführer)"]
    iris = next(b["anderer"] for b in neu["beziehungen"] if "Iris" in b["text"])
    assert [b["text"] for b in beteiligte.eintrag(con, iris)["beziehungen"]] == [
        "Geschäftsführerin von Rehnfeld Leasing GmbH"]
    # Funktion nachträglich ändern; ohne Angabe bleibt sie, "" löscht sie.
    beteiligte.beziehung_setzen(con, gf, neu["id"], "gesetzlicher_vertreter", funktion="Liquidator")
    beteiligte.beziehung_setzen(con, gf, neu["id"], "gesetzlicher_vertreter")
    assert [b["funktion"] for b in beteiligte.eintrag(con, gf)["beziehungen"]] == ["Liquidator"]
    beteiligte.beziehung_setzen(con, gf, neu["id"], "gesetzlicher_vertreter", funktion="")
    assert beteiligte.eintrag(con, gf)["beziehungen"][0]["text"] == "Gesetzlicher Vertreter von Rehnfeld Leasing GmbH"
    with pytest.raises(ValueError, match="Nachnamen"):
        beteiligte.speichern(con, "organisation", {"name": "X GmbH"}, vertreter=[{"vorname": "Ohne"}])
    with pytest.raises(ValueError, match="ist eine Person"):
        beteiligte.speichern(con, "organisation", {"name": "Y GmbH"}, vertreter=[{"beteiligter_id": neu["id"]}])
    assert not beteiligte.liste(con, "X GmbH") and not beteiligte.liste(con, "Y GmbH")
    beteiligte.beziehung_setzen(con, gf, gmbh, "gesetzlicher_vertreter")
    assert [b["text"] for b in beteiligte.eintrag(con, gmbh)["beziehungen"]] == ["vertreten durch Klaus Rehnfeld"]
    with pytest.raises(ValueError, match="Organisation"):
        beteiligte.beziehung_setzen(con, gmbh, gf, "gesetzlicher_vertreter")
    a = neue_akte(con)
    stammdaten.beteiligung_hinzufuegen(con, a, "gegner", beteiligter_id=gmbh)
    with pytest.raises(ValueError, match="an Akten beteiligt"):
        beteiligte.loeschen(con, gmbh)
    assert beteiligte.loeschen(con, gf) == {"geloescht": gf}


# --------------------------------------------------------------------------- Aktenzeichen


def test_aktenzeichen_laufend_je_jahr_und_nie_wiederverwendet(con, tmp_path):
    assert stammdaten.vorschlag(con, HEUTE)["aktenzeichen"] == "1/26"
    a1, a2 = neue_akte(con, "A"), neue_akte(con, "B")
    assert [stammdaten.stammdaten(con, a)["aktenzeichen"] for a in (a1, a2)] == ["1/26", "2/26"]
    akte.akte_loeschen(con, a2, tmp_path / "ablage")
    assert stammdaten.vorschlag(con, HEUTE)["aktenzeichen"] == "3/26"  # 2/26 bleibt vergeben
    a3 = akte.akte_anlegen(con, "C")["id"]
    with pytest.raises(ValueError, match="nicht erneut vergeben"):
        stammdaten.vergeben(con, a3, "2/26", heute=HEUTE)
    stammdaten.vergeben(con, a3, "102 / 26", heute=HEUTE)
    assert stammdaten.stammdaten(con, a3)["aktenzeichen"] == "102/26"
    assert stammdaten.vorschlag(con, HEUTE)["aktenzeichen"] == "103/26"
    assert stammdaten.vorschlag(con, date(2027, 1, 2))["aktenzeichen"] == "1/27"  # neues Jahr, neue Zählung
    with pytest.raises(ValueError, match="schon das Aktenzeichen"):
        stammdaten.vergeben(con, a3, heute=HEUTE)
    with pytest.raises(ValueError, match="Nummer/Jahr"):
        stammdaten.zerlege("2026-102")


def test_aktenzeichen_startwert_und_zusatz(con):
    stammdaten.einstellungen_setzen(con, naechste_nummer=250, aktenzeichen_zusatz="RS", heute=HEUTE)
    assert stammdaten.vorschlag(con, HEUTE)["aktenzeichen"] == "250/26 RS"
    neue_akte(con)
    with pytest.raises(ValueError, match="größer"):
        stammdaten.einstellungen_setzen(con, naechste_nummer=100, heute=HEUTE)
    assert stammdaten.zerlege("7/99", heute=HEUTE) == (7, 1999, "")


def test_stammdaten_speichern(con):
    a = neue_akte(con)
    s = stammdaten.speichern(con, a, {"gegenstand": " Rücktritt  Gebrauchtwagenkauf ", "status": "ruhend",
                                      "mandat_seit": "2025-06-20", "sachgebiet": "Kaufrecht"})
    assert (s["gegenstand"], s["status"], s["sachgebiet"]) == ("Rücktritt Gebrauchtwagenkauf", "ruhend", "Kaufrecht")
    with pytest.raises(ValueError, match="Status"):
        stammdaten.speichern(con, a, {"status": "offen"})
    with pytest.raises(ValueError, match="Kurzbezeichnung"):
        stammdaten.speichern(con, a, {"name": " "})


def test_gegenstandswert_als_zahl(con):
    for eingabe, gespeichert in (("250.000", "250000.00"), ("18.450,50 €", "18450.50"), ("1.234.567", "1234567.00"),
                                 ("1500", "1500.00"), ("99.5", "99.50"), ("  ", "")):
        assert stammdaten.betrag(eingabe) == gespeichert
    a = neue_akte(con)
    assert stammdaten.speichern(con, a, {"gegenstandswert": "250.000"})["gegenstandswert"] == "250000.00"
    assert stammdaten.speichern(con, a, {"gegenstandswert": ""})["gegenstandswert"] is None
    with pytest.raises(ValueError, match="kein Betrag"):
        stammdaten.speichern(con, a, {"gegenstandswert": "viel"})
    # Ein früher frei eingegebener Wert wird beim Öffnen umgestellt.
    con.execute("UPDATE akte SET gegenstandswert = '12.000,00 EUR' WHERE id = ?", (a,))
    stammdaten.einrichten(con)
    assert stammdaten.stammdaten(con, a)["gegenstandswert"] == "12000.00"


def test_bestehende_akte_ohne_aktenzeichen_bleibt_erhalten(tmp_path):
    alt = akte.oeffne(tmp_path / "akten.sqlite")
    akte.akte_anlegen(alt, "Testakte Ordner")
    alt.close()
    con = akte.oeffne(tmp_path / "akten.sqlite")
    eigene.einrichten(con)
    einrichten(con)
    [a] = stammdaten.uebersicht(con)
    assert (a["name"], a["aktenzeichen"], a["status"], a["mandanten"]) == ("Testakte Ordner", None, "laufend", [])
    con.close()


# --------------------------------------------------------------------------- Beteiligte der Akte


def test_beteiligte_der_akte_und_uebersicht(con):
    a = neue_akte(con)
    lena, autohaus = person(con, "Lena", "Brückner"), firma(con, "Autohaus Rehnfeld GmbH")
    gericht = firma(con, "Landgericht Freiburg im Breisgau", kategorie="Gericht")
    stammdaten.beteiligung_hinzufuegen(con, a, "gegner", beteiligter_id=autohaus)
    stammdaten.beteiligung_hinzufuegen(con, a, "mandant", beteiligter_id=lena)
    s = stammdaten.beteiligung_hinzufuegen(con, a, "gericht", beteiligter_id=gericht, aktenzeichen="3 O 412/25")
    assert [(b["rolle_text"], b["seite"], b["name"]) for b in s["beteiligte"]] == [
        ("Mandant", "eigene", "Lena Brückner"), ("Gegner", "gegen", "Autohaus Rehnfeld GmbH"),
        ("Gericht", "neutral", "Landgericht Freiburg im Breisgau")]
    assert [b["gruppe"] for b in s["beteiligte"]] == ["eigene", "gegen", "gericht"]
    with pytest.raises(ValueError, match="schon eingetragen"):
        stammdaten.beteiligung_hinzufuegen(con, a, "mandant", beteiligter_id=lena)
    [u] = stammdaten.uebersicht(con)
    assert (u["mandanten"], u["gegner"], u["gerichte"]) == (
        ["Lena Brückner"], ["Autohaus Rehnfeld GmbH"],
        [{"name": "Landgericht Freiburg im Breisgau", "aktenzeichen": "3 O 412/25"}])
    assert (u["sachbearbeiter"], u["geoeffnet_am"]) == (None, None)
    vorher = u["geaendert_am"]
    stammdaten.geoeffnet(con, a)
    [u] = stammdaten.uebersicht(con)
    assert u["geoeffnet_am"] and u["geaendert_am"] == vorher  # Öffnen gilt nicht als Bearbeiten


def test_konzerngesellschaft_als_mandant(con):
    eigene.form_setzen(con, "rechtsabteilung")
    eigene.organisation_speichern(con, {"name": "Lindenau Holding AG", "ort": "Lindenau"})
    s = eigene.einheit_speichern(con, "konzerngesellschaft", {"name": "Bäderbetriebe Lindenau GmbH", "ort": "Lindenau"})
    kg = s["id"]
    a = neue_akte(con)
    st = stammdaten.beteiligung_hinzufuegen(con, a, "mandant", eigene_organisation_id=kg)
    assert [(b["name"], b["quelle"]) for b in st["beteiligte"]] == [("Bäderbetriebe Lindenau GmbH",
                                                                     "eigene_organisation")]
    with pytest.raises(ValueError, match="Konzerngesellschaft"):
        stammdaten.beteiligung_hinzufuegen(con, a, "gegner", eigene_organisation_id=kg)
    with pytest.raises(ValueError, match="archiviert"):
        eigene.loeschen(con, "organisation", kg)


# --------------------------------------------------------------------------- Kollisionsprüfung


def test_kollision_mandant_war_gegner(con):
    alt = neue_akte(con, "Sattler ./. Wohnbau Ost")
    wohnbau = firma(con, "Wohnbau Ost GmbH")
    stammdaten.beteiligung_hinzufuegen(con, alt, "gegner", beteiligter_id=wohnbau)
    neu = neue_akte(con, "Wohnbau Ost ./. Kramer")
    assert kollision.pruefen(con, neu)["ampel"] == "gruen"
    stammdaten.beteiligung_hinzufuegen(con, neu, "mandant", beteiligter_id=wohnbau)
    p = kollision.pruefen(con, neu)
    assert p["ampel"] == "rot"
    assert p["treffer"][0]["text"] == "Wohnbau Ost GmbH ist hier Mandant; Wohnbau Ost GmbH ist in Akte 1/26 Gegner."
    # Unverändert: kein neuer Eintrag, die Entscheidung bleibt erhalten.
    with pytest.raises(ValueError, match="begründen"):
        kollision.entscheiden(con, p["id"], "kein_konflikt")
    kollision.entscheiden(con, p["id"], "kein_konflikt", "Andere Rechtssache, Mandat Sattler beendet.")
    assert kollision.pruefen(con, neu)["entscheidung"] == "kein_konflikt"
    assert len(kollision.verlauf(con, neu)) == 2


def test_kollision_nachname_und_tippfehler(con):
    alt = neue_akte(con, "Reiter ./. Nordstern")
    stammdaten.beteiligung_hinzufuegen(con, alt, "gegner", beteiligter_id=person(con, "Jonas", "Reiter"))
    for vorname in ("", "Joanas"):
        neu = neue_akte(con, f"{vorname} Reiter")
        stammdaten.beteiligung_hinzufuegen(con, neu, "mandant", beteiligter_id=person(con, vorname, "Reiter"))
        assert kollision.ermitteln(con, neu)["ampel"] == "gelb"
    anna = neue_akte(con, "Anna Reiter")
    stammdaten.beteiligung_hinzufuegen(con, anna, "mandant", beteiligter_id=person(con, "Anna", "Reiter"))
    assert kollision.ermitteln(con, anna)["ampel"] == "gruen"  # andere Vornamen: kein Treffer


def test_kollision_vorab_fuer_suchtreffer(con):
    alt = neue_akte(con, "Reiter ./. Nordstern")
    jonas, nordstern = person(con, "Jonas", "Reiter"), firma(con, "Nordstern Social GmbH")
    stammdaten.beteiligung_hinzufuegen(con, alt, "gegner", beteiligter_id=jonas)
    stammdaten.beteiligung_hinzufuegen(con, alt, "mandant", beteiligter_id=nordstern)
    neu = neue_akte(con, "Neu")
    v = kollision.vorab(con, neu, "mandant", [jonas, nordstern])
    assert list(v) == [str(jonas)] and v[str(jonas)]["ampel"] == "rot"
    assert v[str(jonas)]["texte"] == ["Jonas Reiter wäre hier Mandant; Jonas Reiter ist in Akte 1/26 Gegner."]
    assert kollision.vorab(con, neu, "zeuge", [jonas]) == {}
    # In derselben Akte: wer schon Mandant ist, ist als Gegner verdächtig.
    v = kollision.vorab(con, alt, "gegner", [nordstern])
    assert v[str(nordstern)]["ampel"] == "rot" and "in dieser Akte" in v[str(nordstern)]["texte"][0]
    assert kollision.letzte(con, neu) is None  # die Vorab-Prüfung speichert nichts


def test_kollision_gleiche_seite_ist_kein_treffer(con):
    lena = person(con, "Lena", "Brückner")
    for name in ("A", "B"):
        stammdaten.beteiligung_hinzufuegen(con, neue_akte(con, name), "mandant", beteiligter_id=lena)
    assert kollision.ermitteln(con, 1)["ampel"] == "gruen"


def test_kollision_aehnlich_vertreter_verbunden_und_geburtsdatum(con):
    alt = neue_akte(con)
    stammdaten.beteiligung_hinzufuegen(con, alt, "gegner", beteiligter_id=firma(con, "Autohaus Rehnfeld GmbH"))
    tochter = firma(con, "Rehnfeld Leasing GmbH")
    mutter = firma(con, "Rehnfeld Holding AG")
    beteiligte.beziehung_setzen(con, mutter, tochter, "verbunden")
    stammdaten.beteiligung_hinzufuegen(con, alt, "gegner", beteiligter_id=tochter)
    peter = person(con, "Peter", "Hofmann", geburtsdatum="1970-01-01")
    stammdaten.beteiligung_hinzufuegen(con, alt, "gegner", beteiligter_id=peter)

    neu = neue_akte(con, "Neu")
    stammdaten.beteiligung_hinzufuegen(con, neu, "mandant", beteiligter_id=firma(
        con, "Autohaus Rehnfeld Gesellschaft mit beschränkter Haftung", registernummer=""))
    stammdaten.beteiligung_hinzufuegen(con, neu, "mandant", beteiligter_id=mutter)
    stammdaten.beteiligung_hinzufuegen(con, neu, "mandant", beteiligter_id=person(
        con, "Peter", "Hofmann", geburtsdatum="1985-05-05"))  # gleichnamig, anderer Mensch
    e = kollision.ermitteln(con, neu)
    texte = {t["text"]: t["ampel"] for t in e["treffer"]}
    assert texte == {
        "Autohaus Rehnfeld Gesellschaft mit beschränkter Haftung ist hier Mandant; Autohaus Rehnfeld GmbH ist in "
        "Akte 1/26 Gegner.": "rot",
        "Rehnfeld Holding AG ist hier Mandant; Rehnfeld Holding AG (verbunden mit Rehnfeld Leasing GmbH) ist in "
        "Akte 1/26 Gegner.": "gelb",
        "Rehnfeld Leasing GmbH (verbunden mit Rehnfeld Holding AG) ist hier Mandant; Rehnfeld Leasing GmbH ist in "
        "Akte 1/26 Gegner.": "gelb",
    }


def test_kollision_in_derselben_akte_und_registernummer(con):
    a = neue_akte(con)
    x = firma(con, "Müller Bau GmbH", registergericht="Amtsgericht Freiburg", registernummer="HRB 123")
    y = firma(con, "Mueller Bau Gesellschaft mbH", registergericht="AG Freiburg", registernummer="HRB 999")
    stammdaten.beteiligung_hinzufuegen(con, a, "mandant", beteiligter_id=x)
    stammdaten.beteiligung_hinzufuegen(con, a, "gegner", beteiligter_id=x)
    stammdaten.beteiligung_hinzufuegen(con, a, "gegner", beteiligter_id=y)  # anderes Register: andere Firma
    e = kollision.ermitteln(con, a)
    assert [t["text"] for t in e["treffer"]] == [
        "Müller Bau GmbH ist hier Mandant; Müller Bau GmbH ist in dieser Akte Gegner."]


def test_kollision_konzerngesellschaft_auf_der_gegenseite(con):
    eigene.form_setzen(con, "rechtsabteilung")
    eigene.einheit_speichern(con, "konzerngesellschaft", {"name": "Bäderbetriebe Lindenau GmbH", "ort": "L"})
    a = neue_akte(con)
    stammdaten.beteiligung_hinzufuegen(con, a, "gegner", beteiligter_id=firma(con, "Bäderbetriebe Lindenau GmbH"))
    [t] = kollision.ermitteln(con, a)["treffer"]
    assert (t["ampel"], t["text"]) == ("gelb", "Bäderbetriebe Lindenau GmbH ist Gegner und zugleich eine eigene "
                                               "Konzerngesellschaft.")


# --------------------------------------------------------------------------- über RPC und Umgebungen


def test_rpc_und_andere_umgebung(tmp_path):
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    neu = kern.methoden["akten.anlegen"](name="Brückner ./. Autohaus")
    assert neu["aktenzeichen"].endswith(f"/{date.today().year % 100:02d}")
    with pytest.raises(ValueError, match="Nummer/Jahr"):
        kern.methoden["akten.anlegen"](name="X", aktenzeichen="abc")
    assert len(kern.methoden["akten.liste"]()) == 1  # die fehlerhafte Akte wurde nicht angelegt
    autohaus = kern.methoden["beteiligte.speichern"](art="organisation", daten={"name": "Autohaus Rehnfeld GmbH"})
    s = kern.methoden["akten.beteiligung_hinzufuegen"](akte_id=neu["id"], rolle="gegner", beteiligter_id=autohaus["id"])
    assert s["kollision"]["ampel"] == "gruen"
    assert s["kollision"]["umgebungen"] == ["Standard"]

    # Zweite Umgebung (z. B. die eigene Kanzlei neben der Rechtsabteilung): dort ist das Autohaus Mandant.
    u = kern.methoden["umgebungen.anlegen"](name="Kanzlei")
    kern.methoden["umgebungen.wechseln"](umgebung_id=u["id"])
    a2 = kern.methoden["akten.anlegen"](name="Autohaus ./. Dritter")
    b2 = kern.methoden["beteiligte.speichern"](art="organisation", daten={"name": "Autohaus Rehnfeld GmbH"})
    s2 = kern.methoden["akten.beteiligung_hinzufuegen"](akte_id=a2["id"], rolle="mandant", beteiligter_id=b2["id"])
    [t] = s2["kollision"]["treffer"]
    assert t["ampel"] == "rot" and t["dort"]["andere_umgebung"] and "(Umgebung Standard)" in t["text"]
    # Ausgenommene Umgebungen (z. B. Testdaten) werden nicht durchsucht.
    kern.methoden["akten.einstellungen_setzen"](kollision_ausgenommen=["standard"])
    assert kern.methoden["akten.kollision_pruefen"](akte_id=a2["id"])["ampel"] == "gruen"
    optionen = kern.methoden["akten.optionen"]()
    assert optionen["rollen"]["gericht"] == {"seite": "neutral", "text": "Gericht"}
    assert optionen["gruppen"]["gericht"] == "Gericht"
    kern.methoden["akten.einstellungen_setzen"](kollision_ausgenommen=[])
    v = kern.methoden["akten.kollision_vorab"](akte_id=a2["id"], rolle="gegner", beteiligter_ids=[b2["id"]])
    assert v[str(b2["id"])]["ampel"] == "rot"  # hier selbst Mandant
