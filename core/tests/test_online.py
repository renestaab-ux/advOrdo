import io
import zipfile

import pytest

from juracore import rpc
from juracore.dokumente import akte, urteile
from juracore.rechtsprechung import bayern, neuris, online, verzeichnis

from .conftest import FIXTURES

OLG = "Wie das OLG München, Urteil vom 14.03.2023 – 7 U 1234/22, Rn. 3 entschieden hat, liegt ein Mangel vor."
BGH_NEU = "So zuletzt BGH, Urteil vom 01.06.2026 – VIII ZR 11/26, Rn. 14."


def _bay_zip() -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("bayportalrsp/Y-300-Z-BECKRS-B-2023-N-99999.xml", (FIXTURES / "bayern_volltext_auszug.xml").read_bytes())
    return puffer.getvalue()


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    yield con
    con.close()


@pytest.mark.parametrize("gericht, erwartet", [
    ("OLG München", True), ("LG Traunstein", True), ("BayObLG", True), ("VGH München", True), ("LSG Bayern", True),
    ("OLG Hamm", False), ("BGH", False), ("LG Neustadt", False), ("", False),
])
def test_bayerische_gerichte(gericht, erwartet):
    assert bayern.ist_bayerisch(gericht) is erwartet


def test_bayern_volltext_lesen():
    v = bayern.lies(_bay_zip())
    assert (v.doknr, v.gericht, v.spruchkoerper, v.datum, v.aktenzeichen, v.doktyp) == (
        "Y-300-Z-BECKRS-B-2023-N-99999", "OLG München", "7. Zivilsenat", "2023-03-14", "7 U 1234/22", "Endurteil")
    assert v.normen == "BGB § 434, BGB § 323"
    assert v.vorinstanz == ["LG Traunstein, Endurteil vom 2022-06-01, Az: 3 O 111/21"]
    assert v.titel == "Rücktritt vom Gebrauchtwagenkauf wegen Rost"
    assert [a.teil for a in v.absaetze] == ["leitsatz", "leitsatz", "tenor", "gruende", "gruende", "gruende",
                                            "anmerkung"]
    assert v.randnummern == [1, 2, 3]
    assert v.absaetze[0].text == "Erster Leitsatz (Rn. 3) (redaktioneller Leitsatz)"
    with pytest.raises(ValueError, match="kein lesbares XML"):
        bayern.lies(b"<html>Wartung")
    with pytest.raises(ValueError, match="Dokumentnummer"):
        bayern.adresse("../x")


def test_bayern_trefferliste():
    treffer, gesamt = bayern.lies_trefferliste((FIXTURES / "bayern_trefferliste.html").read_text(encoding="utf-8"))
    assert gesamt == 2
    assert [(t.doknr, t.gericht, t.doktyp, t.datum, t.aktenzeichen) for t in treffer] == [
        ("Y-300-Z-BECKRS-B-2023-N-99999", "OLG München", "Endurteil", "2023-03-14", "7 U 1234/22"),
        ("Y-300-Z-BECKRS-B-2021-N-11111", "LG München I", "Urteil", "2021-02-02", "7 U 1234/22 e"),
    ]
    assert treffer[0].als_dict()["link"] == "https://www.gesetze-bayern.de/Content/Document/Y-300-Z-BECKRS-B-2023-N-99999"
    assert bayern.lies_trefferliste("<html>keine Treffer</html>") == ([], None)


def test_neuris_treffer_und_volltext():
    treffer, gesamt = neuris.lies_treffer((FIXTURES / "neuris_treffer.json").read_bytes())
    assert gesamt == 1
    t = treffer[0]
    assert (t["doknr"], t["gericht"], t["datum"], t["aktenzeichen"], t["link"]) == (
        "KORE999992026", "BGH", "2026-06-01", "VIII ZR 11/26",
        "https://testphase.rechtsinformationen.bund.de/case-law/KORE999992026")
    v = neuris.lies((FIXTURES / "neuris_volltext_auszug.html").read_bytes(), t)
    assert (v.gericht, v.spruchkoerper, v.aktenzeichen, v.doktyp) == ("BGH", "8. Zivilsenat", "VIII ZR 11/26", "Urteil")
    assert [(a.teil, a.rn, a.text) for a in v.absaetze] == [
        ("leitsatz", None, "Ein erfundener Leitsatz."),
        ("tenor", None, "Die Revision wird zurückgewiesen."),
        ("gruende", 1, "Die Klägerin verlangt Rückzahlung."),
        ("gruende", 2, "Das Berufungsgericht hat\ndie Klage abgewiesen."),
        ("gruende", 14, "Das hält rechtlicher Nachprüfung stand."),
    ]
    with pytest.raises(ValueError, match="kein Text"):
        neuris.lies(b"<html><body><p>Wartung</p></body></html>")


