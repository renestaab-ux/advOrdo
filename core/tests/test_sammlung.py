"""Sammlung der Entscheidungen (Bereich „Rechtsprechung“): ohne Akte, Zuordnung, Lösen, Suche."""

import json
import sqlite3

import pytest

from juracore import rpc
from juracore.dokumente import akte, urteile

from .test_urteile import AUSDRUCK


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    yield con
    con.close()


def _ausdruck(tmp_path, name="juris-ausdruck.txt", text=AUSDRUCK):
    datei = tmp_path / name
    datei.write_text(text, encoding="utf-8")
    return datei


def _ohne_akte(akten, tmp_path, **felder):
    felder = {"gericht": "BGH", "aktenzeichen": "VIII ZR 999/20", "datum": "2021-03-17", "herkunft": "juris"} | felder
    return urteile.ergaenzen(akten, None, _ausdruck(tmp_path), tmp_path / "ablage", ocr=False, **felder)


def test_eigene_datei_ohne_akte(akten, tmp_path):
    u = _ohne_akte(akten, tmp_path)
    assert u["neu"] is True
    (abgelegt,) = (tmp_path / "ablage" / urteile.SAMMLUNG).iterdir()
    assert abgelegt.read_text(encoding="utf-8") == AUSDRUCK
    # Dieselbe Datei noch einmal: nichts doppelt, auch ohne Akte.
    assert _ohne_akte(akten, tmp_path)["neu"] is False
    (eintrag,) = urteile.sammlung(akten)
    assert (eintrag["id"], eintrag["akte_id"], eintrag["zugeordnet"], eintrag["akten"]) == (u["urteil_id"], None, False, [])
    assert eintrag["herkunft"] == "juris" and eintrag["quelle"] == urteile.MANUELL


def test_zuordnen_und_loesen(akten, tmp_path):
    a = akte.akte_anlegen(akten, "Brückner")["id"]
    b = akte.akte_anlegen(akten, "Weber")["id"]
    u = _ohne_akte(akten, tmp_path)["urteil_id"]
    ablage = tmp_path / "ablage"

    # Erste Zuordnung: dieselbe Zeile wandert zur Akte, die Datei in deren Ablage.
    assert urteile.zuordnen(akten, u, a, ablage) == {"urteil_id": u, "neu": True}
    assert not list((ablage / urteile.SAMMLUNG).iterdir())
    assert [x["id"] for x in urteile.liste(akten, a)] == [u]
    # Zweite Akte: eigene Zeile mit eigener Kopie und denselben Absätzen.
    zweite = urteile.zuordnen(akten, u, b, ablage)
    assert zweite["neu"] is True and zweite["urteil_id"] != u
    assert (ablage / f"akte-{b}" / "urteile").is_dir()
    assert urteile.zuordnen(akten, u, b, ablage)["neu"] is False
    assert urteile.randnummern(akten, zweite["urteil_id"]) == {1, 2}

    (eintrag,) = urteile.sammlung(akten)
    assert [(x["akte_id"], x["name"]) for x in eintrag["akten"]] == [(a, "Brückner"), (b, "Weber")]

    # Akte löschen: die andere Zuordnung behält ihre Datei und ihren Text.
    akte.akte_loeschen(akten, a, ablage)
    (eintrag,) = urteile.sammlung(akten)
    assert [x["akte_id"] for x in eintrag["akten"]] == [b]
    assert urteile.volltext(akten, zweite["urteil_id"])["abschnitte"]

    # Letzte Zuordnung lösen: steht wieder „nicht zugeordnet“ in der Sammlung.
    assert urteile.loesen(akten, zweite["urteil_id"], ablage)["geloest"] is True
    (eintrag,) = urteile.sammlung(akten)
    assert eintrag["zugeordnet"] is False and eintrag["zitat"] is None
    assert len(list((ablage / urteile.SAMMLUNG).iterdir())) == 1
    assert urteile.liste(akten, b) == []


