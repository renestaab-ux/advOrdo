import io
import json
import sqlite3
import zipfile

import pytest

from juracore import rpc
from juracore.dokumente import akte, urteile
from juracore.rechtsprechung import verzeichnis, volltext

from .conftest import FIXTURES
from .test_rechtsprechung import KLAGE, REPLIK

# Fiktiver Ausdruck einer Entscheidung, wie man ihn aus einer Datenbank speichert.
AUSDRUCK = """BGH, Urteil vom 17.03.2021 – VIII ZR 999/20

Tenor

Die Revision wird zurückgewiesen.

Gründe

(1) Die Klägerin verlangt die Rückabwicklung eines Kaufvertrags.

(2) Das Berufungsgericht hat die Erklärung als letztes Wort des Verkäufers verstanden.
"""


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    yield con
    con.close()


def _akte(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Brückner")
    (tmp_path / "07_Replik.md").write_text(f"(28) {REPLIK}\n\n(29) {KLAGE}", encoding="utf-8")
    akte.importiere(akten, con, a["id"], tmp_path / "07_Replik.md", tmp_path / "ablage", ocr=False)
    return a["id"]


def _ergaenze(akten, akte_id, tmp_path, **felder):
    datei = tmp_path / "juris-ausdruck.txt"
    datei.write_text(AUSDRUCK, encoding="utf-8")
    return urteile.ergaenzen(akten, akte_id, datei, tmp_path / "ablage", ocr=False, **felder)


def test_nicht_gefundenes_urteil_selbst_ergaenzen(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    zitat = "BGH, Urteil vom 17.03.2021 – VIII ZR 999/20"
    ergebnis = _ergaenze(akten, akte_id, tmp_path, gericht="BGH", aktenzeichen="VIII ZR 999 / 20",
                         datum="2021-03-17", zitat=zitat, herkunft="juris")
    assert ergebnis["neu"] is True
    # Unverändert abgelegt, in einem eigenen Ordner der Akte.
    (abgelegt,) = (tmp_path / "ablage" / f"akte-{akte_id}" / "urteile").iterdir()
    assert abgelegt.read_text(encoding="utf-8") == AUSDRUCK
    # Dieselbe Datei noch einmal: nichts doppelt.
    assert _ergaenze(akten, akte_id, tmp_path, gericht="BGH")["neu"] is False

    liste = akte.rechtsprechung(akten, con, akte_id)
    eintrag = next(e for e in liste if e["zitat"] == zitat)
    assert eintrag["status"] == "kein_verzeichnis"  # Prüfergebnis bleibt, der Volltext kommt dazu
    assert eintrag["urteil"]["herkunft"] == "juris" and eintrag["urteil"]["quelle"] == urteile.MANUELL

    text = urteile.volltext(akten, eintrag["urteil"]["id"])
    assert [a["rn"] for a in text["abschnitte"] if a["rn"]] == [1, 2]
    assert "letztes Wort" in next(a["text"] for a in text["abschnitte"] if a["rn"] == 2)


def test_offene_zitate_zuerst(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    _ergaenze(akten, akte_id, tmp_path, gericht="BGH", aktenzeichen="VIII ZR 103/15")
    # Gleicher Status: das ältere, aber schon ergänzte Urteil rückt hinter das offene.
    assert [e["zitat"] for e in akte.rechtsprechung(akten, con, akte_id) if e["status"] == "kein_verzeichnis"] == [
        "BGH, Urteil vom 17.03.2021 – VIII ZR 999/20", "BGH, Urteil vom 12.10.2016 – VIII ZR 103/15"]


def test_ergaenztes_urteil_gilt_fuer_gleiches_aktenzeichen():
    vorhanden = [{"zitat": "BGH, Urteil vom 17.03.2021 – VIII ZR 999/20", "gericht": "BGH",
                  "aktenzeichen": "VIII ZR 999/20"}]
    assert urteile.zu_zitat(vorhanden, "BGH – VIII ZR 999/20", "BGH", "viii zr 999 / 20") is vorhanden[0]
    assert urteile.zu_zitat(vorhanden, "BAG – VIII ZR 999/20", "BAG", "VIII ZR 999/20") is None
    assert urteile.zu_zitat(vorhanden, "BGH – VIII ZR 1/20", "BGH", "VIII ZR 1/20") is None


def test_entfernen_und_akte_loeschen(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    u = _ergaenze(akten, akte_id, tmp_path, gericht="OLG Hamm", aktenzeichen="28 U 1/18")
    ordner = tmp_path / "ablage" / f"akte-{akte_id}" / "urteile"
    assert urteile.entfernen(akten, u["urteil_id"], tmp_path / "ablage")["hinweis"] is None
    assert list(ordner.iterdir()) == [] and urteile.liste(akten, akte_id) == []
    assert (tmp_path / "juris-ausdruck.txt").exists()  # die eigene Datei bleibt

    _ergaenze(akten, akte_id, tmp_path, gericht="OLG Hamm")
    akte.akte_loeschen(akten, akte_id, tmp_path / "ablage")
    assert akten.execute("SELECT COUNT(*) FROM urteil_abschnitt").fetchone()[0] == 0


def test_ohne_gericht_oder_text(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    with pytest.raises(ValueError, match="Gericht"):
        _ergaenze(akten, akte_id, tmp_path, gericht="  ")
    leer = tmp_path / "leer.txt"
    leer.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="kein Text"):
        urteile.ergaenzen(akten, akte_id, leer, tmp_path / "ablage", gericht="BGH", ocr=False)


def test_rpc(tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    a = kern.bearbeite(json.dumps({"id": 1, "method": "akten.anlegen", "params": {"name": "Test"}}))["result"]
    datei = tmp_path / "beck.txt"
    datei.write_text(AUSDRUCK, encoding="utf-8")
    u = kern.bearbeite(json.dumps({"id": 2, "method": "akten.urteil_ergaenzen", "params": {
        "akte_id": a["id"], "pfad": str(datei), "gericht": "BGH", "aktenzeichen": "VIII ZR 999/20",
        "herkunft": "beck-online"}}))["result"]
    assert [x["herkunft"] for x in urteile.liste(kern.akten, a["id"])] == ["beck-online"]
    eigene = kern.bearbeite(json.dumps({"id": 6, "method": "rechtsprechung.eigene"}))["result"]
    assert eigene == {"gesamt": 1, "quellen": [{"quelle": "manuell", "herkunft": "beck-online", "anzahl": 1}]}
    text = kern.bearbeite(json.dumps({"id": 4, "method": "akten.urteil", "params": {"urteil_id": u["urteil_id"]}}))
    assert text["result"]["dateiname"] == "beck.txt"
    weg = kern.bearbeite(json.dumps({"id": 5, "method": "akten.urteil_entfernen",
                                     "params": {"urteil_id": u["urteil_id"]}}))
    assert weg["result"]["hinweis"] is None


# --- Volltexte von rechtsprechung-im-internet.de -------------------------------------------------

def _zip_auszug() -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        # Fester Zeitstempel: Sonst unterscheiden sich zwei Aufrufe, wenn eine Sekundengrenze dazwischen liegt.
        z.writestr(zipfile.ZipInfo("jb-KORE301892016.xml", (2026, 1, 1, 0, 0, 0)), (FIXTURES / "rii_volltext_auszug.xml").read_bytes())
    return puffer.getvalue()


def test_volltext_lesen():
    v = volltext.lies(_zip_auszug())
    assert (v.gericht, v.spruchkoerper, v.datum, v.aktenzeichen, v.doktyp) == (
        "BGH", "8. Zivilsenat", "2016-10-12", "VIII ZR 103/15", "Urteil")
    assert v.vorinstanz[0] == "vorgehend OLG Frankfurt, 14. April 2015, Az: 10 U 133/13"
    assert v.randnummern == [1, 5, 6, 22]
    assert [a.teil for a in v.absaetze][:3] == ["leitsatz", "tenor", "tatbestand"]
    assert v.absaetze[0].text.startswith("1. § 476 BGB ist richtlinienkonform")
    with pytest.raises(ValueError, match="kein lesbares XML"):
        volltext.lies(b"<html>Wartung")
    with pytest.raises(ValueError, match="Dokumentnummer"):
        volltext.adresse("../x")


def test_volltexte_der_akte_laden(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Brückner")
    text = (f"(13) {KLAGE}\n\n(14) Ebenso BGH, Urteil vom 12.10.2016 – VIII ZR 103/15, Rn. 22.\n\n"
            "(15) Vgl. BGH, Urteil vom 12.10.2016 – VIII ZR 103/15, Rn. 99.")
    (tmp_path / "05_Klage.md").write_text(text, encoding="utf-8")
    akte.importiere(akten, con, a["id"], tmp_path / "05_Klage.md", tmp_path / "ablage", ocr=False)
    daten = (FIXTURES / "rii_toc_auszug.xml").read_bytes()
    verzeichnis.importiere(con, daten, "test", *verzeichnis.archiviere(daten, tmp_path / "archiv"))
    akte.zitate_neu_pruefen(akten, con, a["id"])

    angefragt = []

    def lader(doknr):
        angefragt.append(doknr)
        return _zip_auszug()

    # Einzeln: ein anderes Zitat lädt nichts.
    assert urteile.volltexte_laden(akten, con, a["id"], tmp_path / "archiv", lader,
                                   zitat="EuGH, Urteil vom 04.06.2015 – C-497/13")["geladen"] == []
    ergebnis = urteile.volltexte_laden(akten, con, a["id"], tmp_path / "archiv", lader,
                                       zitat="BGH, Urteil vom 12.10.2016 – VIII ZR 103/15")
    # Nur die belegte BGH-Entscheidung; der EuGH steht nicht im Verzeichnis.
    assert angefragt == ["JURE160018467"] and ergebnis["fehler"] == []
    archiviert = list((tmp_path / "archiv" / "RECHTSPRECHUNG" / "volltexte").iterdir())
    assert [p.read_bytes() for p in archiviert] == [_zip_auszug()]

    bgh = next(e for e in akte.rechtsprechung(akten, con, a["id"]) if e["status"] == "belegt")
    assert bgh["urteil"]["quelle"] == urteile.RII and bgh["urteil"]["kopf"]["spruchkoerper"] == "8. Zivilsenat"
    assert [(f["rn"], f["rn_zitiert"], f["rn_vorhanden"]) for f in bgh["fundstellen"]] == [
        (13, None, None), (14, 22, True), (15, 99, False)]
    assert bgh["rn_hoechste"] == 22

    # Noch einmal laden: nichts mehr zu tun.
    assert urteile.volltexte_laden(akten, con, a["id"], tmp_path / "archiv", lader)["geladen"] == []
    # Aus der Akte entfernen: Die archivierte Rechtsquelle bleibt.
    assert urteile.entfernen(akten, bgh["urteil"]["id"], tmp_path / "ablage")["hinweis"] is None
    assert all(p.exists() for p in archiviert)


def test_volltext_fehler_halten_die_uebrigen_nicht_auf(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Fehler")
    (tmp_path / "k.md").write_text(KLAGE, encoding="utf-8")
    akte.importiere(akten, con, a["id"], tmp_path / "k.md", tmp_path / "ablage", ocr=False)
    daten = (FIXTURES / "rii_toc_auszug.xml").read_bytes()
    verzeichnis.importiere(con, daten, "test", *verzeichnis.archiviere(daten, tmp_path / "archiv"))
    akte.zitate_neu_pruefen(akten, con, a["id"])

    def lader(doknr):
        raise OSError("Netz nicht erreichbar")

    ergebnis = urteile.volltexte_laden(akten, con, a["id"], tmp_path / "archiv", lader)
    assert ergebnis["geladen"] == [] and "Netz nicht erreichbar" in ergebnis["fehler"][0]["fehler"]


# Tabellen aus der ersten Fassung von Schema 4 (ohne Randnummern, Teile und Kopfdaten).
_SCHEMA_4_ALT = """
CREATE TABLE akte (id INTEGER PRIMARY KEY, name TEXT NOT NULL, angelegt_am TEXT NOT NULL);
CREATE TABLE urteil (
    id INTEGER PRIMARY KEY, akte_id INTEGER NOT NULL REFERENCES akte(id) ON DELETE CASCADE, zitat TEXT,
    gericht TEXT NOT NULL, aktenzeichen TEXT, az_norm TEXT, datum TEXT, quelle TEXT NOT NULL, herkunft TEXT,
    dateiname TEXT NOT NULL, format TEXT NOT NULL, sha256 TEXT NOT NULL, original TEXT NOT NULL,
    lesart TEXT NOT NULL, hinweise TEXT NOT NULL, hinzugefuegt_am TEXT NOT NULL, UNIQUE (akte_id, sha256));
CREATE TABLE urteil_abschnitt (urteil_id INTEGER NOT NULL REFERENCES urteil(id) ON DELETE CASCADE,
    nr INTEGER NOT NULL, seite INTEGER, rn INTEGER, text TEXT NOT NULL);
INSERT INTO akte VALUES (1, 'Alt', '2026-10-16');
INSERT INTO urteil (akte_id, gericht, quelle, dateiname, format, sha256, original, lesart, hinweise, hinzugefuegt_am)
    VALUES (1, 'EuGH', 'manuell', 'eugh.txt', 'txt', 'abc', 'x', 'datei', '[]', '2026-10-16');
"""


def test_zwischenstand_schema_4_wird_ergaenzt(tmp_path):
    pfad = tmp_path / "akten.sqlite"
    alt = sqlite3.connect(pfad)
    alt.executescript(_SCHEMA_4_ALT)
    alt.close()
    con = akte.oeffne(pfad)
    assert [u["gericht"] for u in urteile.liste(con, 1)] == ["EuGH"]
    assert "teil" in {z["name"] for z in con.execute("PRAGMA table_info(urteil_abschnitt)")}
    con.close()
