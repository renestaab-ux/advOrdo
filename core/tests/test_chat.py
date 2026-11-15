"""Chat mit Akte und Dokument sowie externe KI-Anbieter, ohne echtes Modell und ohne Netz.

Die Dokumente sind frei erfunden (dieselben Auszüge wie in test_ki.py).
"""

import io
import json
import os
import re
import sys
import urllib.error

import pytest

from juracore import rpc
from juracore.dokumente import akte
from juracore.ki import anbieter, chat

from .test_ki import Attrappe, _akte, _warte


@pytest.fixture
def akten(tmp_path):
    verbindung = akte.oeffne(tmp_path / "akten.sqlite")
    yield verbindung
    verbindung.close()


def _zeile(prompt: str, stueck: str) -> tuple[int, int]:
    """Dokument- und Absatznummer der Zeile „[d.n] …“ im Prompt, die das Textstück enthält."""
    for d, n, text in re.findall(r"^\[(\d+)\.(\d+)\] (.*)$", prompt, re.M):
        if stueck in text:
            return int(d), int(n)
    raise AssertionError(f"{stueck!r} nicht im Prompt")


def gute_antwort(prompt: str, schema: dict) -> dict:
    d, n = _zeile(prompt, "wie besehen")
    return {"aussagen": [
        {"text": "Das Autohaus lehnt die Nachbesserung ab.", "art": "tatsache",
         "belege": [{"dokument": d, "absatz": n, "zitat": "Wir lehnen eine Nachbesserung daher ab"}]},
        {"text": "Das Autohaus hat am 01.07.2025 geschrieben.", "art": "tatsache",
         "belege": [{"dokument": d, "absatz": n, "zitat": "Wir schreiben am ersten Juli zurück"}]},
        {"text": "Ein Gewährleistungsausschluss ist bei Verbrauchern unwirksam (§ 476 BGB).", "art": "einschaetzung",
         "belege": []},
        {"text": "Zur Kilometerleistung enthält das Schreiben nichts.", "art": "hinweis", "belege": []},
    ]}


def test_chat_mit_der_akte_prueft_belege_und_speichert_den_verlauf(akten, con, tmp_path):
    akte_id, _ = _akte(akten, con, tmp_path)
    modell = Attrappe(gute_antwort)
    antwort = chat.frage(akten, modell, 16384, akte_id, "Hat das Autohaus die Nachbesserung abgelehnt?")

    a = antwort["aussagen"]
    assert [x["status"] for x in a] == ["belegt", "ohne_beleg", "ohne_beleg", "hinweis"]
    assert a[0]["fundstellen"][0]["dateiname"] == "03_Antwortschreiben.md"
    assert a[0]["fundstellen"][0]["ausschnitt"]["wert"] == "Wir lehnen eine Nachbesserung daher ab"
    assert a[2]["art"] == "einschaetzung"
    assert antwort["auswahl"]["vollstaendig"] is True and antwort["auswahl"]["dokumente"] == 3
    # Alle drei Dokumente lagen vor, jedes mit eigener Nummer.
    assert "Dokument 1: 01_Kaufvertrag.md" in modell.anfragen[0] and "Dokument 3:" in modell.anfragen[0]

    verlauf = chat.verlauf(akten, akte_id)
    assert [v["rolle"] for v in verlauf] == ["frage", "antwort"]
    assert verlauf[0]["text"] == "Hat das Autohaus die Nachbesserung abgelehnt?"

    # Die nächste Frage bekommt den bisherigen Verlauf als Zusammenhang.
    chat.frage(akten, modell, 16384, akte_id, "Und warum?")
    assert "Bisheriger Verlauf" in modell.anfragen[1] and "Nachbesserung abgelehnt?" in modell.anfragen[1]
    assert len(chat.verlauf(akten, akte_id)) == 4
    # Der Chat mit der Akte ist getrennt von dem eines einzelnen Dokuments.
    assert chat.verlauf(akten, akte_id, dokument_id=1) == []
    assert chat.leeren(akten, akte_id)["geloescht"] == 4