@pytest.mark.parametrize("datum, status", [
    ("2023-03-14", verzeichnis.BELEGT), (None, verzeichnis.BELEGT), ("2023-03-15", verzeichnis.ABWEICHEND)])
def test_bewerten(datum, status):
    treffer = [t.als_dict() for t in bayern.lies_trefferliste(
        (FIXTURES / "bayern_trefferliste.html").read_text(encoding="utf-8"))[0]]
    e = online.bewerte(online.BAYERN, "OLG München", "7 U 1234/22", datum, treffer)
    assert e["status"] == status and e["entscheidung"]["doknr"] == "Y-300-Z-BECKRS-B-2023-N-99999"
    assert "gesetze-bayern.de" in e["hinweis"]
    # Aktenzeichen gehört zu einem anderen Gericht.
    anders = online.bewerte(online.BAYERN, "OLG Nürnberg", "7 U 1234/22", None, treffer)
    assert anders["status"] == verzeichnis.ABWEICHEND and "OLG München" in anders["hinweis"]
    assert online.bewerte(online.BAYERN, "OLG München", "1 U 1/23", None, treffer)["status"] == \
        verzeichnis.NICHT_GEFUNDEN


def test_zustaendig():
    assert online.zustaendig("OLG München", "7 U 1/23", verzeichnis.AUSSERHALB, {"bayern"}) == "bayern"
    assert online.zustaendig("OLG München", None, verzeichnis.AUSSERHALB, {"bayern"}) is None
    assert online.zustaendig("OLG Hamm", "7 U 1/23", verzeichnis.AUSSERHALB, {"bayern", "neuris"}) is None
    assert online.zustaendig("BGH", "VIII ZR 1/26", verzeichnis.NICHT_GEFUNDEN, {"bayern"}) is None
    assert online.zustaendig("BGH", "VIII ZR 1/26", verzeichnis.NICHT_GEFUNDEN, {"bayern", "neuris"}) == "neuris"
    assert online.zustaendig("BGH", "VIII ZR 1/26", verzeichnis.BELEGT, {"bayern", "neuris"}) is None


def test_einstellungen(tmp_path):
    datei = tmp_path / "quellen.json"
    assert online.einstellungen(datei) == {"neuris": False}
    assert online.quellen(online.einstellungen(datei)) == {"bayern"}
    assert online.einstellungen_setzen(datei, True) == {"neuris": True}
    assert online.quellen(online.einstellungen(datei)) == {"bayern", "neuris"}


