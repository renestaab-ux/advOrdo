import json
import re
import urllib.parse

import pytest

from juracore import db, rpc
from juracore.dokumente import akte, urteile
from juracore.rechtsprechung import bayern, neuris, recherche, rii_suche, verzeichnis

from .conftest import FIXTURES
from .test_online import _bay_zip
from .test_urteile import _zip_auszug


@pytest.fixture
def wissen(tmp_path):
    con = db.oeffne(tmp_path / "wissen.sqlite")
    verzeichnis.einrichten(con)
    daten = (FIXTURES / "rii_toc_auszug.xml").read_bytes()
    verzeichnis.importiere(con, daten, "test", "0" * 64, "")
    yield con
    con.close()


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    yield con
    con.close()


def _felder(adresse: str) -> list[tuple[str, str]]:
    return urllib.parse.parse_qsl(urllib.parse.urlsplit(adresse).query, keep_blank_values=True)


# --- rechtsprechung-im-internet.de ---------------------------------------------------------------------


def test_lokal_im_verzeichnis(wissen):
    alle = rii_suche.lokal(wissen, gericht="BGH")
    assert alle["gesamt"] == len(alle["treffer"]) > 0
    assert [t["datum"] for t in alle["treffer"]] == sorted((t["datum"] for t in alle["treffer"]), reverse=True)
    az = rii_suche.lokal(wissen, aktenzeichen="VIII ZR 103")
    assert [t["aktenzeichen"] for t in az["treffer"]] == ["VIII ZR 103/15"]
    assert az["treffer"][0]["quelle"] == "rii" and az["treffer"][0]["link"].startswith("https://")
    assert rii_suche.lokal(wissen, aktenzeichen="VIII ZR 103", von="2020-01-01")["gesamt"] == 0
    # Platzhalter im Aktenzeichen wirken nicht als LIKE-Muster.
    assert rii_suche.lokal(wissen, aktenzeichen="%")["gesamt"] == 0


def test_suchadresse_aus_der_maske():
    maske = (FIXTURES / "rii_suchmaske_auszug.html").read_text(encoding="utf-8")
    adresse = rii_suche.suchadresse(maske, text="Gebrauchtwagen & Mangel", norm="§ 476 BGB", gericht="BGH",
                                    von="2016-01-01", bis="2016-12-31")
    assert adresse.startswith("https://www.rechtsprechung-im-internet.de/jportal/portal/t/1a2b/page/bsjrsprod.psml?")
    assert "jsessionid" not in adresse and "%26" in adresse  # & im Suchwert kodiert
    assert _felder(adresse) == [
        ("sugline", "1"), ("desc", "text"), ("query", "Gebrauchtwagen & Mangel"), ("desc", "norm"),
        ("query", "476 BGB"), ("desc", "date"), ("query", "date"), ("dateFrom", "01.01.2016"),
        ("dateTo", "31.12.2016"), ("desc", "court_author"), ("query", "bgh"), ("desc", "filenumber"),
        ("query", ""), ("standardsuche", "suchen"),
    ]
    ohne_gericht = dict(_felder(rii_suche.suchadresse(maske, text="x")))
    assert ohne_gericht["dateFrom"] == "" and ("query", "") in _felder(rii_suche.suchadresse(maske, text="x"))
    with pytest.raises(ValueError, match="Gericht XY"):
        rii_suche.suchadresse(maske, text="x", gericht="XY")
    with pytest.raises(ValueError, match="kein Suchformular"):
        rii_suche.suchadresse("<html></html>", text="x")


