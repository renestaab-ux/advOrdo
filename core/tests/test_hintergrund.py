"""Lange Befehle im Hintergrund: Der Kern bleibt währenddessen ansprechbar (Issue #83)."""

import json
import threading
import time
import urllib.request

import pytest

from juracore import hintergrund, netzprotokoll
from juracore.rpc import Kern

from .conftest import FIXTURES


@pytest.fixture
def kern(tmp_path):
    k = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    yield k
    netzprotokoll.einrichten(None)


def rufe(kern, name, **params):
    antwort = kern.bearbeite(json.dumps({"id": 1, "method": name, "params": params}))
    assert "error" not in antwort, antwort
    return antwort["result"]


def warte(kern, auftrag_id, sekunden=10):
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        stand = rufe(kern, "hintergrund.auftrag", auftrag_id=auftrag_id)
        if stand["status"] != "laeuft":
            return stand
        time.sleep(0.02)
    raise AssertionError("Auftrag wurde nicht fertig")


def test_import_im_hintergrund_mit_eigener_verbindung(kern):
    a = rufe(kern, "hintergrund.starten", methode="gesetze.importieren_datei",
             params={"pfad": str(FIXTURES / "zpo_auszug.xml")})
    assert a["status"] == "laeuft" and a["titel"] == "Gesetz aus Datei laden"
    stand = warte(kern, a["auftrag_id"])
    assert stand["status"] == "fertig", stand
    assert stand["ergebnis"]["abk"] == "ZPO"
    # Der Hauptthread sieht, was der Auftrag mit seiner eigenen Verbindung gespeichert hat.
    assert [g["abk"] for g in rufe(kern, "gesetze.liste")] == ["ZPO"]
    assert rufe(kern, "hintergrund.laufend") == []


def test_kern_antwortet_waehrend_ein_befehl_laeuft(kern):
    frei, begonnen = threading.Event(), threading.Event()
    gesehen = {}

    def langsam():
        gesehen["eigene_verbindung"] = kern.con is not kern._con and kern.akten is not kern._akten
        begonnen.set()
        frei.wait(5)
        return {"geladen": 1}

    kern.methoden["gerichte.laden"] = langsam
    a = rufe(kern, "hintergrund.starten", methode="gerichte.laden")
    assert begonnen.wait(5)
    # Andere Aufrufe kommen sofort durch, auch ein zweiter Hintergrundbefehl anderer Art.
    assert "version" in rufe(kern, "ping")
    assert rufe(kern, "akten.liste") == []
    assert [x["aufgabe"] for x in rufe(kern, "hintergrund.laufend")] == ["gerichte.laden"]
    # Derselbe Befehl läuft nur einmal.
    doppelt = kern.bearbeite(json.dumps({"id": 2, "method": "hintergrund.starten",
                                         "params": {"methode": "gerichte.laden"}}))
    assert "läuft schon" in doppelt["error"]["message"]
    # Die Arbeitsumgebung wechselt nicht unter einem laufenden Auftrag weg.
    wechsel = kern.bearbeite(json.dumps({"id": 3, "method": "umgebungen.wechseln", "params": {"umgebung_id": "x"}}))
    assert "Gerichtsverzeichnis laden" in wechsel["error"]["message"]
    frei.set()
    stand = warte(kern, a["auftrag_id"])
    assert stand["status"] == "fertig" and stand["ergebnis"] == {"geladen": 1}
    assert gesehen["eigene_verbindung"] is True
    assert kern.con is kern._con  # im Hauptthread wieder die eigene


def test_abbrechen_verwirft_das_ergebnis(kern):
    frei = threading.Event()
    kern.methoden["rechtsprechung.laden"] = lambda: (frei.wait(5), {"neu": 3})[1]
    a = rufe(kern, "hintergrund.starten", methode="rechtsprechung.laden")
    assert rufe(kern, "hintergrund.abbrechen", auftrag_id=a["auftrag_id"])["text"] == "Wird abgebrochen …"
    frei.set()
    stand = warte(kern, a["auftrag_id"])
    assert stand["status"] == "abgebrochen" and stand["ergebnis"] is None


def test_abbruch_vor_der_naechsten_verbindung(kern, tmp_path):
    """Nach dem Abbruch baut der Auftrag keine Verbindung mehr auf und schreibt keinen Protokolleintrag."""
    h = hintergrund.Hintergrund()
    versuche = []

    def arbeit():
        auftrag = next(iter(h._auftraege.values()))
        auftrag._abbruch.set()
        versuche.append(1)
        urllib.request.urlopen("http://nicht-erreichbar.invalid/", timeout=1)
        versuche.append(2)

    stand = h.starte("akten.online_pruefen", arbeit, warten=True)
    assert stand["status"] == "abgebrochen"
    assert versuche == [1]
    assert not kern.netzprotokoll_datei.exists()


