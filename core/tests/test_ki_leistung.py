"""KI-Leistungstest der Diagnose: Auswertung der Prüffragen und Messwerte, mit einer Attrappe statt Modell."""

import datetime as dt
import json
import re
import time

import pytest

from juracore.ki import leistung
from juracore.ki.anbieter import KiFehler, verbrauch
from juracore.rpc import Kern


class Auftrag:
    def __init__(self):
        self.texte = []

    def melde(self, text, schritt=None, von=None):
        self.texte.append(text)

    def pruefe(self):
        pass


def richtige_antwort(nutzer: str, schema: dict) -> dict:
    """Antwortet so, wie die Prüffrage es erwartet."""
    for f in leistung.FRAGEN:
        if f.frage == nutzer:
            break
    else:
        if "Sachverhalt" in nutzer:
            return {"saetze": ["Eins.", "Zwei.", "Drei.", "Vier.", "Fünf."]}
        return {"ok": True}
    if "datum" in schema["properties"]:
        soll = re.search(r"Fristende (\d\d)\.(\d\d)\.(\d{4})", f.erwartet).groups()
        return {"datum": f"{soll[2]}-{soll[1]}-{soll[0]}", "begruendung": "…"}
    if "gericht" in schema["properties"]:
        return {"gericht": f.erwartet, "norm": "…"}
    if "thema" in schema["properties"]:
        return {"existiert": True, "thema": leistung.THEMEN_626[0]}
    if "existiert" in schema["properties"]:
        return {"existiert": False, "inhalt": ""}
    if "im_text" in schema["properties"]:
        return {"im_text": False, "zitat": ""}
    return {"zitat": "Das Gerät wurde unserer Mandantin am 12. Mai 2026 in Musterstadt übergeben."}


class Modell:
    modell = "attrappe:1b"

    def __init__(self, antwort, token=None, denken=0):
        self.antwort, self.token, self.denken = antwort, token, denken
        self.anfragen = []

    def chat(self, system, nutzer, schema):
        self.anfragen.append(nutzer)
        self.verbrauch = verbrauch(100, self.token) if self.token else None
        self.denkphase = self.denken
        return self.antwort(nutzer, schema)


def test_alle_richtig():
    m = Modell(richtige_antwort, token=200)
    e = leistung.leistungstest(m, Auftrag(), "LM Studio", "Eigener Rechner")
    assert e["gesamt"]["richtig"] == e["gesamt"]["von"] == len(leistung.FRAGEN)
    assert e["gesamt"]["stand"] == "ok"
    titel = {w["titel"]: w for w in e["messwerte"]}
    assert "Token pro Sekunde" in titel and titel["Denkphase"]["wert"] == "keine"
    assert {b["bereich"] for b in e["bereiche"]} == {"Fristen", "Zuständigkeit", "Erfundene Normen", "Zitattreue"}
    # Nur die festen Testtexte gehen ans Modell.
    assert len(m.anfragen) == 3 + len(leistung.FRAGEN)


def test_falsche_und_kaputte_antworten():
    def antwort(nutzer, schema):
        if "Berufungsfrist" in nutzer:
            return {"datum": "12.09.2026", "begruendung": "ein Monat"}  # Wochenende übersehen
        if "§ 312z" in nutzer:
            return {"existiert": True, "inhalt": "Erfundenes"}
        if "Kaufpreis?" in nutzer:
            return {"im_text": True, "zitat": "Kaufpreis 12.000 Euro"}
        if "Tag der Übergabe" in nutzer:
            return {"zitat": "Die Übergabe erfolgte am 12. Mai 2026."}  # nicht wörtlich
        if "Räumung" in nutzer:
            raise KiFehler("Die Antwort des Modells ist kein JSON.")
        return richtige_antwort(nutzer, schema)

    e = leistung.leistungstest(Modell(antwort, denken=4000), Auftrag(), "Ollama", "Eigener Rechner")
    falsch = {f["id"]: f for f in e["fragen"] if not f["richtig"]}
    assert set(falsch) == {"berufung_wochenende", "berufung_monatsende", "bgb_312z", "nicht_im_text", "zitat",
                           "raeumung"}
    assert falsch["berufung_wochenende"]["antwort"] == "12.09.2026"
    assert "nicht wörtlich" in falsch["zitat"]["antwort"]
    assert "kein JSON" in falsch["raeumung"]["antwort"]
    titel = {w["titel"]: w for w in e["messwerte"]}
    assert titel["Denkphase"]["stand"] == "warnung"
    assert titel["Antworten als gültiges JSON"]["wert"] == "1 fehlerhaft"
    assert "Zeichen pro Sekunde" in titel  # ohne Tokenzahl
    assert e["gesamt"]["stand"] == "warnung"


