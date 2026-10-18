import pytest

from juracore.rpc import Kern
from juracore.umgebungen import STANDARD, Umgebungen, kennung

from .conftest import FIXTURES


def test_kennung():
    assert kennung("Test Rechtsabteilung") == "test-rechtsabteilung"
    assert kennung("Müller & Söhne") == "mueller-soehne"
    assert kennung("Standard") == "umgebung"
    assert kennung("!!!") == "umgebung"


def test_standard_ist_der_bisherige_ordner(tmp_path):
    u = Umgebungen(tmp_path)
    liste = u.liste()
    assert liste["aktiv"] == STANDARD
    assert [e["name"] for e in liste["umgebungen"]] == ["Standard"]
    assert u.ordner() == tmp_path
    assert not (tmp_path / "umgebungen.json").exists()


def test_anlegen_umbenennen_loeschen(tmp_path):
    u = Umgebungen(tmp_path)
    a = u.anlegen("Test Kanzlei")
    b = u.anlegen("Test  kanzlei 2")
    assert (a["id"], b["id"]) == ("test-kanzlei", "test-kanzlei-2")
    assert b["name"] == "Test kanzlei 2"
    with pytest.raises(ValueError, match="gibt es schon"):
        u.anlegen("test kanzlei")
    with pytest.raises(ValueError, match="Namen"):
        u.anlegen("   ")

    u.umbenennen(STANDARD, "Echte Daten")
    u.umbenennen("test-kanzlei", "Kanzlei Muster")
    assert [e["name"] for e in u.liste()["umgebungen"]] == ["Echte Daten", "Kanzlei Muster", "Test kanzlei 2"]

    u.aktivieren("test-kanzlei")
    with pytest.raises(ValueError, match="aktive"):
        u.loeschen("test-kanzlei")
    with pytest.raises(ValueError, match="Standard"):
        u.loeschen(STANDARD)
    with pytest.raises(LookupError):
        u.loeschen("gibt-es-nicht")
    (tmp_path / "umgebungen" / "test-kanzlei-2" / "akten.sqlite").write_text("x")
    u.loeschen("test-kanzlei-2")
    assert not (tmp_path / "umgebungen" / "test-kanzlei-2").exists()
    assert [e["id"] for e in u.liste()["umgebungen"]] == [STANDARD, "test-kanzlei"]


def test_unbekannte_aktive_umgebung_faellt_auf_standard_zurueck(tmp_path):
    (tmp_path / "umgebungen.json").write_text('{"aktiv": "weg", "umgebungen": []}', encoding="utf-8")
    assert Umgebungen(tmp_path).aktiv() == STANDARD


def test_akten_getrennt_wissensbasis_gemeinsam(tmp_path):
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    kern.importieren_datei(str(FIXTURES / "bgb_auszug.xml"))
    kern.methoden["akten.anlegen"]("Akte im Standard")

    test = kern.methoden["umgebungen.anlegen"]("Test Rechtsabteilung")
    liste = kern.methoden["umgebungen.wechseln"](test["id"])
    assert liste["aktiv"] == "test-rechtsabteilung"
    assert kern.methoden["akten.liste"]() == []
    assert kern.methoden["zitat.aufloesen"]("§ 823 Abs. 2 BGB")["status"] == "belegt"
    kern.methoden["akten.anlegen"]("Akte im Test")
    assert (tmp_path / "umgebungen" / "test-rechtsabteilung" / "akten.sqlite").exists()

    kern.methoden["umgebungen.wechseln"](STANDARD)
    assert [a["name"] for a in kern.methoden["akten.liste"]()] == ["Akte im Standard"]

    # Die Wahl bleibt über einen Neustart erhalten.
    kern.methoden["umgebungen.wechseln"](test["id"])
    neu = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    assert [a["name"] for a in neu.methoden["akten.liste"]()] == ["Akte im Test"]


def test_kein_wechsel_waehrend_einer_analyse(tmp_path):
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    test = kern.methoden["umgebungen.anlegen"]("Test")
    kern.auftraege.laufend = lambda: object()
    with pytest.raises(RuntimeError, match="Analyse läuft"):
        kern.umgebung_wechseln(test["id"])
    assert kern.umgebungen.aktiv() == STANDARD
