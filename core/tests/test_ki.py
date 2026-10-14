"""Sprachmodell-Anbindung: ohne echtes Modell, mit einer Attrappe und einem nachgebauten Ollama-Server.

Die Dokumente sind frei erfunden (angelehnt an die fiktive Testakte Brückner).
"""

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from juracore import rpc
from juracore.dokumente import akte
from juracore.ki import anbieter, belege, speicher
from juracore.ki.analyse import Analyse
from juracore.ki.auftraege import Auftraege

KAUFVERTRAG = """Kaufvertrag über ein gebrauchtes Kraftfahrzeug

Käuferin: Dr. Lena Brückner, Verkäufer: Autohaus Rehnfeld GmbH

5. Besondere Vereinbarungen

Neue Bremsbeläge vorne. Fahrzeug ohne Anhängerkupplung.
"""

ANTWORTSCHREIBEN = """Sehr geehrte Frau Albrecht,

wir haben das Fahrzeug am 27.06.2025 kurz in Augenschein genommen.

Das Fahrzeug wurde wie besehen verkauft. Wir lehnen eine Nachbesserung daher ab und sehen die Angelegenheit als erledigt an.
"""

KLAGEERWIDERUNG = """Klageerwiderung

(4) Die Klägerin hat bei Übergabe gegenüber Herrn Pfister geäußert, sie werde mit dem Fahrzeug regelmäßig einen Wohnwagen ziehen.

(5) Unzutreffend ist, dass die Beklagte die Nacherfüllung verweigert habe. Der Geschäftsführer der Beklagten hat der Klägerin am 02.07.2025 telefonisch angeboten, das Fahrzeug kostenfrei zu untersuchen und gegebenenfalls nachzubessern.
"""


class Attrappe:
    """Steht für das Sprachmodell: beantwortet jede Anfrage über eine Funktion und merkt sich die Anfragen."""

    modell = "attrappe:1b"

    def __init__(self, antwort):
        self.antwort = antwort
        self.anfragen: list[str] = []

    def chat(self, system, nutzer, schema):
        self.anfragen.append(nutzer)
        return self.antwort(nutzer, schema)


def absatz(prompt: str, stueck: str) -> int:
    """Nummer der Zeile „[n] …“ im Prompt, die das Textstück enthält."""
    for nr, text in re.findall(r"^\[(\d+)\] (.*)$", prompt, re.M):
        if stueck in text:
            return int(nr)
    raise AssertionError(f"{stueck!r} nicht im Prompt")


def kennung(prompt: str, stueck: str) -> str:
    for k, text in re.findall(r"^\[(A\d+)\] (.*)$", prompt, re.M):
        if stueck in text:
            return k
    raise AssertionError(f"{stueck!r} nicht unter den Angaben")


def angaben_antwort(prompt: str) -> dict:
    """So würde ein gutes Modell die Tatsachenangaben je Dokument liefern (plus eine erfundene)."""
    if "Kaufvertrag" in prompt.split("\n", 1)[0]:
        return {"angaben": [
            {"text": "Das Fahrzeug hat keine Anhängerkupplung.", "haltung": "behauptet",
             "absatz": absatz(prompt, "ohne Anhängerkupplung"), "zitat": "Fahrzeug ohne Anhängerkupplung."},
        ]}
    if "Antwortschreiben" in prompt.split("\n", 1)[0]:
        return {"angaben": [
            # Falsche Absatznummer, das Zitat steht aber im Dokument: wird dem richtigen Absatz zugeordnet.
            {"text": "Das Autohaus lehnt eine Nachbesserung ab.", "haltung": "behauptet",
             "absatz": 1, "zitat": "Wir lehnen eine Nachbesserung daher ab"},
            # Erfundenes Zitat: wird verworfen.
            {"text": "Das Autohaus hat den Kaufpreis erstattet.", "haltung": "behauptet",
             "absatz": 2, "zitat": "Wir haben den Kaufpreis vollständig erstattet"},
        ]}
    return {"angaben": [
        {"text": "Die Klägerin wollte regelmäßig einen Wohnwagen ziehen.", "haltung": "behauptet",
         "absatz": absatz(prompt, "Wohnwagen"), "zitat": "sie werde mit dem Fahrzeug regelmäßig einen Wohnwagen ziehen"},
        {"text": "Der Geschäftsführer bot am 02.07.2025 die Nachbesserung an.", "haltung": "behauptet",
         "absatz": absatz(prompt, "telefonisch angeboten"),
         "zitat": "hat der Klägerin am 02.07.2025 telefonisch angeboten, das Fahrzeug kostenfrei zu untersuchen"},
    ]}