def test_verbindungsfehler_bricht_ab():
    def antwort(nutzer, schema):
        raise KiFehler("LM Studio ist unter http://127.0.0.1:1234 nicht erreichbar.")

    with pytest.raises(KiFehler):
        leistung.leistungstest(Modell(antwort), Auftrag(), "LM Studio", "Eigener Rechner")


def test_erwartete_fristen_stimmen_mit_kalender():
    # Ausgangsdaten nennen den richtigen Wochentag, und kein erwartetes Fristende fällt aufs Wochenende.
    tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    for f in leistung.FRAGEN:
        if f.bereich != "Fristen":
            continue
        for tag, datum in re.findall(r"(\w+), (\d\d\.\d\d\.\d{4})", f.frage):
            assert tage[dt.datetime.strptime(datum, "%d.%m.%Y").weekday()] == tag, f.id
        ende = dt.date.fromisoformat(leistung.lies_datum(f.erwartet))
        assert ende.weekday() < 5, f.id


def test_lies_datum():
    assert leistung.lies_datum("2026-9-14") == "2026-09-14"
    assert leistung.lies_datum("14. 09. 2026") == "2026-09-14"
    assert leistung.lies_datum("bis 14.9.2026") == "2026-09-14"
    assert leistung.lies_datum("unbekannt") is None


def test_verbrauch():
    assert verbrauch(10, 20, 2_000_000_000) == {"eingabe": 10, "ausgabe": 20, "erzeugung_s": 2.0, "denken": None}
    assert verbrauch(10, None) is None


def test_rpc_startet_auftrag(tmp_path):
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    kern.methoden["ki.einstellungen_setzen"](anbieter="openai", endpunkt="http://127.0.0.1:1234",
                                         modell="attrappe:1b")
    m = Modell(richtige_antwort, token=50)
    kern.ki_fabrik = lambda e, schluessel=None: m
    a = kern.methoden["ki.leistungstest"]()
    for _ in range(200):
        a = kern.methoden["ki.auftrag"](auftrag_id=a["auftrag_id"])
        if a["status"] != "laeuft":
            break
        time.sleep(0.02)
    assert a["status"] == "fertig", a
    assert a["titel"] == "KI-Leistungstest (Diagnose)"
    assert a["ergebnis"]["anbieter"].startswith("LM Studio") and a["ergebnis"]["ort"] == "Eigener Rechner"


def test_widerspruch_zwischen_feld_und_text():
    f = next(f for f in leistung.FRAGEN if f.id == "bgb_823_4")
    richtig, anzeige = f.pruefe({"existiert": True, "inhalt": "Der § 823 Abs. 4 BGB ist nicht vorhanden."})
    assert not richtig and anzeige.startswith("widersprüchlich")


def test_traceback_behaelt_ursache():
    from juracore.ki.anbieter import _fehlertext
    roh = json.dumps({"error": "Error: Traceback (most recent call last):\n" + "  File x.py, line 1\n" * 60
                      + "ValueError: Modelltyp wird nicht unterstützt"})
    text = _fehlertext(roh)
    assert len(text) <= 505 and text.startswith("Error: Traceback") and text.endswith("nicht unterstützt")


