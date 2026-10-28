import email.message
import io
import json
import urllib.error
import urllib.request
import urllib.response

import pytest

from juracore import netzprotokoll, rpc
from juracore.ki import anbieter
from juracore.ki.auftraege import Auftraege
from juracore.rechtsprechung import bayern


@pytest.fixture
def protokoll(tmp_path, monkeypatch):
    """Protokoll in einer Testdatei; statt einer Verbindung antwortet ein Stellvertreter (``antworten``)."""
    datei = tmp_path / "netzprotokoll.jsonl"
    gesehen: list[urllib.request.Request] = []
    antworten: dict[str, object] = {}

    def do_open(self, klasse, req, **kw):
        gesehen.append(req)
        a = next((v for k, v in antworten.items() if k in req.full_url), b"ok")
        if isinstance(a, BaseException):
            raise a
        code, inhalt = a if isinstance(a, tuple) else (200, a)
        antwort = urllib.response.addinfourl(io.BytesIO(inhalt), email.message.Message(), req.full_url, code)
        antwort.msg = "OK" if code == 200 else "Fehler"
        return antwort

    monkeypatch.setattr(urllib.request.AbstractHTTPHandler, "do_open", do_open)
    netzprotokoll.einrichten(datei)
    yield datei, gesehen, antworten
    netzprotokoll.einrichten(None)


def _eintraege(datei):
    return netzprotokoll.liste(datei)["eintraege"]


def test_jeder_abruf_ueber_urlopen_steht_im_protokoll(protokoll):
    datei, gesehen, _ = protokoll
    urllib.request.urlopen(urllib.request.Request("https://www.gesetze-im-internet.de/bgb/xml.zip"))
    urllib.request.urlopen("https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:32016R0679")
    neu, alt = _eintraege(datei)
    assert (alt["ziel"], alt["ort"], alt["zweck"], alt["methode"], alt["gesendet"], alt["status"]) == (
        "www.gesetze-im-internet.de", "internet", "Gesetz laden (BGB)", "GET", "", 200)
    assert neu["zweck"] == "Unionsrecht laden (CELEX 32016R0679)"
    assert neu["adresse"].endswith("?uri=CELEX:32016R0679") and len(gesehen) == 2


def test_formularfelder_im_wortlaut_ohne_pruefzeichen(protokoll):
    datei, gesehen, antworten = protokoll
    antworten["/Search/Hitlist"] = b'<input name="__RequestVerificationToken" value="geheim123" />'
    antworten["/Search"] = b"<html></html>"
    with netzprotokoll.anlass("Zitate der Akte online prüfen"):
        try:
            bayern.suche("7 U 1234/22")
        except ValueError:
            pass  # die leere Trefferliste ist hier gleich
    suche = next(e for e in _eintraege(datei) if e["methode"] == "POST")
    assert suche["zweck"] == "Zitate der Akte online prüfen: Entscheidungen suchen (Bayern)"
    assert suche["gesendet"] == "Formular: SearchFields.Aktenzeichen=7 U 1234/22"
    assert "geheim123" not in datei.read_text(encoding="utf-8")
    assert any(r.data and b"geheim123" in r.data for r in gesehen)  # gesendet wird es trotzdem


def test_schluessel_in_der_adresse_wird_geschwaerzt(protokoll):
    datei, _, _ = protokoll
    urllib.request.urlopen("https://nutzer:pw@example.org/feed?key=abc&x=1")
    e = _eintraege(datei)[0]
    assert e["adresse"] == "https://example.org/feed?key=***&x=1"
    assert "abc" not in datei.read_text(encoding="utf-8") and "pw@" not in datei.read_text(encoding="utf-8")


def test_fehler_und_http_status_werden_protokolliert(protokoll):
    datei, _, antworten = protokoll
    antworten["nicht-da"] = (404, b"")
    antworten["kaputt"] = urllib.error.URLError(ConnectionRefusedError("abgelehnt"))
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen("https://www.xrepository.de/nicht-da")
    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen("https://kaputt.example/")
    kaputt, nicht_da = _eintraege(datei)
    assert (nicht_da["zweck"], nicht_da["status"], nicht_da["fehler"]) == ("Gerichtsverzeichnis laden", 404, None)
    assert kaputt["status"] is None and "abgelehnt" in kaputt["fehler"]