def modell_antwort(prompt: str, schema: dict) -> dict:
    if "widersprueche" in schema["properties"]:
        ablehnung, angebot = kennung(prompt, "lehnt eine Nachbesserung"), kennung(prompt, "bot am 02.07.2025")
        wohnwagen, kupplung = kennung(prompt, "Wohnwagen"), kennung(prompt, "keine Anhängerkupplung")
        return {"widersprueche": [
            {"thema": "Nachbesserungsbereitschaft", "art": "widerspruch",
             "erklaerung": "Abgelehnt laut Schreiben, angeboten laut Klageerwiderung.", "angaben": [ablehnung, angebot]},
            {"thema": "Anhängerbetrieb", "art": "spannung",
             "erklaerung": "Ohne Anhängerkupplung lässt sich kein Wohnwagen ziehen.", "angaben": [f"[{wohnwagen}]", kupplung]},
            {"thema": "Erfunden", "art": "widerspruch", "erklaerung": "Kennung gibt es nicht.", "angaben": ["A1", "A99"]},
            {"thema": "Doppelt", "art": "widerspruch", "erklaerung": "Schon genannt.", "angaben": [angebot, ablehnung]},
        ]}
    if "angaben" in schema["properties"]:
        return angaben_antwort(prompt)
    if "quellen" in json.dumps(schema):
        return {"aussagen": [{"text": "Streit um die Nachbesserung.", "art": "streitig", "quellen": ["A1", "A2"]},
                             {"text": "Ohne Quelle.", "art": "offen", "quellen": ["A77"]}]}
    if "Antwortschreiben" not in prompt.split("\n", 1)[0]:
        erste = re.search(r"^\[(\d+)\] (.*)$", prompt, re.M)
        return {"aussagen": [{"text": "Ein Dokument.", "art": "tatsache",
                              "belege": [{"absatz": int(erste.group(1)), "zitat": erste.group(2)}]}]}
    return {"aussagen": [
        {"text": "Schreiben des Autohauses.", "art": "tatsache",
         "belege": [{"absatz": 7, "zitat": "wir haben das Fahrzeug am 27.06.2025 kurz in Augenschein genommen"}]},
        {"text": "Das Autohaus lehnt die Nachbesserung ab.", "art": "vortrag",
         "belege": [{"absatz": absatz(prompt, "lehnen"), "zitat": "„Wir lehnen eine Nachbesserung daher ab“"}]},
        {"text": "Erfundene Aussage.", "art": "vortrag", "belege": [{"absatz": 1, "zitat": "Das steht nirgends im Text."}]},
    ]}


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    yield con
    con.close()


