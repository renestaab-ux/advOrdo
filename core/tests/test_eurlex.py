"""Unionsrecht aus EUR-Lex: Lesen der HTML-Fassung, Import und Zitate wie "Art. 6 Abs. 1 lit. f DSGVO"."""

import io
import urllib.error
import urllib.request

import pytest

from juracore.gesetze import eurlex, quelle, wissensbasis
from juracore.gesetze.zitate import finde_zitate, parse_zitat

from .conftest import FIXTURES

AUSZUG = FIXTURES / "eurlex_dsgvo_auszug.html"


@pytest.fixture
def dsgvo():
    return eurlex.parse_eurlex_html(AUSZUG.read_bytes(), "DSGVO")


def _norm(dokument, bezeichnung):
    return next(n for n in dokument.normen if n.bezeichnung == bezeichnung)


def test_stammdaten(dsgvo):
    assert dsgvo.langtitel.startswith("Verordnung (EU) 2016/679 des Europäischen Parlaments und des Rates vom 27. April")
    assert dsgvo.langtitel.endswith("(Datenschutz-Grundverordnung)")
    assert dsgvo.builddate == "20160504"
    assert dsgvo.stand == ["ABl. L 119 vom 4.5.2016, S. 1"]


def test_artikel_mit_gliederung_und_absaetzen(dsgvo):
    assert [n.bezeichnung for n in dsgvo.normen if n.typ == "artikel"] == ["Art. 1", "Art. 4", "Art. 6", "Art. 82"]
    art82 = _norm(dsgvo, "Art. 82")
    assert art82.titel == "Haftung und Recht auf Schadenersatz"
    assert art82.gliederung == ["Kapitel VIII Rechtsbehelfe, Haftung und Sanktionen"]
    assert [a.nr for a in art82.absaetze] == ["1", "2", "6"]
    assert len(art82.absaetze[1].saetze) == 2
    # Die Schlussformel gehört nicht mehr zum letzten Artikel.
    assert "verbindlich" not in art82.text and "Geschehen" not in art82.text


def test_aufzaehlung_und_unterabsatz(dsgvo):
    abs1 = _norm(dsgvo, "Art. 6").absaetze[0]
    assert abs1.nr == "1"
    assert [nr for nr, _ in abs1.saetze[0].nummern] == ["a", "b", "f"]
    assert "f) die Verarbeitung ist zur Wahrung" in abs1.text
    assert abs1.saetze[1].text.startswith("Unterabsatz 1 Buchstabe f gilt nicht")


def test_begriffsbestimmungen_ohne_absatznummer(dsgvo):
    art4 = _norm(dsgvo, "Art. 4")
    assert len(art4.absaetze) == 1 and art4.absaetze[0].nr is None
    assert [nr for nr, _ in art4.absaetze[0].saetze[0].nummern] == ["1", "2"]


def test_erwaegungsgruende_ohne_fussnotenzeichen(dsgvo):
    erw = [n for n in dsgvo.normen if n.typ == "erwaegungsgrund"]
    assert [n.nummer for n in erw] == ["1", "146"]
    assert erw[1].bezeichnung == "Erwägungsgrund 146"
    assert "weit auf eine Art und Weise ausgelegt" in erw[1].text
    assert all("ABl. C 229" not in n.text for n in dsgvo.normen)


def test_alte_rechtsakte_ohne_oj_praefix():
    html = """<html><body><p class="doc-ti">VERORDNUNG (EG) Nr. 864/2007 DES EUROPÄISCHEN PARLAMENTS UND DES RATES</p>
    <p class="ti-section-1">KAPITEL I</p><p class="ti-section-2">ANWENDUNGSBEREICH</p>
    <p class="ti-art">Artikel 1</p><p class="sti-art">Anwendungsbereich</p>
    <p class="normal">(1) Diese Verordnung gilt für außervertragliche Schuldverhältnisse in Zivil- und Handelssachen.</p>
    <p class="normal">(2) Vom Anwendungsbereich dieser Verordnung ausgenommen sind</p>
    <p class="normal">a) außervertragliche Schuldverhältnisse aus einem Familienverhältnis;</p>
    <p class="normal">b) außervertragliche Schuldverhältnisse aus ehelichen Güterständen.</p>
    <p class="normal">Geschehen zu Straßburg am 11. Juli 2007.</p></body></html>"""
    d = eurlex.parse_eurlex_html(html, "ROM2")
    assert d.langtitel.startswith("Verordnung (EG) Nr. 864/2007 des Europäischen")
    art1 = d.normen[0]
    assert art1.gliederung == ["Kapitel I ANWENDUNGSBEREICH"]
    assert [a.nr for a in art1.absaetze] == ["1", "2"]
    assert [nr for nr, _ in art1.absaetze[1].saetze[0].nummern] == ["a", "b"]
    assert "Geschehen" not in art1.text


def test_kein_rechtsakt():
    assert not eurlex.ist_eurlex(b"<?xml version='1.0'?><dokumente/>")
    with pytest.raises(ValueError, match="keine Artikel"):
        eurlex.parse_eurlex_html("<html><p class='oj-normal'>Text</p><p class='oj-ti-art'>Anhang</p></html>")