def test_chat_mit_einem_dokument_sieht_nur_dieses(akten, con, tmp_path):
    akte_id, ids = _akte(akten, con, tmp_path)
    modell = Attrappe(gute_antwort)
    chat.frage(akten, modell, 16384, akte_id, "Was schreibt das Autohaus?", dokument_id=ids["03"])
    assert "Dokument 1: 03_Antwortschreiben.md" in modell.anfragen[0]
    assert "Kaufvertrag" not in modell.anfragen[0]
    assert len(chat.verlauf(akten, akte_id, ids["03"])) == 2 and chat.verlauf(akten, akte_id) == []
    with pytest.raises(LookupError):
        chat.frage(akten, modell, 16384, akte_id + 1, "x", dokument_id=ids["03"])


def test_grosse_akte_bekommt_eine_auswahl_nach_der_frage(akten, con, tmp_path):
    akte_id, _ = _akte(akten, con, tmp_path)
    viel = tmp_path / "09_Gutachten.md"
    viel.write_text("\n\n".join(f"Absatz {i} über die Lackierung der Tür, ohne Bezug." * 8 for i in range(150))
                    + "\n\nDer Wohnwagen wurde nie gezogen.", encoding="utf-8")
    akte.importiere(akten, con, akte_id, viel, tmp_path / "ablage", ocr=False)
    modell = Attrappe(lambda p, s: {"aussagen": []})
    antwort = chat.frage(akten, modell, 8192 + 1200 + 5000, akte_id, "Wurde ein Wohnwagen gezogen?")

    auswahl = antwort["auswahl"]
    assert auswahl["vollstaendig"] is False and auswahl["absaetze"] < auswahl["von"]
    prompt = modell.anfragen[0]
    assert "nie gezogen" in prompt and "Wohnwagen ziehen" in prompt  # die passenden Absätze
    assert "Dokument 1: 01_Kaufvertrag.md" in prompt  # der Kopf jedes Dokuments
    assert "nur eine Auswahl" in prompt


def test_rpc_chat_im_hintergrund(con, tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    kern.ki_fabrik = lambda e, schluessel=None: Attrappe(gute_antwort)
    akte_id, _ = _akte(kern.akten, con, tmp_path)

    def aufruf(methode, **params):
        antwort = kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))
        assert "error" not in antwort, antwort
        return antwort["result"]

    aufruf("ki.einstellungen_setzen", anbieter="ollama", endpunkt="http://127.0.0.1:9", modell=Attrappe.modell)
    auftrag = aufruf("ki.chat_fragen", akte_id=akte_id, frage="Lehnt das Autohaus ab?")
    stand = _warte(lambda: aufruf("ki.auftrag", auftrag_id=auftrag["auftrag_id"]))
    assert stand["status"] == "fertig", stand
    assert stand["ergebnis"]["aussagen"][0]["status"] == "belegt" and stand["ergebnis"]["extern"] is None
    assert len(aufruf("ki.chat_verlauf", akte_id=akte_id)) == 2
    assert aufruf("ki.chat_leeren", akte_id=akte_id) == {"geloescht": 2}


# --- Externe KI ------------------------------------------------------------------------------------