def test_loesen_bei_mehreren_akten_entfernt_nur_die_zuordnung(akten, tmp_path):
    a = akte.akte_anlegen(akten, "A")["id"]
    b = akte.akte_anlegen(akten, "B")["id"]
    u = _ohne_akte(akten, tmp_path)["urteil_id"]
    urteile.zuordnen(akten, u, a, tmp_path / "ablage")
    zweite = urteile.zuordnen(akten, u, b, tmp_path / "ablage")["urteil_id"]
    urteile.loesen(akten, zweite, tmp_path / "ablage")
    (eintrag,) = urteile.sammlung(akten)
    assert [x["akte_id"] for x in eintrag["akten"]] == [a]
    assert not (tmp_path / "ablage" / f"akte-{b}" / "urteile").exists() or not list(
        (tmp_path / "ablage" / f"akte-{b}" / "urteile").iterdir())


def test_aus_sammlung_entfernen(akten, tmp_path):
    a = akte.akte_anlegen(akten, "A")["id"]
    u = _ohne_akte(akten, tmp_path)["urteil_id"]
    urteile.zuordnen(akten, u, a, tmp_path / "ablage")
    urteile.ergaenzen(akten, None, _ausdruck(tmp_path), tmp_path / "ablage", gericht="BGH", ocr=False)
    assert urteile.aus_sammlung_entfernen(akten, u, tmp_path / "ablage")["entfernt"] == 2
    assert urteile.sammlung(akten) == []
    assert urteile.suche(akten, "Berufungsgericht")["urteile"] == []


def test_suche_in_gespeicherten_entscheidungen(akten, tmp_path):
    a = akte.akte_anlegen(akten, "A")["id"]
    u = _ohne_akte(akten, tmp_path)["urteil_id"]
    urteile.zuordnen(akten, u, a, tmp_path / "ablage")
    urteile.zuordnen(akten, u, akte.akte_anlegen(akten, "B")["id"], tmp_path / "ablage")
    anderes = urteile.ergaenzen(akten, None, _ausdruck(tmp_path, "olg.txt", "OLG Hamm\n\n(1) Ein Werkvertrag."),
                                tmp_path / "ablage", gericht="OLG Hamm", ocr=False)["urteil_id"]

    ergebnis = urteile.suche(akten, "berufungsgericht wort")
    # Kopien in weiteren Akten zählen nicht doppelt; die Fundstelle trägt die Randnummer.
    (treffer,) = ergebnis["urteile"]
    assert [f["rn"] for f in treffer["fundstellen"]] == [2]
    assert treffer["fundstellen"][0]["ausschnitt"]["treffer"].casefold() in ("berufungsgericht", "wort")
    assert treffer["sha256"] == next(e["sha256"] for e in urteile.sammlung(akten) if e["id"] != anderes)
    assert treffer["id"] != anderes and treffer["gericht"]  # Angaben für die Trefferliste im Bereich „Suche“
    assert urteile.suche(akten, "Werkv*")["urteile"][0]["sha256"] == next(
        e["sha256"] for e in urteile.sammlung(akten) if e["id"] == anderes)
    assert urteile.suche(akten, "  ") == {"urteile": [], "treffer": 0}