# --- Zitate ---------------------------------------------------------------------------------------


def test_zitate_unionsrecht():
    z = parse_zitat("Art. 6 Abs. 1 UAbs. 1 Buchst. f DS-GVO")
    assert (z.gesetz, z.nummer, z.absatz, z.nr, z.zeichen) == ("DSGVO", "6", "1", "f", "Art.")
    assert str(z) == "Art. 6 Abs. 1 lit. f DSGVO"
    assert [str(z) for z in finde_zitate("nach Art. 15 Abs. 1 lit. h, Abs. 3 DSGVO und Art. 82 DSGVO")] == [
        "Art. 15 Abs. 1 lit. h DSGVO", "Art. 15 Abs. 3 DSGVO", "Art. 82 DSGVO"]
    assert [str(z) for z in finde_zitate("Art. 6 Abs. 1 lit. a und f DSGVO, § 280 ff. BGB")] == [
        "Art. 6 Abs. 1 lit. a DSGVO", "Art. 6 Abs. 1 lit. f DSGVO", "§ 280 BGB"]
    # Bindestrich nur zwischen Großbuchstaben: "BGB-Gesellschaft" ist kein Gesetz.
    assert [str(z) for z in finde_zitate("die BGB-Gesellschaft nach § 705 BGB")] == ["§ 705 BGB"]
    # Ein Wort nach der Nummer ist kein Buchstabe.
    assert str(parse_zitat("§ 437 Nr. 4 BGB")) == "§ 437 Nr. 4 BGB"


# --- Import und Auflösung -------------------------------------------------------------------------


def test_import_und_aufloesung(con, tmp_path):
    roh = quelle.lies_datei(AUSZUG, tmp_path / "archiv")
    assert roh.abk == "DSGVO"  # an der CELEX-Nummer der gespeicherten Seite erkannt
    assert roh.archivpfad.suffix == ".html" and roh.archivpfad.read_bytes() == AUSZUG.read_bytes()
    ergebnis = wissensbasis.importiere(con, roh, roh.abk)
    assert ergebnis["neu"] and ergebnis["normen"] == 6

    b = wissensbasis.loese_zitat(con, "Art. 6 Abs. 1 lit. f DS-GVO")
    assert b["status"] == "belegt" and b["wortlaut"].startswith("f) die Verarbeitung ist zur Wahrung")
    assert b["fassung"]["hinweis"].startswith("Fassung des Amtsblatts der EU (EUR-Lex)")
    assert wissensbasis.loese_zitat(con, "Art. 82 Abs. 1 DSGVO")["wortlaut"].startswith("Jede Person, der wegen")
    assert wissensbasis.loese_zitat(con, "Art. 4 Nr. 2 DSGVO")["wortlaut"].startswith("2. „Verarbeitung“")
    fehlt = wissensbasis.loese_zitat(con, "Art. 6 Abs. 1 lit. g DSGVO")
    assert fehlt["status"] == "nicht_gefunden" and fehlt["hinweis"].startswith("Buchstabe g")

    assert wissensbasis.norm(con, "DSGVO", "146", typ="erwaegungsgrund")["bezeichnung"] == "Erwägungsgrund 146"
    assert "Art. 82" in [t["bezeichnung"] for t in wissensbasis.suche(con, "immaterieller", "DSGVO")]
    # Erneuter Import derselben Datei legt keine zweite Fassung an.
    assert not wissensbasis.importiere(con, quelle.lies_datei(AUSZUG, tmp_path / "archiv"), "DSGVO")["neu"]