def test_trefferliste_und_weiterblaettern():
    seite = (FIXTURES / "rii_trefferliste_auszug.html").read_text(encoding="utf-8")
    treffer, gesamt = rii_suche.lies_trefferliste(seite)
    assert gesamt == 2852  # Tausenderpunkt
    erster, zweiter = treffer
    assert (erster["doknr"], erster["gericht"], erster["spruchkoerper"], erster["datum"], erster["aktenzeichen"],
            erster["doktyp"], erster["titel"], erster["normen"]) == (
        "KORE301892016", "BGH", "8. Zivilsenat", "2016-10-12", "VIII ZR 103/15", "Urteil",
        "Sachmängelhaftung beim Gebrauchtwagenkauf", "§ 476 BGB")
    assert (zweiter["doktyp"], zweiter["titel"]) == ("Beschluss", None)
    assert zweiter["ausschnitt"] == "... der Gebrauchtwagen wies einen Mangel auf ..."
    weiter = rii_suche.weiteradresse(seite)
    assert weiter.startswith("https://www.rechtsprechung-im-internet.de/jportal/portal/t/9z8y/page/bsjrsprod.psml?")
    assert _felder(weiter) == [
        ("action", "portlets.jw.ResultListFormAction"), ("tl", "true"), ("IGNORE", "true"),
        ("currentNavigationPosition", "1"), ("numberofresults", "2852"),
        ("eventSubmit_doSkipforward.x", "5"), ("eventSubmit_doSkipforward.y", "5"),
    ]
    keine = "<p>Es wurden keine mit Ihrer Suchanfrage &uuml;bereinstimmenden Dokumente gefunden.</p>"
    assert rii_suche.lies_trefferliste(keine) == ([], 0)


class _Sitzung(rii_suche.Sitzung):
    """Sitzung ohne Netz: liefert Maske und Trefferseite aus den Testdateien und merkt sich die Adressen."""

    def __init__(self):
        super().__init__()
        self.adressen = []

    def _hole(self, url):
        self.adressen.append(url)
        datei = "rii_suchmaske_auszug.html" if url == rii_suche.MASKE else "rii_trefferliste_auszug.html"
        return (FIXTURES / datei).read_text(encoding="utf-8")


def test_recherche_rii_lokal_oder_online(wissen):
    sitzungen = []

    def neue():
        sitzungen.append(_Sitzung())
        return sitzungen[-1]

    r = recherche.Recherche(wissen, sitzung=neue)
    lokal = r.suche("rii", {"gericht": "BGH", "aktenzeichen": "VIII ZR 103"})
    assert lokal["ort"] == "verzeichnis" and not sitzungen
    with pytest.raises(ValueError, match="Bitte"):
        r.suche("rii", {"gericht": "", "aktenzeichen": " "})

    online = r.suche("rii", {"volltext": "Gebrauchtwagen", "gericht": "BGH"})
    assert online["ort"] == "online" and online["gesamt"] == 2852 and online["weitere"]
    assert len(sitzungen) == 1 and len(sitzungen[0].adressen) == 2
    weiter = r.weiter("rii")
    assert len(weiter["treffer"]) == 2 and len(sitzungen) == 1 and len(sitzungen[0].adressen) == 3
    assert "eventSubmit_doSkipforward.x=5" in sitzungen[0].adressen[-1]
    # ECLI im Aktenzeichenfeld geht an die Seite, eine neue Suche bekommt eine neue Sitzung.
    r.suche("rii", {"aktenzeichen": "ECLI:DE:BGH:2016:121016UVIIIZR103.15.0"})
    assert len(sitzungen) == 2


def test_ohne_verzeichnis(tmp_path):
    con = db.oeffne(tmp_path / "leer.sqlite")
    with pytest.raises(ValueError, match="noch nicht geladen"):
        recherche.Recherche(con).suche("rii", {"aktenzeichen": "VIII ZR 1/20"})
    con.close()


def test_weiterblaettern_endet_bei_hoechstzahl():
    s = _Sitzung()
    s.suche(text="x")
    s.geladen = rii_suche.MAX_TREFFER
    assert not s.weitere
    assert s.weiter() == {"treffer": [], "gesamt": 2852, "weitere": False}


# --- gesetze-bayern.de und NeuRIS ----------------------------------------------------------------------


