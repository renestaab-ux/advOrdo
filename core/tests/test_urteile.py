import json

import pytest

from juracore import rpc
from juracore.dokumente import akte, urteile

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
    liste = kern.bearbeite(json.dumps({"id": 3, "method": "akten.urteile", "params": {"akte_id": a["id"]}}))
    assert [x["herkunft"] for x in liste["result"]] == ["beck-online"]
    eigene = kern.bearbeite(json.dumps({"id": 6, "method": "rechtsprechung.eigene"}))["result"]
    assert eigene == {"gesamt": 1, "quellen": [{"quelle": "manuell", "herkunft": "beck-online", "anzahl": 1}]}
    text = kern.bearbeite(json.dumps({"id": 4, "method": "akten.urteil", "params": {"urteil_id": u["urteil_id"]}}))
    assert text["result"]["dateiname"] == "beck.txt"
    weg = kern.bearbeite(json.dumps({"id": 5, "method": "akten.urteil_entfernen",
                                     "params": {"urteil_id": u["urteil_id"]}}))
    assert weg["result"]["hinweis"] is None