def test_fehler_und_unbekannte_befehle(kern):
    a = rufe(kern, "hintergrund.starten", methode="gesetze.importieren_datei",
             params={"pfad": str(FIXTURES / "gibt-es-nicht.xml")})
    stand = warte(kern, a["auftrag_id"])
    assert stand["status"] == "fehler" and stand["fehler"]
    falsch = kern.bearbeite(json.dumps({"id": 1, "method": "hintergrund.starten",
                                        "params": {"methode": "akten.loeschen", "params": {"akte_id": 1}}}))
    assert "nicht im Hintergrund" in falsch["error"]["message"]


def test_import_meldet_fortschritt_je_gesetz(kern, monkeypatch):
    staende = []

    def lade(abk, archiv, gesetze=None):
        staende.append(kern.hintergrund.laufend()[0]["text"])
        raise OSError("offline")

    monkeypatch.setattr("juracore.gesetze.quelle.lade_gesetz", lade)
    a = kern.hintergrund_starten("gesetze.importieren", {"gesetze": ["bgb", "zpo"]})
    stand = warte(kern, a["auftrag_id"])
    assert stand["status"] == "fertig"
    assert [e["fehler"] for e in stand["ergebnis"]] == ["offline", "offline"]
    assert staende == ["Lade BGB (1 von 2) …", "Lade ZPO (2 von 2) …"]


def test_dokumente_einlesen_im_hintergrund(kern, tmp_path):
    """Dokumente werden als Hintergrundauftrag eingelesen; eine unlesbare Datei hält die übrigen nicht auf."""
    akte_id = kern.akte_anlegen("Testakte", ohne_aktenzeichen=True)["id"]
    a = tmp_path / "a.txt"
    a.write_text("Erster Schriftsatz.\n\nZweiter Absatz.", encoding="utf-8")
    b = tmp_path / "b.md"
    b.write_text("# Antwort\n\nText.", encoding="utf-8")
    dateien = [{"pfad": str(a), "name": "a.txt"}, {"pfad": str(tmp_path / "fehlt.pdf"), "name": "fehlt.pdf"},
               {"pfad": str(b), "name": "unter/b.md", "tags": ["Gegner"], "herkunft": "unter"},
               {"pfad": str(a), "name": "a.txt"}]
    auftrag = rufe(kern, "hintergrund.starten", methode="akten.importieren_dateien",
                   params={"akte_id": akte_id, "dateien": dateien})
    assert rufe(kern, "ping")["version"]  # der Kern bleibt ansprechbar
    stand = warte(kern, auftrag["auftrag_id"])
    assert stand["status"] == "fertig", stand
    ergebnisse = stand["ergebnis"]["ergebnisse"]
    assert [e["name"] for e in ergebnisse] == ["a.txt", "fehlt.pdf", "unter/b.md", "a.txt"]
    assert ergebnisse[0]["neu"] is True and "fehler" not in ergebnisse[0]
    assert "nicht gefunden" in ergebnisse[1]["fehler"]
    assert ergebnisse[3]["neu"] is False and ergebnisse[3]["dokument_id"] == ergebnisse[0]["dokument_id"]
    assert len(rufe(kern, "akten.dokumente", akte_id=akte_id)) == 2


def test_dokumente_einlesen_abbrechen_behaelt_eingelesene(kern, tmp_path, monkeypatch):
    akte_id = kern.akte_anlegen("Testakte", ohne_aktenzeichen=True)["id"]
    dateien = []
    for n in range(3):
        p = tmp_path / f"d{n}.txt"
        p.write_text(f"Dokument {n}.", encoding="utf-8")
        dateien.append({"pfad": str(p), "name": p.name})
    from juracore.dokumente import akte

    echt = akte.importiere

    def importiere(*args, **kwargs):
        r = echt(*args, **kwargs)
        kern.hintergrund.abbrechen(kern.hintergrund.laufend()[0]["auftrag_id"])  # nach der ersten Datei
        return r

    monkeypatch.setattr(akte, "importiere", importiere)
    a = kern.hintergrund_starten("akten.importieren_dateien", {"akte_id": akte_id, "dateien": dateien})
    stand = warte(kern, a["auftrag_id"])
    assert stand["status"] == "abgebrochen"
    assert len(rufe(kern, "akten.dokumente", akte_id=akte_id)) == 1
