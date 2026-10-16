import json
import sqlite3

import pytest

from juracore import rpc
from juracore.dokumente import akte, ansicht, suche

from .conftest import schreibe_pdf


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    yield con
    con.close()


def _lege_an(akten, con, tmp_path, akte_name, name, text):
    a = next((x for x in akte.akten(akten) if x["name"] == akte_name), None) or akte.akte_anlegen(akten, akte_name)
    (tmp_path / name).write_text(text, encoding="utf-8")
    return akte.importiere(akten, con, a["id"], tmp_path / name, tmp_path / "ablage", ocr=False)["dokument_id"], a["id"]


@pytest.mark.parametrize("eingabe, erwartet", [
    ("Rücktritt Kaufvertrag", '"Rücktritt" "Kaufvertrag"'),
    ('"VIII ZR 103/15"', '"VIII ZR 103 15"'),
    ("Nachbesser*", '"Nachbesser"*'),
    ('Frist "bis zum', '"Frist" "bis zum"'),
    ("§ 437", '"437"'),
    ('" ; "', ""),
])
def test_abfrage(eingabe, erwartet):
    assert suche.abfrage(eingabe) == erwartet


def test_suche_ueber_akten_mit_rang_und_ausschnitt(akten, con, tmp_path):
    d1, a1 = _lege_an(akten, con, tmp_path, "Brückner", "klage.md",
                      "(1) Die Klägerin erklärte den Rücktritt.\n\n(2) Der Rücktritt war wirksam; Rücktritt ist Rücktritt.")
    d2, a2 = _lege_an(akten, con, tmp_path, "Hallenbad", "brief.md", "(1) Kein Ruecktritt, sondern Rücktritt vom Vertrag.")
    _lege_an(akten, con, tmp_path, "Hallenbad", "anderes.md", "(1) Hier steht nichts davon.")

    e = suche.suche(akten, "rucktritt")  # ohne Umlaut und klein geschrieben
    assert [d["dateiname"] for d in e["dokumente"]] == ["klage.md", "brief.md"]
    assert e["treffer"] == 5 and e["seiten"] == 3  # ohne Seitenzahlen zählt jede Randnummer als Fundstelle
    klage = e["dokumente"][0]
    assert klage["akte"] == "Brückner" and klage["rang"] == 1 and klage["treffer"] == 4
    erste, zweite = klage["fundstellen"]
    assert (erste["seite"], erste["abschnitt"], erste["rn"], erste["treffer"]) == (None, 1, 1, 1)
    assert (zweite["abschnitt"], zweite["treffer"], zweite["rang"]) == (2, 3, 1)  # die meisten Treffer zuerst
    assert erste["begriffe"] == ["Rücktritt"]
    assert erste["ausschnitt"] == {"vor": "(1) Die Klägerin erklärte den ", "treffer": "Rücktritt", "nach": "."}

    assert [d["dateiname"] for d in suche.suche(akten, "Rücktritt", akte_id=a2)["dokumente"]] == ["brief.md"]
    assert suche.suche(akten, '"vom Vertrag"')["dokumente"][0]["fundstellen"][0]["begriffe"] == ["vom Vertrag"]
    assert suche.suche(akten, "Rück")["dokumente"] == []  # ohne * nur ganze Wörter
    assert len(suche.suche(akten, "Rück*")["dokumente"]) == 2
    assert suche.suche(akten, "   ")["dokumente"] == []


def test_seiten_eines_pdfs_und_markierungen(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "PDF")
    pdf = schreibe_pdf(tmp_path / "klage.pdf", [
        ["(1) Auf der ersten Seite steht nichts."],
        ["(2) Die Mechatronik ist defekt.", "Die Mechatronik wurde getauscht."],
    ])
    d = akte.importiere(akten, con, a["id"], pdf, tmp_path / "ablage", ocr=False)["dokument_id"]

    (dok,) = suche.suche(akten, "mechatronik")["dokumente"]
    (fund,) = dok["fundstellen"]
    assert (fund["seite"], fund["treffer"], fund["begriffe"]) == (2, 2, ["Mechatronik"])

    bild = ansicht.seitenbild(akten, d, 2, breite=400, begriffe=fund["begriffe"])
    assert len(bild["markierungen"]) == 2
    oben, unten = bild["markierungen"]
    assert 0 < oben["x"] < 0.5 and 0 < oben["y"] < unten["y"] < 0.2 and 0 < oben["b"] < 0.5
    assert ansicht.seitenbild(akten, d, 1, breite=400, begriffe=["Mechatronik"])["markierungen"] == []


def test_index_folgt_dem_entfernen(akten, con, tmp_path):
    d, a = _lege_an(akten, con, tmp_path, "Weg", "brief.md", "(1) Einzigartiges Wort Quasthoff.")
    assert suche.suche(akten, "Quasthoff")["treffer"] == 1
    akte.dokument_loeschen(akten, d)
    assert suche.suche(akten, "Quasthoff")["treffer"] == 0


def test_alte_akte_wird_nachindiziert(con, tmp_path):
    pfad = tmp_path / "akten.sqlite"
    alt = akte.oeffne(pfad)
    _lege_an(alt, con, tmp_path, "Alt", "brief.md", "(1) Ein Wort aus Version vier: Zwischenstand.")
    alt.executescript("DROP TABLE abschnitt_fts; DROP TRIGGER abschnitt_fts_neu; DROP TRIGGER abschnitt_fts_weg;"
                      "DROP TRIGGER abschnitt_fts_neu_text; PRAGMA user_version = 4;")
    alt.close()
    neu = akte.oeffne(pfad)
    assert suche.suche(neu, "Zwischenstand")["treffer"] == 1
    neu.close()


def test_rpc(tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    antwort = kern.bearbeite(json.dumps({"id": 1, "method": "akten.suche", "params": {"text": "x"}}))
    assert antwort["result"]["dokumente"] == []
    assert isinstance(kern.akten, sqlite3.Connection)