def test_ki_anfrage_ohne_text_und_schluessel(protokoll):
    datei, gesehen, antworten = protokoll
    antworten["/v1/messages"] = json.dumps({"stop_reason": "end_turn", "content": [
        {"type": "text", "text": '{"aussagen": []}'}]}).encode()
    e = anbieter.KiEinstellungen(aktiv="extern", extern_freigegeben=True, extern_anbieter="anthropic",
                                 extern_modell="claude-opus-5-5")
    modell = anbieter.erzeuge_aktiv(e, "sk-ant-geheim-987")
    Auftraege().starte("chat", lambda _: modell.chat("System", "Vertraulicher Akteninhalt Brückner", {
        "type": "object", "properties": {}}), warten=True)
    eintrag = _eintraege(datei)[0]
    assert eintrag["zweck"].startswith("KI-Chat: Sprachmodell (")
    assert eintrag["gesendet"].startswith("Anfrage an claude-opus-5-5: ")
    assert eintrag["gesendet"].endswith("Zeichen (Text nicht protokolliert)")
    text = datei.read_text(encoding="utf-8")
    assert "Brückner" not in text and "sk-ant-geheim-987" not in text
    assert b"Br\xc3\xbcckner" in gesehen[0].data  # an den Anbieter geht der Inhalt (Modus „Extern“)


def test_lokales_modell_als_eigener_rechner(protokoll):
    datei, _, antworten = protokoll
    antworten["/api/tags"] = json.dumps({"models": []}).encode()
    anbieter._Http("http://127.0.0.1:11434", "Ollama").anfrage("/api/tags")
    e = _eintraege(datei)[0]
    assert (e["ort"], e["zweck"]) == ("geraet", "Sprachmodell (Ollama) – Modelle abfragen")
    assert netzprotokoll.liste(datei, nur_internet=True)["gesamt"] == 0


def test_export_csv_und_text(protokoll, tmp_path):
    datei, _, _ = protokoll
    urllib.request.urlopen("https://www.gesetze-im-internet.de/zpo/xml.zip")
    csv_datei = tmp_path / "protokoll.csv"
    assert netzprotokoll.exportieren(datei, str(csv_datei)) == {"pfad": str(csv_datei), "anzahl": 1}
    zeilen = csv_datei.read_text(encoding="utf-8-sig").splitlines()
    assert zeilen[0].startswith("Zeit;Ort;Ziel;Zweck;") and "Gesetz laden (ZPO)" in zeilen[1]
    assert "Internet;www.gesetze-im-internet.de" in zeilen[1]
    txt = tmp_path / "protokoll.txt"
    netzprotokoll.exportieren(datei, str(txt))
    inhalt = txt.read_text(encoding="utf-8")
    assert "Protokoll der Online-Anfragen" in inhalt and "Ergebnis: HTTP 200" in inhalt


def test_kuerzen_und_kaputte_zeilen(tmp_path, monkeypatch):
    datei = tmp_path / "p.jsonl"
    monkeypatch.setattr(netzprotokoll, "HOECHSTENS", 3)
    datei.write_text("".join(json.dumps({"zeit": f"2026-10-28T10:00:0{i}+01:00", "n": i}) + "\n" for i in range(5))
                     + '{"zeit": "halb', encoding="utf-8")
    assert [e["n"] for e in netzprotokoll.liste(datei)["eintraege"]] == [4, 3, 2]
    netzprotokoll._kuerze(datei)
    assert len(datei.read_text(encoding="utf-8").splitlines()) == 3


def test_rpc_protokoll(tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    try:
        assert kern.methoden["netz.protokoll"]() == {"eintraege": [], "gesamt": 0, "seit": None, "hoechstens": 5000}
        assert kern.netzprotokoll_datei == tmp_path / "netzprotokoll.jsonl"
    finally:
        netzprotokoll.einrichten(None)