def test_lmstudio_ohne_schema_wenn_grammatik_scheitert():
    from juracore.ki.anbieter import OpenAIKompatibel
    m = OpenAIKompatibel("http://127.0.0.1:1234", "luciole-8b")
    gesendet = []

    def anfrage(pfad, daten=None, timeout=600):
        gesendet.append(daten)
        if "response_format" in daten:
            raise KiFehler("LM Studio meldet Fehler 400: Error in iterating prediction stream … <grammar>…</grammar>")
        return {"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]}

    m.http.anfrage = anfrage
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    assert m.chat("System", "Frage", schema) == {"ok": True}
    assert "JSON-Schema" in gesendet[1]["messages"][0]["content"]
    # Danach gleich ohne Schema-Vorgabe.
    assert m.chat("System", "Frage", schema) == {"ok": True} and len(gesendet) == 3


def test_lmstudio_anderer_fehler_bleibt_fehler():
    from juracore.ki.anbieter import OpenAIKompatibel
    m = OpenAIKompatibel("http://127.0.0.1:1234", "x")

    def anfrage(pfad, daten=None, timeout=600):
        raise KiFehler("LM Studio meldet Fehler 400: model not loaded")

    m.http.anfrage = anfrage
    with pytest.raises(KiFehler, match="not loaded"):
        m.chat("S", "N", {"type": "object"})


def test_626_zeigt_existiert_mit():
    f = next(f for f in leistung.FRAGEN if f.id == "bgb_626")
    assert f.pruefe({"existiert": False, "thema": leistung.THEMEN_626[0]}) == (
        False, f"existiert nicht, Thema: {leistung.THEMEN_626[0]}")
    assert f.pruefe({"existiert": True, "thema": leistung.THEMEN_626[0]})[0]


def test_mit_gesetzen_aus_der_wissensbasis(con):
    m = Modell(richtige_antwort)
    e = leistung.leistungstest(m, Auftrag(), "LM Studio", "Eigener Rechner", wb=con)
    assert e["mit_gesetzen"] is True
    prompts = {f.id: p for f, p in zip(leistung.FRAGEN, m.anfragen[3:], strict=True)}
    assert "§ 195 BGB" in prompts["verjaehrung"] and "§ 199 BGB" in prompts["verjaehrung"]
    assert "Fassung:" in prompts["verjaehrung"] and prompts["verjaehrung"].endswith(
        next(f.frage for f in leistung.FRAGEN if f.id == "verjaehrung"))
    assert "§ 312z BGB: In der Gesetzessammlung der App (BGB) nicht vorhanden." in prompts["bgb_312z"]
    assert "MandAktG: Ein Gesetz mit dieser Abkürzung ist in der Gesetzessammlung der App nicht enthalten." in \
        prompts["mandaktg"]
    # Nicht geladene echte Gesetze gehen nicht als „nicht enthalten“ hinaus, sondern werden gemeldet.
    assert "KSchG" not in prompts["kschg"].split("Frage:")[0]
    fragen = {f["id"]: f for f in e["fragen"]}
    assert fragen["verjaehrung"]["gesetze"] == ["§ 195 BGB", "§ 199 BGB"]
    assert fragen["zitat"]["gesetze"] == []
    hinweis = next(w for w in e["messwerte"] if w["titel"] == "Gesetze in der Wissensbasis")
    assert "StPO" in hinweis["wert"] and "KSchG" in hinweis["wert"] and "§ 626 BGB" in hinweis["wert"]


def test_ohne_gesetze_gleiche_fragen():
    m = Modell(richtige_antwort)
    e = leistung.leistungstest(m, Auftrag(), "LM Studio", "Eigener Rechner")
    assert e["mit_gesetzen"] is False
    assert m.anfragen[3:] == [f.frage for f in leistung.FRAGEN]


# Bezugstag und Dauer, wie sie ein Modell für den Fristenrechner liefern soll.
EINGABEN = {
    "berufung_wochenende": ("12.08.2026", "1 Monat"),
    "berufung_monatsende": ("31.03.2026", "1 Monat"),
    "berufung_strafrecht": ("03.11.2026", "eine Woche"),
    "kschg": ("02.10.2026", "drei Wochen"),
    "einspruch_vu": ("20.11.2026", "2 Wochen"),
    "verjaehrung": ("31.12.2023", "3 Jahre"),
}


def test_mit_fristenrechner():
    systeme = []

    def antwort(nutzer, schema):
        if "bezugstag" in schema["properties"]:
            f = next(f for f in leistung.FRAGEN if f.frage.replace(leistung.FRIST_SCHLUSS, leistung.RECHNER_SCHLUSS)
                     in nutzer)
            tag, dauer = EINGABEN[f.id]
            return {"bezugstag": tag, "dauer": dauer, "begruendung": "…"}
        return richtige_antwort(nutzer, schema)

    class MitSystem(Modell):
        def chat(self, system, nutzer, schema):
            systeme.append(system)
            return super().chat(system, nutzer, schema)

    m = MitSystem(antwort)
    e = leistung.leistungstest(m, Auftrag(), "LM Studio", "Eigener Rechner", rechner=True)
    assert e["mit_fristenrechner"] is True
    assert e["gesamt"]["richtig"] == len(leistung.FRAGEN)
    fragen = {f["id"]: f for f in e["fragen"]}
    assert fragen["berufung_wochenende"]["antwort"] == \
        "14.09.2026 (Fristenrechner aus: Bezugstag 12.08.2026, Dauer 1 Monat)"
    assert "Nenne den letzten Tag" not in m.anfragen[3]
    assert leistung.SYSTEM_RECHNER in systeme[3] and leistung.SYSTEM_RECHNER not in systeme[-1]


def test_fristenrechner_falscher_bezugstag_und_unbrauchbare_dauer():
    f = next(f for f in leistung.FRAGEN if f.id == "verjaehrung")
    richtig, anzeige = leistung.mit_fristenrechner(f, {"bezugstag": "15.06.2023", "dauer": "3 Jahre"})
    assert not richtig and anzeige.startswith("15.06.2026 (Fristenrechner aus: Bezugstag 15.06.2023")
    richtig, anzeige = leistung.mit_fristenrechner(f, {"bezugstag": "15.06.2023", "dauer": "bis Jahresende"})
    assert not richtig and anzeige.startswith("keine verwertbaren Angaben")