def test_externe_ki_nur_mit_schalter(tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    erhalten = []
    kern.ki_fabrik = lambda e, schluessel=None: erhalten.append((e.extern, schluessel)) or Attrappe(gute_antwort)

    def aufruf(methode, **params):
        return kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))

    # Voreinstellung: lokal, Schalter aus.
    stand = aufruf("ki.status")["result"]
    assert stand["aktiv"] == "lokal" and stand["externe"]["freigegeben"] is False
    assert aufruf("ki.modus")["result"]["aktiv"] == "lokal"

    # Extern wählen ohne Schalter geht nicht.
    fehler = aufruf("ki.extern_setzen", freigegeben=False, aktiv="extern")
    assert "nicht eingebunden" in fehler["error"]["message"]
    # Nur HTTPS für andere Anbieter.
    fehler = aufruf("ki.extern_setzen", freigegeben=True, anbieter="anderer", adresse="http://ki.example.org/v1")
    assert "HTTPS" in fehler["error"]["message"]

    geheim = "sk-ant-test-1234567890abcd"
    stand = aufruf("ki.extern_setzen", freigegeben=True, anbieter="anthropic", modell="claude-opus-5-5",
                   schluessel=geheim, aktiv="extern")["result"]
    assert stand["aktiv"] == "extern" and stand["bereit"] is True and stand["titel"] == "Anthropic Claude"
    assert stand["externe"]["schluessel_hinterlegt"] is True and stand["externe"]["schluessel_ende"] == "abcd"
    assert geheim not in json.dumps(stand)  # der Schlüssel geht nie an die Oberfläche
    assert geheim not in (tmp_path / "ki.json").read_text(encoding="utf-8")
    if sys.platform != "win32":
        assert os.stat(tmp_path / "ki-schluessel.json").st_mode & 0o077 == 0
    assert aufruf("ki.modus")["result"] == {"aus": False, "aktiv": "extern", "titel": "Anthropic Claude",
                                           "modell": "claude-opus-5-5", "ort": None}

    akte_id = aufruf("akten.anlegen", name="Test")["result"]["id"]
    pfad = tmp_path / "brief.md"
    pfad.write_text("Das Fahrzeug wurde wie besehen verkauft. Wir lehnen eine Nachbesserung daher ab.",
                    encoding="utf-8")
    aufruf("akten.importieren", akte_id=akte_id, pfad=str(pfad))
    auftrag = aufruf("ki.chat_fragen", akte_id=akte_id, frage="Was lehnt das Autohaus ab?")["result"]
    stand = _warte(lambda: aufruf("ki.auftrag", auftrag_id=auftrag["auftrag_id"])["result"])
    assert stand["ergebnis"]["extern"] == "Anthropic Claude"
    assert erhalten[-1] == (True, geheim)

    # Schalter aus: wieder lokal, ohne Schlüssel an die Fabrik.
    stand = aufruf("ki.extern_setzen", freigegeben=False)["result"]
    assert stand["aktiv"] == "lokal"
    aufruf("ki.einstellungen_setzen", anbieter="ollama", endpunkt="http://127.0.0.1:9", modell="m")
    aufruf("ki.chat_fragen", akte_id=akte_id, frage="Noch einmal?")
    assert erhalten[-1] == (False, None)
    # Schlüssel löschen.
    stand = aufruf("ki.extern_setzen", freigegeben=False, schluessel_loeschen=True)["result"]
    assert stand["externe"]["schluessel_hinterlegt"] is False


class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class _FalscherOeffner:
    """Steht für das Internet: merkt sich die Anfragen und antwortet je Adresse."""

    def __init__(self, antworten):
        self.antworten = antworten
        self.anfragen = []

    def open(self, req, timeout=None):
        daten = json.loads(req.data) if req.data else None
        self.anfragen.append((req.full_url, dict(req.header_items()), daten))
        for teil, antwort in self.antworten.items():
            if req.full_url.endswith(teil):
                return _Antwort(json.dumps(antwort).encode())
        raise AssertionError(req.full_url)


def test_anthropic_ueber_https(monkeypatch):
    netz = _FalscherOeffner({
        "/v1/models?limit=100": {"data": [{"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5"}]},
        "/v1/messages": {"stop_reason": "end_turn", "content": [
            {"type": "thinking", "thinking": ""}, {"type": "text", "text": '{"aussagen": []}'}]},
    })
    monkeypatch.setattr(anbieter, "_oeffner", lambda extern: netz)
    e = anbieter.KiEinstellungen(aktiv="extern", extern_freigegeben=True, extern_anbieter="anthropic",
                                 extern_modell="claude-opus-5-5")
    stand = anbieter.status_extern(e, "sk-ant-xyz-123456789", verbindung=True)
    assert stand["bereit"] is True and stand["modelle"][0]["name"] == "claude-opus-5-5"

    modell = anbieter.erzeuge_aktiv(e, "sk-ant-xyz-123456789")
    schema = {"type": "object", "properties": {"a": {"type": "object", "properties": {}}}}
    assert modell.chat("System", "Frage", schema) == {"aussagen": []}
    url, kopf, daten = netz.anfragen[-1]
    assert url == "https://api.anthropic.com/v1/messages"
    assert kopf["X-api-key"] == "sk-ant-xyz-123456789" and kopf["Anthropic-version"] == "2023-06-01"
    assert daten["system"] == "System" and "temperature" not in daten
    format_ = daten["output_config"]["format"]
    assert format_["type"] == "json_schema" and format_["schema"]["additionalProperties"] is False
    assert format_["schema"]["properties"]["a"]["additionalProperties"] is False

    netz.antworten["/v1/messages"] = {"stop_reason": "refusal", "content": []}
    with pytest.raises(anbieter.KiFehler, match="abgelehnt"):
        modell.chat("System", "Frage", schema)