def test_bayerisches_zitat_online_pruefen_und_volltext_laden(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Rost")
    (tmp_path / "klage.md").write_text(f"(1) {OLG}", encoding="utf-8")
    akte.importiere(akten, con, a["id"], tmp_path / "klage.md", tmp_path / "ablage", ocr=False)
    vorher = akte.rechtsprechung(akten, con, a["id"])
    assert [(g["status"], g["online_offen"]) for g in vorher] == [(verzeichnis.AUSSERHALB, "bayern")]

    gesucht = []

    def suche(az):
        gesucht.append(az)
        return [t.als_dict() for t in bayern.lies_trefferliste(
            (FIXTURES / "bayern_trefferliste.html").read_text(encoding="utf-8"))[0]]

    ergebnis = online.pruefe(con, vorher, {"bayern"}, suche={"bayern": suche})
    assert gesucht == ["7 U 1234/22"] and ergebnis["fehler"] == []
    akte.urteilszitate_neu_pruefen(akten, con, a["id"])
    g = akte.rechtsprechung(akten, con, a["id"])[0]
    assert g["status"] == verzeichnis.BELEGT and g["online_offen"] is None
    assert g["entscheidung"]["quelle"] == "bayern" and "gesetze-bayern.de" in g["hinweis"]
    # Schon geprüft: keine zweite Anfrage, außer ausdrücklich neu.
    online.pruefe(con, akte.rechtsprechung(akten, con, a["id"]), {"bayern"}, suche={"bayern": suche})
    assert gesucht == ["7 U 1234/22"]

    angefragt = []

    def lade(doknr):
        angefragt.append(doknr)
        return _bay_zip()

    geladen = urteile.volltexte_laden(akten, con, a["id"], tmp_path / "archiv", lader_online={"bayern": lade})
    assert geladen == {"geladen": [g["zitat"]], "fehler": []}
    assert angefragt == ["Y-300-Z-BECKRS-B-2023-N-99999"]
    archiviert = list((tmp_path / "archiv" / "RECHTSPRECHUNG" / "bayern").iterdir())
    assert [p.read_bytes() for p in archiviert] == [_bay_zip()]
    g = akte.rechtsprechung(akten, con, a["id"])[0]
    assert (g["urteil"]["quelle"], g["urteil"]["herkunft"]) == ("bayern", "gesetze-bayern.de")
    assert [(f["rn_zitiert"], f["rn_vorhanden"]) for f in g["fundstellen"]] == [(3, True)]


def test_bundesgericht_bei_neuris_pruefen(akten, con, tmp_path):
    daten = (FIXTURES / "rii_toc_auszug.xml").read_bytes()
    verzeichnis.importiere(con, daten, "test", *verzeichnis.archiviere(daten, tmp_path / "archiv"))
    a = akte.akte_anlegen(akten, "Neu")
    (tmp_path / "replik.md").write_text(f"(1) {BGH_NEU}", encoding="utf-8")
    akte.importiere(akten, con, a["id"], tmp_path / "replik.md", tmp_path / "ablage", ocr=False)
    g = akte.rechtsprechung(akten, con, a["id"])[0]
    assert g["status"] == verzeichnis.NICHT_GEFUNDEN and g["online_offen"] is None  # NeuRIS ist aus
    aktiv = {"bayern", "neuris"}
    g = akte.rechtsprechung(akten, con, a["id"], online_quellen=aktiv)[0]
    assert g["online_offen"] == "neuris"

    treffer = neuris.lies_treffer((FIXTURES / "neuris_treffer.json").read_bytes())[0]
    online.pruefe(con, [g], aktiv, suche={"neuris": lambda az: treffer})
    akte.urteilszitate_neu_pruefen(akten, con, a["id"])
    g = akte.rechtsprechung(akten, con, a["id"], online_quellen=aktiv)[0]
    assert g["status"] == verzeichnis.BELEGT and "NeuRIS" in g["hinweis"]

    html = (FIXTURES / "neuris_volltext_auszug.html").read_bytes()
    urteile.volltexte_laden(akten, con, a["id"], tmp_path / "archiv", lader_online={"neuris": lambda d: html})
    g = akte.rechtsprechung(akten, con, a["id"])[0]
    assert g["urteil"]["quelle"] == "neuris" and g["rn_hoechste"] == 14
    assert [(f["rn_zitiert"], f["rn_vorhanden"]) for f in g["fundstellen"]] == [(14, True)]
    assert (tmp_path / "archiv" / "RECHTSPRECHUNG" / "neuris").is_dir()


def test_nicht_gefunden_und_fehler(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Fehler")
    (tmp_path / "k.md").write_text(f"(1) {OLG}", encoding="utf-8")
    akte.importiere(akten, con, a["id"], tmp_path / "k.md", tmp_path / "ablage", ocr=False)

    def kaputt(az):
        raise OSError("Netz nicht erreichbar")

    e = online.pruefe(con, akte.rechtsprechung(akten, con, a["id"]), {"bayern"}, suche={"bayern": kaputt})
    assert e["geprueft"] == [] and "Netz nicht erreichbar" in e["fehler"][0]["fehler"]
    assert akte.rechtsprechung(akten, con, a["id"])[0]["online_offen"] == "bayern"  # bleibt offen

    online.pruefe(con, akte.rechtsprechung(akten, con, a["id"]), {"bayern"}, suche={"bayern": lambda az: []})
    akte.urteilszitate_neu_pruefen(akten, con, a["id"])
    g = akte.rechtsprechung(akten, con, a["id"])[0]
    assert g["status"] == verzeichnis.AUSSERHALB and g["online_offen"] is None
    assert "Bei gesetze-bayern.de nicht gefunden" in g["hinweis"]


def test_rpc_quellen(tmp_path):
    kern = rpc.Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    assert kern.methoden["rechtsprechung.quellen"]() == {"neuris": False}
    assert kern.methoden["rechtsprechung.quellen_setzen"](neuris=True) == {"neuris": True}
    assert kern._online_quellen() == {"bayern", "neuris"}
    a = akte.akte_anlegen(kern.akten, "Leer")
    assert kern.online_pruefen(a["id"]) == {"geprueft": [], "fehler": []}
