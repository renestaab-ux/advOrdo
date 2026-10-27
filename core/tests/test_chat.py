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
    monkeypatch.setattr(anbieter, "_OEFFNER_EXTERN", netz)
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
    monkeypatch.setattr(anbieter, "_OEFFNER_EXTERN", netz)
    for name, url, feld, temperatur in (
        ("openai_cloud", "https://api.openai.com/v1", "max_completion_tokens", False),
        ("mistral", "https://api.mistral.ai/v1", "max_tokens", True),
    ):
        e = anbieter.KiEinstellungen(aktiv="extern", extern_freigegeben=True, extern_anbieter=name,
                                     extern_modell="m")
        assert anbieter.erzeuge_aktiv(e, "schluessel").chat("s", "n", {"type": "object"}) == {"ok": True}
        adresse, kopf, daten = netz.anfragen[-1]
        assert adresse == url + "/chat/completions" and kopf["Authorization"] == "Bearer schluessel"
        assert daten[feld] == anbieter.EXTERN_ANTWORT_TOKEN and ("temperature" in daten) is temperatur
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
    monkeypatch.setattr(anbieter, "_OEFFNER_EXTERN", netz)
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
    monkeypatch.setattr(anbieter, "_OEFFNER_EXTERN", netz)
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
    monkeypatch.setattr(anbieter, "_OEFFNER_EXTERN", kaputt)
    with pytest.raises(anbieter.KiFehler, match="anderes Modell wählen"):
        gemma.chat("System", "Frage", {"type": "object"})
    assert len(kaputt.anfragen) == 2
    monkeypatch.setattr(anbieter, "_OEFFNER_EXTERN", netz)

    netz.antworten[":generateContent"] = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [
        {"text": '{"ok": tr'}]}}]}
    with pytest.raises(anbieter.KiFehler, match="abgeschnitten"):
        modell.chat("System", "Frage", {"type": "object"})