def test_akten_aus_version_7_werden_umgestellt(tmp_path):
    """Alte Akten: urteil.akte_id war NOT NULL, ohne Suchindex. Zeilen, Nummern und Absätze bleiben erhalten."""
    pfad = tmp_path / "alt.sqlite"
    con = akte.oeffne(pfad)
    a = akte.akte_anlegen(con, "Alt")["id"]
    u = urteile.ergaenzen(con, a, _ausdruck(tmp_path), tmp_path / "ablage", gericht="BGH", ocr=False)["urteil_id"]
    # Zustand von Version 7 nachbauen.
    alt = urteile.volltext(con, u)
    con.executescript("DROP TABLE urteil_fts; DROP TRIGGER urteil_fts_neu; DROP TRIGGER urteil_fts_weg;"
                      "PRAGMA foreign_keys = OFF;")
    con.execute(akte._URTEIL.format(name="urteil_alt").replace(
        "akte_id         INTEGER REFERENCES", "akte_id         INTEGER NOT NULL REFERENCES"))
    con.executescript("INSERT INTO urteil_alt SELECT * FROM urteil; DROP TABLE urteil;"
                      "ALTER TABLE urteil_alt RENAME TO urteil; PRAGMA user_version = 7;")
    con.close()
    assert next(z for z in sqlite3.connect(pfad).execute("PRAGMA table_info(urteil)") if z[1] == "akte_id")[3] == 1

    con = akte.oeffne(pfad)
    assert next(z for z in con.execute("PRAGMA table_info(urteil)") if z["name"] == "akte_id")["notnull"] == 0
    assert urteile.volltext(con, u) == alt
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert urteile.suche(con, "Berufungsgericht")["urteile"]
    # Fremdschlüssel greifen wieder: Akte löschen nimmt ihre Entscheidung mit.
    akte.akte_loeschen(con, a, tmp_path / "ablage")
    assert urteile.sammlung(con) == []
    assert con.execute("SELECT COUNT(*) FROM urteil_abschnitt").fetchone()[0] == 0
    # Der Suchindex folgt auch dem Löschen über den Fremdschlüssel.
    con.execute("INSERT INTO urteil_fts (urteil_fts) VALUES ('integrity-check')")
    assert con.execute("SELECT COUNT(*) FROM urteil_fts WHERE urteil_fts MATCH 'Revision'").fetchone()[0] == 0
    con.close()


def test_rpc_sammlung(tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")

    def rufe(methode, **params):
        antwort = kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))
        assert "error" not in antwort, antwort
        return antwort["result"]

    a = rufe("akten.anlegen", name="Test")
    u = rufe("rechtsprechung.ergaenzen", pfad=str(_ausdruck(tmp_path)), gericht="BGH", herkunft="juris")
    assert [e["zugeordnet"] for e in rufe("rechtsprechung.sammlung")] == [False]
    rufe("rechtsprechung.zuordnen", urteil_id=u["urteil_id"], akte_id=a["id"])
    assert rufe("rechtsprechung.sammlung")[0]["akten"][0]["akte_id"] == a["id"]
    assert rufe("rechtsprechung.suche", suchtext="Revision")["urteile"]
    # Suche in der Akte: nur die Entscheidungen, die ihr zugeordnet sind.
    assert rufe("rechtsprechung.suche", suchtext="Revision", akte_id=a["id"])["urteile"]
    andere = rufe("akten.anlegen", name="Andere")
    assert rufe("rechtsprechung.suche", suchtext="Revision", akte_id=andere["id"])["urteile"] == []
    assert rufe("akten.aktensuche", akte_id=a["id"], text="Test")["treffer"][0]["bereich"] == "stammdaten"
    rufe("rechtsprechung.loesen", urteil_id=u["urteil_id"])
    assert rufe("rechtsprechung.entfernen", urteil_id=u["urteil_id"])["entfernt"] == 1
    assert rufe("rechtsprechung.sammlung") == []


def test_zur_bearbeitung_zugeordnet(akten, con, tmp_path):
    """Aus der Sammlung zugeordnet, aber in keinem Dokument der Akte zitiert: eigener Abschnitt in der Akte."""
    from .test_urteile import _akte

    akte_id = _akte(akten, con, tmp_path)  # Replik zitiert u. a. BGH VIII ZR 103/15
    zitiert = urteile.ergaenzen(akten, None, _ausdruck(tmp_path, "bgh.txt", "BGH\n\n(1) Zitiert."),
                                tmp_path / "ablage", gericht="BGH", aktenzeichen="VIII ZR 103/15", ocr=False)
    frei = _ohne_akte(akten, tmp_path, aktenzeichen="I ZR 130/25")
    urteile.zuordnen(akten, zitiert["urteil_id"], akte_id, tmp_path / "ablage")
    urteile.zuordnen(akten, frei["urteil_id"], akte_id, tmp_path / "ablage")
    assert [u["id"] for u in urteile.zur_bearbeitung(akten, con, akte_id)] == [frei["urteil_id"]]
    # Das zitierte erscheint beim Zitat in der Akte.
    assert any(g["urteil"] and g["urteil"]["id"] == zitiert["urteil_id"]
               for g in akte.rechtsprechung(akten, con, akte_id))