class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_laden_ueber_voreinstellung(monkeypatch, tmp_path):
    aufrufe = []

    def urlopen(anfrage, timeout):
        aufrufe.append(anfrage.full_url)
        if anfrage.full_url == eurlex.adresse("32016R0679"):
            return _Antwort(AUSZUG.read_bytes())
        raise urllib.error.HTTPError(anfrage.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(eurlex.urllib.request, "urlopen", urlopen)
    roh = quelle.lade_gesetz("DSGVO", tmp_path)
    assert roh.abk == "DSGVO" and roh.quelle == eurlex.adresse("32016R0679")
    assert aufrufe == ["https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:32016R0679"]
    with pytest.raises(ValueError, match="nicht gefunden"):
        eurlex.lade("32099R9999")


def test_bot_abwehr_weicht_auf_cellar_aus(monkeypatch, tmp_path):
    aufrufe = []

    def urlopen(anfrage, timeout):
        aufrufe.append((anfrage.full_url, anfrage.get_header("Accept-language")))
        if anfrage.full_url == eurlex.cellar_adresse("32016R0679"):
            return _Antwort(AUSZUG.read_bytes())
        return _Antwort(b"")  # EUR-Lex: HTTP 202 ohne Inhalt

    monkeypatch.setattr(eurlex.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(eurlex, "_cellar_oeffnen", urlopen)
    roh = quelle.lade_gesetz("DSGVO", tmp_path)
    assert roh.quelle == "https://publications.europa.eu/resource/celex/32016R0679"
    assert [a[0] for a in aufrufe] == [eurlex.adresse("32016R0679"), eurlex.cellar_adresse("32016R0679")]
    assert aufrufe[1][1] == "deu"


def test_unlesbare_antwort_nennt_ausweg(monkeypatch):
    def urlopen(anfrage, timeout):
        if anfrage.full_url == eurlex.cellar_adresse("32016R0679"):
            raise urllib.error.HTTPError(anfrage.full_url, 406, "Not Acceptable", {}, None)
        return _Antwort(b"<html>Bitte warten</html>")

    monkeypatch.setattr(eurlex.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(eurlex, "_cellar_oeffnen", urlopen)
    with pytest.raises(ValueError, match="als Datei importieren"):
        eurlex.lade("32016R0679")
    with pytest.raises(ValueError, match="CELEX"):
        eurlex.lade("../etc")


def test_cellar_weiterleitung_auf_https():
    """Cellar antwortet mit 303 auf eine http-Adresse; abgerufen wird dieselbe Adresse verschlüsselt."""
    assert eurlex.https("http://publications.europa.eu/resource/cellar/abc.0004.02/DOC_1") == (
        "https://publications.europa.eu/resource/cellar/abc.0004.02/DOC_1")
    assert eurlex.https("http://example.org/x") == "http://example.org/x"
    assert eurlex.https("https://eur-lex.europa.eu/x") == "https://eur-lex.europa.eu/x"
    alt = urllib.request.Request(eurlex.cellar_adresse("32016R0679"), headers={"Accept-Language": "deu"})
    neu = eurlex._HttpsWeiterleitung().redirect_request(
        alt, None, 303, "See Other", {}, "http://publications.europa.eu/resource/cellar/abc/DOC_1")
    assert neu.full_url == "https://publications.europa.eu/resource/cellar/abc/DOC_1"


def test_zitate_rom_verordnungen():
    for text in ("Art. 4 Abs. 1 lit. a Rom I-VO", "Art. 4 Abs. 1 lit. a Rom I", "Art. 4 Abs. 1 lit. a Rom-I-VO"):
        assert str(parse_zitat(text)) == "Art. 4 Abs. 1 lit. a Rom I-VO"
    assert [str(z) for z in finde_zitate("nach Art. 4 Abs. 1 Rom II-VO und Art. 14 Rom II")] == [
        "Art. 4 Abs. 1 Rom II-VO", "Art. 14 Rom II-VO"]
    # "Rom" als Wort ohne Verordnung ist kein Gesetz.
    assert finde_zitate("Art. 3 Rom ist die Hauptstadt") == []


def test_rom_verordnung_import_und_aufloesung(con, tmp_path):
    html = """<html><body><table><tr><td><p class="hd-date">31.7.2007</p></td><td><p class="hd-lg">DE</p></td>
    <td><p class="hd-ti">Amtsblatt der Europäischen Union</p></td><td><p class="hd-oj">L 199/40</p></td></tr></table>
    <p class="doc-ti">VERORDNUNG (EG) Nr. 864/2007 DES EUROPÄISCHEN PARLAMENTS UND DES RATES</p>
    <p class="ti-art">Artikel 4</p><p class="sti-art">Allgemeine Kollisionsnorm</p>
    <p class="normal">(1) Soweit in dieser Verordnung nichts anderes vorgesehen ist, ist auf ein außervertragliches
    Schuldverhältnis aus unerlaubter Handlung das Recht des Staates anzuwenden, in dem der Schaden eintritt.</p>
    <p class="normal">Geschehen zu Straßburg am 11. Juli 2007.</p></body></html>"""
    datei = tmp_path / "rom2.html"
    datei.write_text(html, encoding="utf-8")
    roh = quelle.lies_datei(datei, tmp_path / "archiv", abk="Rom II-VO")
    assert roh.archivpfad.parent.name == "ROM II-VO"
    wissensbasis.importiere(con, roh, roh.abk)
    b = wissensbasis.loese_zitat(con, "Art. 4 Abs. 1 Rom II")
    assert b["status"] == "belegt" and b["wortlaut"].startswith("Soweit in dieser Verordnung")
    assert b["fassung"]["stand"] == ["ABl. L 199 vom 31.7.2007, S. 40"]


def test_abkuerzung_ohne_pfadzeichen():
    assert quelle.pfadkuerzel("Rom I-VO") == ("ROM I-VO", "32008R0593")
    for falsch in ("../bgb", "a/b", "Rom I-VO x", "-x", "a.b"):
        with pytest.raises(ValueError):
            quelle.pfadkuerzel(falsch, [])


def test_voreinstellung_enthaelt_unionsrecht():
    gesetze = {g["abk"]: g for g in quelle.voreinstellung()}
    assert gesetze["Rom I-VO"]["kuerzel"] == "32008R0593" and gesetze["Rom II-VO"]["kuerzel"] == "32007R0864"
    assert gesetze["DSGVO"]["kuerzel"] == "32016R0679" and gesetze["DSGVO"]["gruppe"] == "Unionsrecht"
    assert eurlex.ist_celex(gesetze["EuGVVO"]["kuerzel"])
