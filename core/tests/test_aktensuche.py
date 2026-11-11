"""Suche in der Akte: Notizen, Fristen und Termine, Stammdaten und Verfahren, Beteiligte, Zeiten."""

import pytest

from juracore import zeiterfassung
from juracore.aktenverwaltung import aktensuche, beteiligte, einrichten, kalender, notizen, stammdaten, verfahren
from juracore.dokumente import akte
from juracore.eigene import daten as eigene
from juracore.schriftstuecke import kostennote


@pytest.fixture
def con(tmp_path):
    verbindung = akte.oeffne(tmp_path / "akten.sqlite")
    eigene.einrichten(verbindung)
    einrichten(verbindung)
    kostennote.einrichten(verbindung)
    zeiterfassung.einrichten(verbindung)
    yield verbindung
    verbindung.close()


@pytest.fixture
def akten(con):
    """Akte Brückner mit Einträgen in allen Bereichen, dazu eine zweite Akte, die nie gefunden werden darf."""
    a = akte.akte_anlegen(con, "Brückner ./. Autohaus Rehnfeld")["id"]
    stammdaten.speichern(con, a, {"gegenstand": "Rücktritt vom Kaufvertrag über einen Gebrauchtwagen"})
    lena = beteiligte.speichern(con, "person", {"vorname": "Lena", "nachname": "Brückner", "ort": "Freiburg",
                                                "email": "lena@beispiel.test"})["id"]
    stammdaten.beteiligung_hinzufuegen(con, a, "mandant", beteiligter_id=lena)
    verfahren.speichern(con, a, {"art": "klage", "gericht": "Landgericht Freiburg im Breisgau",
                                 "aktenzeichen": "2 O 233/26"})
    notizen.speichern(con, a, "Terminsprotokoll\n\nZeuge bestätigt die Mechatronik-Störung.")
    kalender.speichern(con, a, {"art": "frist", "titel": "Replik", "datum": "2026-12-01",
                                "notiz": "Stellungnahme zum Gutachten"})
    e = zeiterfassung.bearbeiter_speichern(con, "RA Staab")
    bearbeiter = next(x["id"] for x in e["bearbeiter"] if x["name"] == "RA Staab")
    zeiterfassung.speichern(con, a, {"datum": "2026-11-10", "minuten": 30, "taetigkeit": "Telefonat Mandantin",
                                     "bearbeiter_id": bearbeiter})
    b = akte.akte_anlegen(con, "Andere Akte")["id"]
    notizen.speichern(con, b, "Mechatronik auch hier")
    return a, b


def test_findet_in_allen_bereichen_nur_dieser_akte(con, akten):
    a, b = akten
    # Groß/klein, Umlaute und Wortteile spielen keine Rolle.
    t = aktensuche.suche(con, a, "mechatronik")["treffer"]
    assert [(x["bereich"], x["reiter"], x["art"], x["titel"]) for x in t] == [
        ("notizen", "notizen", "Notiz", "Terminsprotokoll")]
    assert t[0]["ausschnitt"]["treffer"] == "Mechatronik"
    assert t[0]["ausschnitt"]["vor"].endswith("Zeuge bestätigt die ")
    assert [x["bereich"] for x in aktensuche.suche(con, b, "Mechatronik")["treffer"]] == ["notizen"]

    assert [x["bereich"] for x in aktensuche.suche(con, a, "gutachten")["treffer"]] == ["fristen"]
    assert [x["bereich"] for x in aktensuche.suche(con, a, "kaufvertrag")["treffer"]] == ["stammdaten"]
    v = aktensuche.suche(con, a, "2 O 233")["treffer"]
    # Das Gericht des Verfahrens wird Beteiligter mit dem gerichtlichen Aktenzeichen.
    assert [(x["art"], x["reiter"]) for x in v] == [("Verfahren", "stammdaten"), ("Gericht", "beteiligte")]
    assert v[0]["titel"].startswith("Klageverfahren")
    # Beteiligte auch über die Angaben im Verzeichnis (Ort, E-Mail).
    t = aktensuche.suche(con, a, "beispiel.test")["treffer"]
    assert [(x["bereich"], x["art"], x["titel"], x["feld"]) for x in t] == [
        ("beteiligte", "Mandant", "Lena Brückner", "Email")]
    assert [x["bereich"] for x in aktensuche.suche(con, a, "telefonat")["treffer"]] == ["zeiten"]
    # Brückner steht im Namen der Akte und beim Beteiligten.
    assert {x["bereich"] for x in aktensuche.suche(con, a, "bruckner")["treffer"]} == {"stammdaten", "beteiligte"}


def test_alle_woerter_und_bereiche(con, akten):
    a, _ = akten
    assert aktensuche.suche(con, a, "Replik Gutachten")["treffer"][0]["feld"] == "Bezeichnung"
    assert aktensuche.suche(con, a, "Replik Mechatronik")["treffer"] == []
    assert aktensuche.suche(con, a, '"*protokoll*"')["treffer"][0]["bereich"] == "notizen"
    assert aktensuche.suche(con, a, "Freiburg", ["beteiligte"])["treffer"][0]["bereich"] == "beteiligte"
    assert aktensuche.suche(con, a, "  ")["treffer"] == []
    with pytest.raises(ValueError):
        aktensuche.suche(con, a, "x", ["dokumente"])
    with pytest.raises(LookupError):
        aktensuche.suche(con, 999, "x")