def test_openai_und_mistral_ueber_https(monkeypatch):
    antwort = {"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]}
    netz = _FalscherOeffner({"/chat/completions": antwort,
                             "/models": {"data": [{"id": "gpt-x"}, {"id": "text-embedding-3"}]}})
    monkeypatch.setattr(anbieter, "_oeffner", lambda extern: netz)
    for name, url, feld, temperatur, laenge in (
        ("openai_cloud", "https://api.openai.com/v1", "max_completion_tokens", False, anbieter.EXTERN_ANTWORT_TOKEN),
        ("mistral", "https://api.mistral.ai/v1", "max_tokens", True, anbieter.ANTWORT_TOKEN),
    ):
        e = anbieter.KiEinstellungen(aktiv="extern", extern_freigegeben=True, extern_anbieter=name,
                                     extern_modell="m")
        assert anbieter.erzeuge_aktiv(e, "schluessel").chat("s", "n", {"type": "object"}) == {"ok": True}
        adresse, kopf, daten = netz.anfragen[-1]
        assert adresse == url + "/chat/completions" and kopf["Authorization"] == "Bearer schluessel"
        assert daten[feld] == laenge and ("temperature" in daten) is temperatur
    # Modellnamen ohne „models/“, ohne Einbettungsmodelle.
    assert [m["name"] for m in anbieter.erzeuge_aktiv(e, "schluessel").modelle()] == ["gpt-x"]


def test_ohne_schalter_kein_externes_modell():
    e = anbieter.KiEinstellungen(aktiv="extern", extern_freigegeben=False, extern_modell="m").pruefen()
    assert e.aktiv == "lokal" and e.extern is False
    with pytest.raises(anbieter.KiFehler, match="nicht eingebunden"):
        anbieter.erzeuge_extern(e, "schluessel")
    with pytest.raises(anbieter.KiFehler, match="kein API-Schlüssel"):
        anbieter.erzeuge_extern(anbieter.KiEinstellungen(extern_freigegeben=True), None)


class _Fehler500(_FalscherOeffner):
    """Wie Google mit strukturierter Ausgabe: erst Serverfehler, ohne Schema eine Antwort."""

    def open(self, req, timeout=None):
        daten = json.loads(req.data) if req.data else None
        if daten and "responseJsonSchema" in daten["generationConfig"]:
            self.anfragen.append((req.full_url, dict(req.header_items()), daten))
            raise urllib.error.HTTPError(req.full_url, 500, "Internal", {}, io.BytesIO(
                b'{"error": {"code": 500, "message": "Internal error encountered.", "status": "INTERNAL"}}'))
        return super().open(req, timeout)


def test_gemini_ueber_die_eigene_schnittstelle(monkeypatch):
    antwort = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": "Überlegung", "thought": True}, {"text": '{"ok": true}'}]}}]}
    netz = _FalscherOeffner({
        ":generateContent": antwort,
        "/models?pageSize=1000": {"models": [
            {"name": "models/gemini-2.5-pro", "displayName": "Gemini 2.5 Pro",
             "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]}]},
    })
    monkeypatch.setattr(anbieter, "_oeffner", lambda extern: netz)
    e = anbieter.KiEinstellungen(aktiv="extern", extern_freigegeben=True, extern_anbieter="gemini",
                                 extern_modell="gemini-2.5-pro")
    modell = anbieter.erzeuge_aktiv(e, "schluessel")
    assert [m["name"] for m in modell.modelle()] == ["gemini-2.5-pro"]
    assert modell.chat("System", "Frage", {"type": "object"}) == {"ok": True}
    url, kopf, daten = netz.anfragen[-1]
    assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"
    assert kopf["X-goog-api-key"] == "schluessel"
    assert daten["systemInstruction"]["parts"][0]["text"] == "System"
    konfig = daten["generationConfig"]
    assert konfig["responseMimeType"] == "application/json"
    assert konfig["responseJsonSchema"] == {"type": "object", "additionalProperties": False}

    # Serverfehler mit Schema: zweiter Versuch ohne Schema-Zwang, das Schema steht in der Anweisung.
    netz = _Fehler500(netz.antworten)
    monkeypatch.setattr(anbieter, "_oeffner", lambda extern: netz)
    assert modell.chat("System", "Frage", {"type": "object"}) == {"ok": True}
    assert len(netz.anfragen) == 2
    zweite = netz.anfragen[-1][2]
    assert "responseJsonSchema" not in zweite["generationConfig"] and "systemInstruction" not in zweite
    assert "JSON-Schema" in zweite["contents"][0]["parts"][0]["text"]

    # Gemma-Modelle bei Google: gleich ohne Systemanweisung und JSON-Modus.
    gemma = anbieter.GoogleGemini("models/gemma-4-31b-it", "schluessel")
    assert gemma.chat("System", "Frage", {"type": "object"}) == {"ok": True}
    url, _, daten = netz.anfragen[-1]
    assert url.endswith("/models/gemma-4-31b-it:generateContent")
    assert "systemInstruction" not in daten and "responseMimeType" not in daten["generationConfig"]

    # Serverfehler auch ohne Schema: ein zweiter Versuch, danach eine Meldung mit Ausweg.
    monkeypatch.setattr(anbieter.GoogleGemini, "PAUSE", 0)

    class _Immer500(_FalscherOeffner):
        def open(self, req, timeout=None):
            self.anfragen.append((req.full_url, dict(req.header_items()), json.loads(req.data)))
            raise urllib.error.HTTPError(req.full_url, 500, "Internal", {}, io.BytesIO(
                b'{"error": {"code": 500, "message": "Internal error encountered."}}'))

    kaputt = _Immer500({})
    monkeypatch.setattr(anbieter, "_oeffner", lambda extern: kaputt)
    with pytest.raises(anbieter.KiFehler, match="anderes Modell wählen"):
        gemma.chat("System", "Frage", {"type": "object"})
    assert len(kaputt.anfragen) == 2
    monkeypatch.setattr(anbieter, "_oeffner", lambda extern: netz)

    netz.antworten[":generateContent"] = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [
        {"text": '{"ok": tr'}]}}]}
    with pytest.raises(anbieter.KiFehler, match="abgeschnitten"):
        modell.chat("System", "Frage", {"type": "object"})