def test_bayern_suchfelder(monkeypatch, wissen):
    abrufe = []

    class Antwort:
        def __init__(self, text):
            self.text = text

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.text.encode()

    class Oeffner:
        addheaders = []

        def open(self, url, data=None, timeout=None):
            abrufe.append((url, data))
            if url.endswith("/Search/Hitlist"):
                return Antwort('<input name="__RequestVerificationToken" type="hidden" value="T&amp;1" />')
            if url.endswith("/Search"):
                return Antwort((FIXTURES / "bayern_trefferliste.html").read_text(encoding="utf-8"))
            return Antwort("")

    monkeypatch.setattr(bayern.urllib.request, "build_opener", lambda *a: Oeffner())
    r = recherche.Recherche(wissen)
    ergebnis = r.suche("bayern", {"volltext": "Hallenbad", "von": "2023-01-01", "bis": "2023-12-31",
                                  "gerichtsbarkeit": "Ordentliche Gerichtsbarkeit"})
    assert ergebnis["treffer"] and ergebnis["weitere"] is False
    assert abrufe[1][0].endswith("/Search/Filter/LEVEL1RSPRTREENODE/Ordentliche%20Gerichtsbarkeit")
    formular = dict(urllib.parse.parse_qsl(abrufe[-1][1].decode(), keep_blank_values=True))
    assert formular == {"SearchFields.Aktenzeichen": "", "SearchFields.Content": "Hallenbad",
                        "SearchFields.DatumVon": "01.01.2023", "SearchFields.DatumBis": "31.12.2023",
                        "__RequestVerificationToken": "T&1"}
    with pytest.raises(ValueError, match="Gerichtsbarkeit"):
        bayern.suche(volltext="x", gerichtsbarkeit="Mondgericht")
    with pytest.raises(ValueError, match="Bitte"):
        r.suche("bayern", {"gerichtsbarkeit": "Ordentliche Gerichtsbarkeit"})


def test_neuris_suchfelder_und_seiten(monkeypatch, wissen):
    adressen = []
    antwort = json.loads((FIXTURES / "neuris_treffer.json").read_text(encoding="utf-8"))
    antwort["totalItems"] = 120
    antwort["member"][0]["textMatches"] = [{"name": "text", "text": "der <mark>Gebrauchtwagen</mark> war"}]

    def hole(url, timeout):
        adressen.append(url)
        return json.dumps(antwort).encode()

    monkeypatch.setattr(neuris, "_hole", hole)
    r = recherche.Recherche(wissen)
    with pytest.raises(ValueError, match="ausgeschaltet"):
        r.suche("neuris", {"volltext": "x"})
    erste = r.suche("neuris", {"volltext": "Gebrauchtwagen", "gericht": "BGH", "von": "2026-01-01"},
                    neuris_an=True)
    assert erste["treffer"][0]["ausschnitt"] == "der Gebrauchtwagen war" and erste["weitere"]
    abfrage = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(adressen[0]).query))
    assert abfrage == {"searchTerm": "Gebrauchtwagen", "court": "BGH", "dateFrom": "2026-01-01", "size": "50",
                       "pageIndex": "0", "sort": "-date"}
    r.weiter("neuris")
    assert "pageIndex=1" in adressen[-1]


# --- Treffer ansehen und in die Sammlung übernehmen -------------------------------------------------


def test_vorschau_und_in_sammlung(akten, wissen, tmp_path):
    abrufe = []

    def lade(doknr):
        abrufe.append(doknr)
        return _zip_auszug()

    r = recherche.Recherche(wissen, lader={"rii": lade})
    v = urteile.vorschau(r.daten("rii", "KORE301892016"), "rii")
    assert v["id"] is None and v["gericht"] == "BGH" and v["abschnitte"]
    gespeichert = urteile.in_sammlung(akten, r.daten("rii", "KORE301892016"), "rii", tmp_path / "archiv")
    assert gespeichert["neu"] and abrufe == ["KORE301892016"]  # zweiter Zugriff aus dem Zwischenspeicher
    eintrag = urteile.sammlung(akten)[0]
    assert (eintrag["id"], eintrag["akte_id"], eintrag["quelle"]) == (gespeichert["urteil_id"], None, "rii")
    # Ein zweites Speichern legt nichts doppelt an; Treffer erkennen die gespeicherte Entscheidung.
    assert urteile.in_sammlung(akten, _zip_auszug(), "rii", tmp_path / "archiv") == {
        "urteil_id": gespeichert["urteil_id"], "neu": False}
    markiert = urteile.gespeichert(akten, [{"quelle": "rii", "doknr": "KORE301892016"},
                                           {"quelle": "rii", "doknr": "KORE000000000"}])
    assert [t["urteil_id"] for t in markiert] == [gespeichert["urteil_id"], None]

    bay = urteile.in_sammlung(akten, _bay_zip(), "bayern", tmp_path / "archiv")
    assert urteile.volltext(akten, bay["urteil_id"])["herkunft"] == bayern.HERKUNFT