def _akte(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Brückner ./. Autohaus")
    ids = {}
    for name, text, tag in (("01_Kaufvertrag.md", KAUFVERTRAG, "Kläger"),
                            ("03_Antwortschreiben.md", ANTWORTSCHREIBEN, "Beklagter"),
                            ("06_Klageerwiderung.md", KLAGEERWIDERUNG, "Beklagter")):
        pfad = tmp_path / name
        pfad.write_text(text, encoding="utf-8")
        ids[name[:2]] = akte.importiere(akten, con, a["id"], pfad, tmp_path / "ablage", ocr=False, tags=[tag])[
            "dokument_id"
        ]
    return a["id"], ids


# --- Nur lokal ------------------------------------------------------------------------------------


@pytest.mark.parametrize("endpunkt", ["http://localhost:11434", "http://127.0.0.1:11434/", "http://[::1]:1234",
                                      "https://127.0.0.2:8443"])
def test_lokale_endpunkte_sind_erlaubt(endpunkt):
    assert anbieter.pruefe_lokal(endpunkt) == endpunkt.rstrip("/")


@pytest.mark.parametrize("endpunkt", ["http://192.168.1.20:11434", "https://api.example.com", "http://localhost.evil.de",
                                      "ftp://127.0.0.1", "127.0.0.1:11434"])
def test_entfernte_endpunkte_werden_abgelehnt(endpunkt):
    with pytest.raises(ValueError):
        anbieter.pruefe_lokal(endpunkt)


def test_einstellungen_speichern_und_laden(tmp_path):
    pfad = tmp_path / "ki.json"
    assert anbieter.lade_einstellungen(pfad).anbieter == "ollama"
    anbieter.speichere_einstellungen(pfad, anbieter.KiEinstellungen("ollama", "http://localhost:11434", "qwen3:14b"))
    assert anbieter.lade_einstellungen(pfad).modell == "qwen3:14b"
    with pytest.raises(ValueError):
        anbieter.speichere_einstellungen(pfad, anbieter.KiEinstellungen("ollama", "http://10.0.0.5:11434", "x"))
    # Eine von Hand auf eine fremde Adresse geänderte Datei fällt auf die Voreinstellung zurück.
    pfad.write_text(json.dumps({"endpunkt": "http://10.0.0.5:11434", "modell": "x"}), encoding="utf-8")
    assert anbieter.lade_einstellungen(pfad).endpunkt == "http://127.0.0.1:11434"


def test_antwort_mit_denkabschnitt_und_codezaun():
    assert anbieter.lies_json('<think>hm</think>\n```json\n{"a": 1}\n```') == {"a": 1}
    assert anbieter.lies_json('Hier: {"a": [1]} fertig') == {"a": [1]}
    with pytest.raises(anbieter.KiFehler):
        anbieter.lies_json("keine Ahnung")


# --- Belege ---------------------------------------------------------------------------------------


ABSCHNITTE = {
    1: "Das Fahrzeug wurde wie besehen verkauft.",
    2: "Wir lehnen eine Nach-­besserung   daher ab und sehen die Angelegenheit als „erledigt“ an.",
    3: "Der Geschäftsführer hat der Klägerin am 02.07.2025 telefonisch angeboten, das Fahrzeug zu untersuchen.",
}


def test_zitat_wird_woertlich_gefunden_trotz_schreibweise():
    fund = belege.finde('wir lehnen eine Nach-besserung daher ab und sehen die Angelegenheit als "erledigt" an', ABSCHNITTE, 2)
    assert (fund.abschnitt, fund.treffer) == (2, belege.WOERTLICH)
    assert ABSCHNITTE[2][fund.start : fund.ende].startswith("Wir lehnen")
    assert ABSCHNITTE[2][fund.start : fund.ende].endswith("an")


def test_falsche_absatznummer_wird_berichtigt():
    fund = belege.finde("telefonisch angeboten, das Fahrzeug zu untersuchen", ABSCHNITTE, 1)
    assert fund.abschnitt == 3


def test_zitat_mit_auslassung_und_kleinem_fehler():
    fund = belege.finde("Der Geschäftsführer … telefonisch angeboten", ABSCHNITTE, 3)
    assert fund.treffer == belege.WOERTLICH and ABSCHNITTE[3][fund.start :].startswith("Der Geschäftsführer")
    fund = belege.finde("Der Geschäftsführer hat der Klägerin am 02.07.2025 telefonish angeboten", ABSCHNITTE, 3)
    assert fund.treffer == belege.ANGENAEHERT and fund.abschnitt == 3


def test_erfundene_und_zu_kurze_zitate_belegen_nichts():
    assert belege.finde("Der Kaufpreis wurde vollständig erstattet", ABSCHNITTE, 1) is None
    assert belege.finde("Wir", ABSCHNITTE, 2) is None
    assert belege.finde(None, ABSCHNITTE, 2) is None


# --- Analyse mit der Attrappe ----------------------------------------------------------------------


def test_widersprueche_ohne_zahl_oder_datum(akten, con, tmp_path):
    akte_id, ids = _akte(akten, con, tmp_path)
    modell = Attrappe(modell_antwort)
    ergebnis = Analyse(akten, modell).widersprueche(akte_id)

    assert ergebnis["angaben"] == 4 and ergebnis["verworfen"] == 1
    themen = [w["thema"] for w in ergebnis["widersprueche"]]
    assert themen == ["Nachbesserungsbereitschaft", "Anhängerbetrieb"]  # erfundene Kennung und Dublette entfallen

    w6 = ergebnis["widersprueche"][0]
    assert w6["einordnung"] == ["innerhalb_partei"]
    stellen = [a["fundstelle"] for a in w6["angaben"]]
    assert [f["dokument_id"] for f in stellen] == [ids["03"], ids["06"]]
    assert stellen[0]["ausschnitt"]["wert"] == "Wir lehnen eine Nachbesserung daher ab"
    assert stellen[1]["rn"] == 5 and stellen[1]["parteien"] == ["Beklagter"]

    w7 = ergebnis["widersprueche"][1]
    assert w7["art"] == "spannung" and w7["einordnung"] == ["zwischen_parteien"]
    assert {a["fundstelle"]["rn"] for a in w7["angaben"]} == {4, None}

    # Gespeichert: ein zweiter Lauf fragt das Modell nicht mehr.
    anzahl = len(modell.anfragen)
    assert Analyse(akten, modell).widersprueche(akte_id)["gespeichert"] is True
    assert len(modell.anfragen) == anzahl
    # Neu berechnen auf Wunsch: nur der Vergleich, die Angaben je Dokument bleiben gespeichert.
    Analyse(akten, modell, neu=True).widersprueche(akte_id)
    assert len(modell.anfragen) == anzahl + 1


def test_zusammenfassung_prueft_jeden_beleg(akten, con, tmp_path):
    _, ids = _akte(akten, con, tmp_path)
    ergebnis = Analyse(akten, Attrappe(modell_antwort)).zusammenfassung_dokument(ids["03"])
    assert ergebnis["zaehlung"] == {"belegt": 2, "ohne_beleg": 1}
    erste, zweite, dritte = ergebnis["aussagen"]
    assert erste["fundstellen"][0]["abschnitt"] != 7  # Absatz 7 gibt es nicht, das Zitat steht in Absatz 2
    assert zweite["fundstellen"][0]["ausschnitt"]["wert"] == "Wir lehnen eine Nachbesserung daher ab"
    assert dritte["status"] == "ohne_beleg" and dritte["fundstellen"] == []


def test_akte_zusammenfassung_verweist_auf_gepruefte_aussagen(akten, con, tmp_path):
    akte_id, ids = _akte(akten, con, tmp_path)
    ergebnis = Analyse(akten, Attrappe(modell_antwort)).zusammenfassung_akte(akte_id)
    streit, ohne = ergebnis["aussagen"]
    assert streit["status"] == "belegt" and len(streit["fundstellen"]) == 2
    assert ohne["status"] == "ohne_beleg"
    assert [d["dokument_id"] for d in ergebnis["dokumente"]] == [ids["01"], ids["03"], ids["06"]]

    gespeichert = speicher.ergebnisse(akten, akte_id, Attrappe.modell)
    assert gespeichert["zusammenfassung_akte"]["aussagen"][0]["text"] == "Streit um die Nachbesserung."
    assert set(gespeichert["dokumente"]) == {str(i) for i in ids.values()}

    # Mit der Akte verschwinden auch die gespeicherten Ergebnisse.
    akte.akte_loeschen(akten, akte_id, tmp_path / "ablage")
    assert akten.execute("SELECT COUNT(*) FROM ki_ergebnis").fetchone()[0] == 0


def test_langes_dokument_wird_in_teilen_gelesen_und_verdichtet(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Lang")
    pfad = tmp_path / "lang.md"
    pfad.write_text("\n\n".join(f"({i}) Absatz {i}: " + "Die Klägerin trägt ausführlich vor. " * 12
                                for i in range(1, 41)), encoding="utf-8")
    d = akte.importiere(akten, con, a["id"], pfad, tmp_path / "ablage", ocr=False)["dokument_id"]

    def antwort(prompt, schema):
        if "quellen" in json.dumps(schema):
            return {"aussagen": [{"text": "Gesamt.", "art": "vortrag", "quellen": ["A1", "A3"]}]}
        erster = int(re.search(r"^\[(\d+)\]", prompt, re.M).group(1))
        return {"aussagen": [{"text": f"Ab Absatz {erster}.", "art": "vortrag",
                              "belege": [{"absatz": erster, "zitat": f"Absatz {erster}: Die Klägerin trägt ausführlich vor."}]}]}

    modell = Attrappe(antwort)
    ergebnis = Analyse(akten, modell, kontext=4096).zusammenfassung_dokument(d)
    assert ergebnis["teile"] == len(modell.anfragen) - 1 > 1
    assert all(len(p) < 4500 for p in modell.anfragen[:-1])
    (gesamt,) = ergebnis["aussagen"]
    assert gesamt["status"] == "belegt" and [f["rn"] for f in gesamt["fundstellen"]][0] == 1


# --- Hintergrundaufträge und RPC ------------------------------------------------------------------


def _warte(abfrage, bis=5.0):
    ende = time.monotonic() + bis
    while time.monotonic() < ende:
        stand = abfrage()
        if stand["status"] != "laeuft":
            return stand
        time.sleep(0.02)
    raise AssertionError("Auftrag läuft zu lange")


def test_auftraege_laufen_einzeln_und_lassen_sich_abbrechen():
    auftraege = Auftraege()
    weiter = threading.Event()

    def arbeit(auftrag):
        auftrag.melde("Schritt 1", 0, 2)
        weiter.wait(5)
        auftrag.pruefe()
        return {"ok": True}

    a = auftraege.starte("test", arbeit)
    assert auftraege.status(a["auftrag_id"])["status"] == "laeuft"
    with pytest.raises(RuntimeError, match="läuft bereits"):
        auftraege.starte("test", arbeit)
    auftraege.abbrechen(a["auftrag_id"])
    weiter.set()
    assert _warte(lambda: auftraege.status(a["auftrag_id"]))["status"] == "abgebrochen"

    def kaputt(auftrag):
        raise anbieter.KiFehler("Ollama ist nicht erreichbar")

    b = auftraege.starte("test", kaputt)
    stand = _warte(lambda: auftraege.status(b["auftrag_id"]))
    assert stand["status"] == "fehler" and "nicht erreichbar" in stand["fehler"]


def test_rpc_startet_analyse_im_hintergrund(con, tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    kern.ki_fabrik = lambda e: Attrappe(modell_antwort)
    akte_id, _ = _akte(kern.akten, con, tmp_path)

    def aufruf(methode, **params):
        antwort = kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))
        assert "error" not in antwort, antwort
        return antwort["result"]

    fehler = kern.bearbeite(json.dumps({"id": 2, "method": "ki.starten", "params": {"aufgabe": "widersprueche",
                                                                                     "akte_id": akte_id}}))
    assert "Kein Sprachmodell gewählt" in fehler["error"]["message"]
    fehler = kern.bearbeite(json.dumps({"id": 3, "method": "ki.einstellungen_setzen", "params": {
        "anbieter": "ollama", "endpunkt": "http://192.168.0.9:11434", "modell": "x"}}))
    assert "Nur lokal" in fehler["error"]["message"]

    # Ein Port, an dem nichts läuft: Status meldet „nicht erreichbar“, speichert aber die Wahl.
    stand = aufruf("ki.einstellungen_setzen", anbieter="ollama", endpunkt="http://127.0.0.1:9", modell=Attrappe.modell)
    assert stand["erreichbar"] is False and "nicht erreichbar" in stand["hinweis"]

    auftrag = aufruf("ki.starten", aufgabe="widersprueche", akte_id=akte_id)
    stand = _warte(lambda: aufruf("ki.auftrag", auftrag_id=auftrag["auftrag_id"]))
    assert stand["status"] == "fertig", stand
    assert len(stand["ergebnis"]["widersprueche"]) == 2
    assert aufruf("ki.ergebnisse", akte_id=akte_id)["widersprueche"]["angaben"] == 4


# --- Ollama und LM Studio über HTTP (nachgebauter Server auf 127.0.0.1) ----------------------------


class _Server(BaseHTTPRequestHandler):
    anfragen: list = []

    def log_message(self, *args):
        pass

    def _antworte(self, code, daten):
        roh = json.dumps(daten).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    def do_GET(self):
        if self.path == "/api/tags":
            self._antworte(200, {"models": [{"name": "qwen3:14b", "size": 9_300_000_000,
                                             "details": {"parameter_size": "14.8B", "quantization_level": "Q4_K_M"}}]})
        elif self.path == "/v1/models":
            self._antworte(200, {"data": [{"id": "qwen3-14b"}]})
        else:
            self._antworte(404, {"error": "nicht gefunden"})

    def do_POST(self):
        daten = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Server.anfragen.append((self.path, daten))
        if self.path == "/api/show":
            self._antworte(200, {"capabilities": ["completion", "thinking"]})
        elif self.path == "/api/chat":
            if daten["model"] != "qwen3:14b":
                self._antworte(404, {"error": f"model '{daten['model']}' not found"})
            else:
                self._antworte(200, {"message": {"role": "assistant", "content": '{"aussagen": []}'}})
        elif self.path == "/v1/chat/completions":
            self._antworte(200, {"choices": [{"message": {"content": '{"aussagen": [{"text": "x"}]}'}}]})


@pytest.fixture
def server(monkeypatch):
    # Ein gesetzter Proxy darf Anfragen an das lokale Modell nicht umleiten.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    _Server.anfragen = []
    httpd = HTTPServer(("127.0.0.1", 0), _Server)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_ollama_ueber_http(server):
    e = anbieter.KiEinstellungen("ollama", server, "qwen3:14b", 8192)
    stand = anbieter.status(e)
    assert stand["bereit"] is True and stand["modelle"][0]["parameter"] == "14.8B"

    ollama = anbieter.erzeuge(e)
    assert ollama.chat("System", "Frage", {"type": "object"}) == {"aussagen": []}
    pfad, gesendet = _Server.anfragen[-1]
    assert pfad == "/api/chat"
    assert gesendet["format"] == {"type": "object"} and gesendet["stream"] is False
    assert gesendet["think"] is False  # Denkendes Modell: Denkphase aus
    assert gesendet["options"] == {"temperature": 0, "seed": 42, "num_ctx": 8192}

    with pytest.raises(anbieter.KiFehler, match="not found"):
        anbieter.erzeuge(anbieter.KiEinstellungen("ollama", server, "gibtsnicht")).chat("s", "n", {})
    assert anbieter.status(anbieter.KiEinstellungen("ollama", server, "gibtsnicht"))["bereit"] is False


def test_lm_studio_ueber_http(server):
    e = anbieter.KiEinstellungen("openai", server, "qwen3-14b")
    assert anbieter.status(e)["bereit"] is True
    assert anbieter.erzeuge(e).chat("s", "n", {"type": "object"}) == {"aussagen": [{"text": "x"}]}
    pfad, gesendet = _Server.anfragen[-1]
    assert pfad == "/v1/chat/completions"
    assert gesendet["response_format"]["json_schema"]["schema"] == {"type": "object"}


def test_nicht_erreichbar():
    with pytest.raises(anbieter.KiFehler, match="nicht erreichbar"):
        anbieter.erzeuge(anbieter.KiEinstellungen("ollama", "http://127.0.0.1:9", "m")).modelle()


def test_viele_angaben_werden_blockweise_verglichen(akten, con, tmp_path):
    akte_id, _ = _akte(akten, con, tmp_path)

    def antwort(prompt, schema):
        if "widersprueche" in schema["properties"]:
            return {"widersprueche": []}
        # Viele lange Angaben je Dokument, alle mit gültigem Zitat.
        nr = int(re.search(r"^\[(\d+)\] (.*)$", prompt, re.M).group(1))
        zitat = re.search(r"^\[\d+\] (.*)$", prompt, re.M).group(1)
        return {"angaben": [{"text": f"Angabe {i} " + "x" * 300, "haltung": "behauptet", "absatz": nr, "zitat": zitat}
                            for i in range(12)]}

    modell = Attrappe(antwort)
    ergebnis = Analyse(akten, modell, kontext=4096).widersprueche(akte_id)
    vergleiche = [p for p in modell.anfragen if p.startswith("Unten stehen")]
    assert ergebnis["angaben"] == 36 and len(vergleiche) > 1
    # Jede Angabe trifft in mindestens einer Anfrage auf jede andere.
    for a, b in [("[A1]", "[A36]"), ("[A2]", "[A20]")]:
        assert any(a in p and b in p for p in vergleiche)


def test_kommandozeile_waehlt_lm_studio(server, tmp_path, capsys):
    from juracore.__main__ import main

    port = server.rsplit(":", 1)[1]
    assert main(["--db", str(tmp_path / "w.sqlite"), "ki-status", "--anbieter", "lmstudio",
                 "--endpunkt", f"http://127.0.0.1:{port}"]) == 0
    stand = json.loads(capsys.readouterr().out)
    assert stand["anbieter"] == "openai" and stand["modell"] == "qwen3-14b" and stand["bereit"] is True
