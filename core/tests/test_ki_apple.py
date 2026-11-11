"""Apple Intelligence (On-Device) über das Hilfsprogramm, hier mit einem nachgebauten Hilfsprogramm geprüft."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from juracore.ki import anbieter, apple
from juracore.ki.anbieter import KiEinstellungen, KiFehler

# Das nachgebaute Hilfsprogramm legt die Anfrage in ANFRAGE ab und antwortet, was in ANTWORTEN steht (eine Antwort
# je Aufruf, der Reihe nach).
FAKE = """#!{python}
import json, os, sys
anfrage = json.loads(sys.stdin.read())
ablage = os.environ["APPLE_TEST_ABLAGE"]
with open(os.path.join(ablage, "anfragen.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(anfrage) + "\\n")
antworten = json.load(open(os.path.join(ablage, "antworten.json"), encoding="utf-8"))
nr = sum(1 for _ in open(os.path.join(ablage, "anfragen.jsonl"), encoding="utf-8")) - 1
print(json.dumps(antworten[min(nr, len(antworten) - 1)]))
"""


@pytest.fixture
def helfer(tmp_path, monkeypatch):
    pfad = tmp_path / "advordo-apple-ki"
    pfad.write_text(FAKE.format(python=sys.executable), encoding="utf-8")
    pfad.chmod(0o755)
    monkeypatch.setenv("APPLE_TEST_ABLAGE", str(tmp_path))
    monkeypatch.setenv("ADVORDO_APPLE_KI", str(pfad))

    def antworten(*liste: dict) -> None:
        (tmp_path / "antworten.json").write_text(json.dumps(list(liste)), encoding="utf-8")

    def anfragen() -> list[dict]:
        datei = tmp_path / "anfragen.jsonl"
        return [json.loads(z) for z in datei.read_text(encoding="utf-8").splitlines()] if datei.exists() else []

    return antworten, anfragen


pytestmark = pytest.mark.skipif(os.name == "nt", reason="Das nachgebaute Hilfsprogramm ist ein Skript mit Shebang")

SCHEMA = {"type": "object", "properties": {"absatz": {"type": "integer"}, "zitat": {"type": "string", "maxLength": 9}},
          "required": ["absatz", "zitat"]}


def test_einstellungen_ohne_adresse():
    e = KiEinstellungen(anbieter=anbieter.APPLE, endpunkt="http://example.com", modell="", kontext=4096).pruefen()
    assert e.endpunkt == "" and e.modell == apple.MODELL
    assert anbieter.lokal_ort(e) == anbieter.GERAET
    assert isinstance(anbieter.erzeuge(e), apple.AppleIntelligence)


def test_antwortlaenge_an_kleinen_kontext_angepasst():
    assert apple.AppleIntelligence(4096).antwort_token == 1024
    assert apple.AppleIntelligence(2048).antwort_token == 512
    assert anbieter.antwort_token(apple.AppleIntelligence(4096)) == 1024
    assert anbieter.antwort_token(anbieter.Ollama("http://127.0.0.1:11434", "m")) == anbieter.ANTWORT_TOKEN


def test_nur_unter_macos_angeboten(monkeypatch):
    monkeypatch.setattr(apple, "moeglich", lambda system=sys.platform: False)
    s = anbieter.status(KiEinstellungen())
    assert anbieter.APPLE not in {a["id"] for a in s["anbieter_liste"]}
    s = anbieter.status(KiEinstellungen(anbieter=anbieter.APPLE, endpunkt=""))
    assert s["hinweis"] == "Apple Intelligence gibt es nur unter macOS." and not s["bereit"]


def test_status_bereit(helfer, monkeypatch):
    antworten, anfragen = helfer
    monkeypatch.setattr(apple, "moeglich", lambda system=sys.platform: True)
    antworten({"ok": True, "verfuegbar": True, "grund": None, "deutsch": True, "system": "macOS 26.1"})
    s = anbieter.status(KiEinstellungen(anbieter=anbieter.APPLE, endpunkt="", kontext=4096))
    assert s["bereit"] and s["erreichbar"] and s["modelle"][0]["name"] == apple.MODELL
    assert anbieter.APPLE in {a["id"] for a in s["anbieter_liste"]}
    assert anfragen() == [{"aktion": "status"}]


@pytest.mark.parametrize("grund, text", [("nicht_eingeschaltet", "ausgeschaltet"), ("geraet", "nicht"),
                                         ("nicht_bereit", "noch nicht bereit")])
def test_status_nicht_verfuegbar(helfer, monkeypatch, grund, text):
    antworten, _ = helfer
    monkeypatch.setattr(apple, "moeglich", lambda system=sys.platform: True)
    antworten({"ok": True, "verfuegbar": False, "grund": grund, "deutsch": True})
    s = anbieter.status(KiEinstellungen(anbieter=anbieter.APPLE, endpunkt=""))
    assert not s["bereit"] and text in s["hinweis"]


def test_ohne_deutsch_nicht_bereit(helfer):
    antworten, _ = helfer
    antworten({"ok": True, "verfuegbar": True, "grund": None, "deutsch": False})
    with pytest.raises(KiFehler, match="kein Deutsch"):
        apple.AppleIntelligence().modelle()


def test_hilfsprogramm_fehlt(monkeypatch, tmp_path):
    monkeypatch.setenv("ADVORDO_APPLE_KI", str(tmp_path / "gibt-es-nicht"))
    monkeypatch.setattr(apple, "programm", lambda: None)
    with pytest.raises(KiFehler, match="bauen.sh"):
        apple.AppleIntelligence().modelle()


def test_chat_mit_schema(helfer):
    antworten, anfragen = helfer
    antworten({"ok": True, "text": '{"absatz": 3, "zitat": "Der Kaufpreis"}'})
    ergebnis = apple.AppleIntelligence(4096).chat("System", "Frage", SCHEMA)
    assert ergebnis == {"absatz": 3, "zitat": "Der Kaufpreis"}
    gesendet = anfragen()[0]
    assert gesendet["aktion"] == "chat" and gesendet["system"] == "System" and gesendet["nutzer"] == "Frage"
    assert gesendet["antwort_token"] == 1024
    assert gesendet["schema"]["x-reihenfolge"] == ["absatz", "zitat"]
    assert "maxLength" not in gesendet["schema"]["properties"]["zitat"]


def test_schema_nicht_abbildbar_dann_als_anweisung(helfer):
    antworten, anfragen = helfer
    antworten({"ok": False, "fehler": "schema", "meldung": "Typ x"}, {"ok": True, "text": '{"absatz": 1, "zitat": "a"}'})
    assert apple.AppleIntelligence().chat("System", "Frage", SCHEMA) == {"absatz": 1, "zitat": "a"}
    zweite = anfragen()[1]
    assert zweite["schema"] is None and '"absatz"' in zweite["system"]


def test_kontext_ueberschritten_laesst_analyse_teilen(helfer):
    """Die Analyse teilt ein Stück, wenn die Meldung „JSON“ und „abgeschnitten“ enthält."""
    antworten, _ = helfer
    antworten({"ok": False, "fehler": "kontext", "meldung": "exceeded"})
    with pytest.raises(KiFehler) as fehler:
        apple.AppleIntelligence(4096).chat("System", "Frage", SCHEMA)
    assert "JSON" in str(fehler.value) and "abgeschnitten" in str(fehler.value)


@pytest.mark.parametrize("art, text", [("schutz", "Inhaltsfilter"), ("sprache", "Sprache"),
                                       ("json", "kein gültiges JSON"), ("sonstiges", "meldet einen Fehler")])
def test_fehler_werden_verstaendlich(helfer, art, text):
    antworten, _ = helfer
    antworten({"ok": False, "fehler": art, "meldung": "x"})
    with pytest.raises(KiFehler, match=text):
        apple.AppleIntelligence().chat("System", "Frage", SCHEMA)


def test_kaputte_ausgabe(tmp_path):
    pfad = tmp_path / "kaputt"
    pfad.write_text(f"#!{sys.executable}\nimport sys\nsys.stderr.write('dyld: Library not loaded')\nsys.exit(3)\n",
                    encoding="utf-8")
    pfad.chmod(0o755)
    with pytest.raises(KiFehler, match="Code 3.*dyld"):
        apple.AppleIntelligence(pfad=pfad).modelle()


def test_ki_modus_zeigt_eigenen_rechner(tmp_path):
    from juracore.rpc import Kern

    k = Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    anbieter.speichere_einstellungen(k.ki_datei, KiEinstellungen(anbieter=anbieter.APPLE, endpunkt="", kontext=4096))
    modus = k.ki_modus()
    assert modus["ort"] == anbieter.GERAET and modus["modell"] == apple.MODELL


def test_hilfsprogramm_im_projektordner():
    erwartet = Path(apple.__file__).resolve().parents[3] / "macos" / "apple-ki" / "main.swift"
    assert erwartet.is_file()