def test_rpc_recherche(tmp_path, monkeypatch):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    monkeypatch.setitem(kern.recherche.lader, "rii", lambda doknr: _zip_auszug())
    verzeichnis.einrichten(kern.con)
    verzeichnis.importiere(kern.con, (FIXTURES / "rii_toc_auszug.xml").read_bytes(), "test", "0" * 64, "")

    def ruf(methode, **params):
        antwort = kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))
        return antwort.get("result", antwort.get("error"))

    treffer = ruf("rechtsprechung.recherche", quelle="rii", felder={"aktenzeichen": "VIII ZR 103/15"})["treffer"]
    assert [t["urteil_id"] for t in treffer] == [None]
    vorschau = ruf("rechtsprechung.recherche_oeffnen", quelle="rii", doknr=treffer[0]["doknr"], treffer=treffer[0])
    assert vorschau["id"] is None and vorschau["aktenzeichen"] == "VIII ZR 103/15"
    gespeichert = ruf("rechtsprechung.recherche_speichern", quelle="rii", doknr=treffer[0]["doknr"])
    assert gespeichert["neu"]
    assert [u["id"] for u in ruf("rechtsprechung.sammlung")] == [gespeichert["urteil_id"]]

    def kein_netz(doknr):
        raise rpc.urllib.error.URLError("keine Verbindung")

    monkeypatch.setitem(kern.recherche.lader, "rii", kein_netz)
    fehler = ruf("rechtsprechung.recherche_oeffnen", quelle="rii", doknr="KORE000000000")
    assert "nicht erreichbar" in fehler["message"]


def test_suchformular_ohne_namen_und_ohne_base():
    maske = (FIXTURES / "rii_suchmaske_auszug.html").read_text(encoding="utf-8")
    ohne = re.sub(r"<base[^>]*>", "", maske).replace('name="searchForm"', 'id="x"')
    adresse = rii_suche.suchadresse(ohne, text="Kauf", adresse="https://www.rechtsprechung-im-internet.de/jportal/a/b")
    assert adresse.startswith("https://www.rechtsprechung-im-internet.de/jportal/portal/t/1a2b/page/bsjrsprod.psml?")
    assert ("query", "Kauf") in _felder(adresse)


def test_unlesbare_maske_wird_abgelegt(tmp_path):
    class Leer(_Sitzung):
        def _hole(self, url):
            return "<html><body>Wartungsarbeiten</body></html>"

    s = Leer()
    s.fehlerseite = tmp_path / "diagnose" / "rii-suchmaske.html"
    with pytest.raises(ValueError, match="liegt zur Prüfung unter"):
        s.suche(text="x")
    assert "Wartungsarbeiten" in s.fehlerseite.read_text(encoding="utf-8")


def test_neuris_volltext_als_html(monkeypatch):
    arten = []

    def hole(url, timeout, art="application/json"):
        arten.append(art)
        if url.endswith("FEHLT.html"):
            raise neuris.urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return b"<html></html>"

    monkeypatch.setattr(neuris, "_hole", hole)
    neuris.lade("KORE999992026")
    assert arten == ["text/html"]
    with pytest.raises(ValueError, match="keinen Volltext"):
        neuris.lade("FEHLT")