class _ZuViele(_FalscherOeffner):
    """Wie ein kostenloser Tarif: die ersten Anfragen mit 429, dann eine Antwort."""

    def __init__(self, antworten, fehlschlaege, retry_after=None, code=429):
        super().__init__(antworten)
        self.code = code
        self.fehlschlaege = fehlschlaege
        self.retry_after = retry_after

    def open(self, req, timeout=None):
        if self.fehlschlaege > 0:
            self.fehlschlaege -= 1
            self.anfragen.append((req.full_url, {}, None))
            kopf = {"Retry-After": self.retry_after} if self.retry_after else {}
            raise urllib.error.HTTPError(req.full_url, self.code, "Too Many Requests", kopf,
                                         io.BytesIO(b'{"message": "Rate limit exceeded"}'))
        return super().open(req, timeout)


def test_mistral_429_wartet_und_versucht_erneut(monkeypatch):
    pausen = []
    monkeypatch.setattr(anbieter.netzprotokoll.time, "sleep", pausen.append)
    antwort = {"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]}
    e = anbieter.KiEinstellungen(aktiv="extern", extern_freigegeben=True, extern_anbieter="mistral", extern_modell="m")

    netz = _ZuViele({"/chat/completions": antwort}, fehlschlaege=2, retry_after="2")
    monkeypatch.setattr(anbieter, "_oeffner", lambda extern: netz)
    assert anbieter.erzeuge_aktiv(e, "schluessel").chat("s", "n", {"type": "object"}) == {"ok": True}
    assert pausen == [2.0, 2.0] and len(netz.anfragen) == 3

    pausen.clear()
    netz = _ZuViele({"/chat/completions": antwort}, fehlschlaege=9)
    monkeypatch.setattr(anbieter, "_oeffner", lambda extern: netz)
    with pytest.raises(anbieter.KiFehler, match="keine weiteren Anfragen zu .*Rate limit exceeded.*3-mal"):
        anbieter.erzeuge_aktiv(e, "schluessel").chat("s", "n", {"type": "object"})
    assert pausen == list(anbieter._Http.WARTEN_429)


def test_ueberlastet_503_wartet_ebenfalls(monkeypatch):
    pausen = []
    monkeypatch.setattr(anbieter.netzprotokoll.time, "sleep", pausen.append)
    e = anbieter.KiEinstellungen(aktiv="extern", extern_freigegeben=True, extern_anbieter="mistral", extern_modell="m")
    netz = _ZuViele({}, fehlschlaege=9, code=503)
    monkeypatch.setattr(anbieter, "_oeffner", lambda extern: netz)
    with pytest.raises(anbieter.KiFehler, match="überlastet .*3-mal"):
        anbieter.erzeuge_aktiv(e, "schluessel").chat("s", "n", {"type": "object"})
    assert len(pausen) == 3


def test_klauselpruefung_nennt_die_bestimmungen_des_vertrags(akten, con, tmp_path):
    """Ein gegliederter Vertrag (frei erfunden): Absätze tragen ihre Bestimmung, die Fundstelle nennt sie."""
    akte_id = akte.akte_anlegen(akten, "Studio ./. Kundin")["id"]
    vertrag = tmp_path / "Mitgliedsvertrag.md"
    vertrag.write_text(
        "Mitgliedsvertrag Studio Muster\n\n§ 1 Leistungen\n\n(1) Das Studio stellt Trainingsflächen bereit.\n\n"
        "§ 2 Laufzeit\n\n(1) Die Erstlaufzeit beträgt 24 Monate.\n\n"
        "(2) Der Vertrag verlängert sich danach jeweils um weitere 12 Monate.\n\n"
        "§ 6 Haftung\n\n(1) Das Studio haftet nicht für Schäden, gleich aus welchem Rechtsgrund.\n",
        encoding="utf-8")
    akte.importiere(akten, con, akte_id, vertrag, tmp_path / "ablage", ocr=False)

    def antwort(prompt: str, schema: dict) -> dict:
        if "aussagen" not in schema["properties"]:  # vorab: Verbraucher oder Unternehmer?
            return {"ergebnis": "verbraucher", "text": "Die Kundin schließt den Vertrag privat.",
                    "belege": [{"dokument": 1, "absatz": 1, "zitat": "Mitgliedsvertrag Studio Muster"}]}
        assert schema["properties"]["aussagen"]["items"]["properties"]["ergebnis"]["enum"] == [
            "unwirksam", "bedenklich", "wirksam"]
        if "Zu prüfen: § 6" in prompt:
            d, n = _zeile(prompt, "gleich aus welchem")
            return {"aussagen": [{"text": "§ 6 Abs. 1 des Vertrags: unwirksam ([1.8]).", "art": "tatsache",
                                  "ergebnis": "unwirksam", "belege": [
                {"dokument": d, "absatz": n, "zitat": "{§ 6 Abs. 1} Das Studio haftet nicht für Schäden"}]}]}
        d, n, stueck = next((int(d), int(n), s) for d, n, s in re.findall(r"^\[(\d+)\.(\d+)\] \{§ \d+ Abs\. 1\} (.*)$",
                                                                        prompt, re.M))
        return {"aussagen": [{"text": f"{stueck[:12]}: keine Bedenken.", "art": "einschaetzung", "ergebnis": "wirksam",
                              "belege": [{"dokument": d, "absatz": n, "zitat": stueck}]}]}

    modell = Attrappe(antwort)
    ergebnis = chat.frage(akten, modell, 16384, akte_id, "Welche Klauseln sind unwirksam?")
    # Eine Anfrage je Paragraph, jede mit dem Kopf des Vertrags als Zusammenhang.
    assert len(modell.anfragen) == 4 and all("Studio Muster" in a for a in modell.anfragen)
    assert all("ist nach dem Vertrag Verbraucher (§ 13 BGB)" in a for a in modell.anfragen[1:])
    assert "{§ 2 Abs. 2} (2) Der Vertrag verlängert sich" in modell.anfragen[2]
    assert "§ 6 Haftung" not in modell.anfragen[2]
    a = ergebnis["aussagen"]
    assert a[0]["text"].endswith("Wohl unwirksam: § 6 Abs. 1. Ohne Bedenken: § 1 Abs. 1, § 2 Abs. 1.")
    assert a[1]["text"] == "Vertragspartner: Die Kundin schließt den Vertrag privat." and a[1]["status"] == "belegt"
    assert a[2]["status"] == "belegt" and a[2]["fundstellen"][0]["bestimmung"] == "§ 6 Abs. 1"
    assert a[2]["text"] == "§ 6 Abs. 1 des Vertrags: unwirksam." and a[2]["art"] == "einschaetzung"
    assert ergebnis["auswahl"]["je_bestimmung"] and "klausel" not in a[2]
    # Ohne Frage nach Klauseln keine Prüfanweisung, die Kennzeichen bleiben.
    modell = Attrappe(lambda p, s: {"aussagen": []})
    chat.frage(akten, modell, 16384, akte_id, "Wie lange läuft der Vertrag?")
    assert len(modell.anfragen) == 1 and "{§ 2 Abs. 1}" in modell.anfragen[0]


def test_gesetze_weichen_einem_vertrag_der_sonst_nicht_ganz_passt(akten, con, tmp_path):
    akte_id, _ = _akte(akten, con, tmp_path)
    texte = [chat.belege.lade_text(akten, i, chat.PARTEIEN)
             for (i,) in akten.execute("SELECT id FROM dokument WHERE akte_id = ?", (akte_id,))]
    modell = Attrappe(gute_antwort)
    assert chat._gesetze_budget(texte, 32768, modell, 0) == chat.wissen.GESETZE_ZEICHEN
    assert chat._gesetze_budget(texte, 8192 + 1200 + 1000, modell, 0) == chat.GESETZE_MINDESTENS


def test_skills_weichen_den_dokumenten():
    from juracore.ki import belege
    text = belege.Text(1, "v.md", [], [{"nr": 1, "text": "Vertrag " * 600, "seite": 1, "seitenwechsel": "[]",
                                        "rn": None}])
    skills = [{"name": "eins", "text": "a" * 2000}, {"name": "zwei", "text": "b" * 9000}]
    modell = Attrappe(gute_antwort)
    behalten, weg = chat._skills_kuerzen(skills, [text], 8192 + 1200 + 5000, modell, 0)
    assert [s["name"] for s in behalten] == ["eins"] and weg == ["zwei"]
    assert chat._skills_kuerzen(skills, [text], 32768, modell, 0) == (skills, [])


def test_verlesene_ueberschrift_und_angehaengte_ueberschrift_im_scan():
    from juracore.ki import belege

    def a(nr, text):
        return {"nr": nr, "text": text, "seite": 1, "seitenwechsel": "[]", "rn": None}

    # So liest die Texterkennung manchmal (frei erfunden): „§ 10“ als „810“, „§ 5“ am Ende des vorigen Absatzes.
    t = belege.Text(1, "scan.pdf", [], [
        a(1, "§ 4 Rücklastschriften"),
        a(2, "(2) Für jede Rücklastschrift berechnet das Studio 25,00 €. Weitere Ansprüche bleiben vorbehalten. "
             "§ 5 Ruhen des Vertrags"),
        a(3, "(1) Bei Krankheit ruht der Vertrag."),
        a(4, "§ 9 Hausordnung"), a(5, "(1) Es gilt die Hausordnung."),
        a(6, "810 Gerichtsstand, Schlussbestimmungen"), a(7, "(1) Gerichtsstand ist Freiburg."),
        a(8, "810 Mitglieder haben sich angemeldet."), a(9, "$& 11 Schlussbestimmungen"), a(10, "(1) Ende."),
    ])
    assert chat._bestimmungen(t, 7) == "{§ 10 Abs. 1} "
    assert chat._bestimmungen(t, 8) == "{§ 10 Abs. 1} "  # „§ 11“ wäre die nächste Nummer, nicht „10“
    assert chat._bestimmungen(t, 10) == "{§ 11 Abs. 1} "  # so las Tesseract den Scan bei René
    gruppen = {p: [x["nr"] for x in absaetze] for _, _, p, absaetze in chat._paragraphen([t])}
    assert gruppen["§ 4"] == [1, 2] and gruppen["§ 5"] == [3] and gruppen["§ 10"] == [6, 7, 8]
    assert gruppen["§ 11"] == [9, 10]


def test_klauselpruefung_waehlt_skills_je_paragraph(akten, con, tmp_path):
    akte_id = akte.akte_anlegen(akten, "Studio ./. Kundin")["id"]
    vertrag = tmp_path / "Vertrag.md"
    vertrag.write_text("Vertrag Studio Muster\n\n§ 1 Leistungen\n\n(1) Das Studio stellt Geräte bereit.\n\n"
                       "§ 2 Gerichtsstand\n\n(1) Gerichtsstand ist Freiburg im Breisgau.\n", encoding="utf-8")
    akte.importiere(akten, con, akte_id, vertrag, tmp_path / "ablage", ocr=False)
    systeme: list[str] = []

    class Modell(Attrappe):
        def chat(self, system, nutzer, schema):
            systeme.append(system)
            return super().chat(system, nutzer, schema)

    eigener = {"id": "g", "name": "gerichtsstand-pruefen", "text": "Prüfe § 38 ZPO für Verbraucher."}
    allgemein = {"id": "a", "name": "agb-allgemein", "text": "Prüfe §§ 307 ff. BGB."}
    ergebnis = chat.frage(akten, Modell(lambda p, s: {"aussagen": []}), 16384, akte_id,
                          "Welche Klauseln sind unwirksam?", skills=[allgemein],
                          skill_waehler=lambda text: [eigener] if "Gerichtsstand" in text else [])
    # Vorab-Anfrage und § 1 mit dem allgemeinen Skill, § 2 mit dem passenden.
    assert ["38 ZPO" in s for s in systeme] == [False, False, True]
    assert "307 ff." in systeme[1] and "307 ff." not in systeme[2]
    assert ergebnis["skills"] == ["agb-allgemein", "gerichtsstand-pruefen"]


def test_pauschale_aussage_zum_paragraphen_entfaellt_neben_einzelnen(akten, con, tmp_path):
    akte_id = akte.akte_anlegen(akten, "Studio ./. Kundin")["id"]
    vertrag = tmp_path / "Vertrag.md"
    vertrag.write_text("Vertrag Studio Muster, Mitglied Erika Muster\n\n§ 1 Leistungen\n\n(1) Das Studio stellt "
                       "Geräte bereit.\n\n§ 2 Laufzeit\n\n(1) Der Vertrag läuft zwei Jahre lang.\n", encoding="utf-8")
    akte.importiere(akten, con, akte_id, vertrag, tmp_path / "ablage", ocr=False)

    def antwort(prompt, schema):
        if "aussagen" not in schema["properties"]:
            assert "Frage des Nutzers: Welche Klauseln" in prompt
            return {"ergebnis": "verbraucher", "text": "Privatperson.", "belege": []}
        p = "§ 1" if "Zu prüfen: § 1" in prompt else "§ 2"
        return {"aussagen": [
            {"text": f"{p} Abs. 1 des Vertrags: keine Bedenken.", "art": "einschaetzung", "ergebnis": "wirksam",
             "belege": []},
            {"text": f"{p} des Vertrags: keine Bedenken.", "art": "einschaetzung", "ergebnis": "wirksam",
             "belege": []}]}

    texte = [a["text"] for a in chat.frage(akten, Attrappe(antwort), 16384, akte_id,
                                           "Welche Klauseln sind unwirksam?")["aussagen"]]
    assert "§ 1 Abs. 1 des Vertrags: keine Bedenken." in texte and "§ 1 des Vertrags: keine Bedenken." not in texte


def test_uebersicht_nennt_jede_bestimmung_nur_unter_dem_schaerfsten_ergebnis():
    def a(text, klausel, bestimmung):
        return {"text": text, "klausel": klausel, "fundstellen": [{"bestimmung": bestimmung}]}

    aus = chat._klauseln_ordnen([a("x", "unwirksam", "§ 3 Abs. 3"), a("y", "bedenklich", "§ 3 Abs. 3"),
                                 a("z", "bedenklich", "§ 10 Abs. 2"), a("w", "wirksam", "§ 10 Abs. 2"),
                                 a("v", "wirksam", "§ 1 Abs. 1")])
    assert aus[0]["text"].endswith("Wohl unwirksam: § 3 Abs. 3. Bedenklich: § 10 Abs. 2. Ohne Bedenken: § 1 Abs. 1.")
