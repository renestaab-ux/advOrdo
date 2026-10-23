"""Zusatzwissen im KI-Chat: Rechner der Toolbox und Gesetze der Wissensbasis, ohne echtes Modell.

Die Akte ist frei erfunden.
"""

import json
import re
from datetime import date

import pytest

from juracore import rpc
from juracore.dokumente import akte
from juracore.ki import chat, wissen

from .test_ki import Attrappe, _warte

ANSPRUCH = (
    "Anspruchsbegründung\n\n"
    "Die Beklagte schuldet die Rückzahlung der Abschlagszahlung in Höhe von 12.500,00 € nebst Zinsen in Höhe von "
    "fünf Prozentpunkten über dem jeweiligen Basiszinssatz seit dem 15.04.2026.\n\n"
    "Die Beklagte befindet sich seit dem 15.04.2026 in Verzug. Der Anspruch folgt aus § 280 Abs. 1 BGB.\n\n"
    "Das Versäumnisurteil wurde der Beklagten am 02.03.2026 zugestellt; die Einspruchsfrist beträgt zwei Wochen."
)


@pytest.fixture
def akten(tmp_path):
    verbindung = akte.oeffne(tmp_path / "akten.sqlite")
    yield verbindung
    verbindung.close()


def _akte(akten, con, tmp_path) -> int:
    a = akte.akte_anlegen(akten, "Weber ./. Bau GmbH")
    pfad = tmp_path / "04_Anspruchsbegruendung.md"
    pfad.write_text(ANSPRUCH, encoding="utf-8")
    akte.importiere(akten, con, a["id"], pfad, tmp_path / "ablage", ocr=False)
    return a["id"]


def _zeile(prompt: str, stueck: str) -> tuple[int, int]:
    for d, n, text in re.findall(r"^\[(\d+)\.(\d+)\] (.*)$", prompt, re.M):
        if stueck in text:
            return int(d), int(n)
    raise AssertionError(f"{stueck!r} nicht im Prompt")


def zinsantwort(prompt: str, schema: dict) -> dict:
    assert "berechnungen" in schema["properties"]
    d, n = _zeile(prompt, "12.500,00")
    return {
        "aussagen": [
            {"text": "Die Klägerin verlangt Zinsen seit dem 15.04.2026.", "art": "tatsache",
             "belege": [{"dokument": d, "absatz": n, "zitat": "Basiszinssatz seit dem 15.04.2026"}]},
            {"text": "Die Dokumente enthalten keine Angaben zum aktuellen Basiszinssatz.", "art": "hinweis",
             "belege": []},
        ],
        "berechnungen": [{"rechner": "zinsen", "angaben": [
            {"feld": "hauptbetrag", "wert": "12.500,00 €", "dokument": d, "absatz": n,
             "zitat": "Abschlagszahlung in Höhe von 12.500,00 €"},
            {"feld": "zinsbeginn", "wert": "15.04.2026", "dokument": d, "absatz": n,
             "zitat": "Basiszinssatz seit dem 15.04.2026"},
            {"feld": "zinssatz", "wert": "5 Prozentpunkte über dem Basiszinssatz", "dokument": d, "absatz": n,
             "zitat": "fünf Prozentpunkten über dem jeweiligen Basiszinssatz"},
        ]}],
    }


def test_zinsen_rechnet_die_app_mit_belegten_angaben(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    modell = Attrappe(zinsantwort)
    antwort = chat.frage(akten, modell, 32768, akte_id, "Kannst du mir die Zinsen zum heutigen Tag ausrechnen?",
                         rechner=True, heute=date(2026, 10, 23))

    assert "Rechne Zinsen oder Fristen nicht selbst" in modell.anfragen[0]
    erste = antwort["aussagen"][0]
    assert erste["art"] == "berechnung" and erste["status"] == "belegt"
    b = erste["berechnung"]
    assert [e["status"] for e in b["eingaben"]] == ["belegt"] * 4
    assert b["eingaben"][3]["quelle"] == "heute"
    # 12.500 € × (1,27 % + 5) × 77/365 (15.04.–30.06.) + 12.500 € × (1,52 % + 5) × 115/365 (01.07.–23.10.)
    assert b["ergebnis"]["summe_zinsen"] == "422.12"
    assert "422,12 €" in erste["text"] and "12.922,12 €" in erste["text"]
    # Der Hinweis des Modells, der Basiszinssatz fehle, ist nach der Berechnung falsch und entfällt.
    assert not any("Basiszinssatz" in a["text"] for a in antwort["aussagen"] if a["art"] == "hinweis")
    assert antwort["wissen"] == {"rechner": True}


def test_erfundene_angaben_bleiben_ohne_beleg(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)

    def antwort(prompt, schema):
        d, n = _zeile(prompt, "12.500,00")
        return {"aussagen": [], "berechnungen": [{"rechner": "zinsen", "angaben": [
            # Der Betrag steht so nicht im Absatz.
            {"feld": "hauptbetrag", "wert": "15.000,00 €", "dokument": d, "absatz": n,
             "zitat": "Abschlagszahlung in Höhe von 12.500,00 €"},
            {"feld": "zinsbeginn", "wert": "15.04.2026", "dokument": d, "absatz": n, "zitat": "seit dem 15.04.2026"},
            # Das Zitat gibt es nicht.
            {"feld": "zinssatz", "wert": "9 Prozentpunkte über dem Basiszinssatz", "dokument": d, "absatz": n,
             "zitat": "neun Prozentpunkte über dem Basiszinssatz der EZB"},
        ]}]}

    erg = chat.frage(akten, Attrappe(antwort), 32768, akte_id, "Wie hoch sind die Zinsen bis 31.12.2026?",
                     rechner=True, heute=date(2026, 10, 23))
    b = erg["aussagen"][0]["berechnung"]
    assert erg["aussagen"][0]["status"] == "ohne_beleg" and b["belegt"] is False
    status = {e["feld"]: e["status"] for e in b["eingaben"]}
    assert status == {"hauptbetrag": "ohne_beleg", "zinsbeginn": "belegt", "zinssatz": "ohne_beleg",
                      "bis": "belegt"}
    assert b["ergebnis"] is not None  # gerechnet wird trotzdem, aber sichtbar ohne Beleg


def test_fehlende_angaben_werden_genannt(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    erg = chat.frage(akten, Attrappe(lambda p, s: {"aussagen": [], "berechnungen": [
        {"rechner": "zinsen", "angaben": [{"feld": "zinsbeginn", "wert": "15.04.2026", "dokument": 1, "absatz": 1,
                                           "zitat": "seit dem 15.04.2026"}]}]}),
        32768, akte_id, "Rechne die Zinsen aus.", rechner=True)
    b = erg["aussagen"][0]["berechnung"]
    assert b["ergebnis"] is None and b["fehlt"] == ["Hauptforderung", "Zinssatz"]
    assert "fehlt" in erg["aussagen"][0]["text"]


def test_frist_mit_dem_fristenrechner(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)

    def antwort(prompt, schema):
        d, n = _zeile(prompt, "Einspruchsfrist")
        return {"aussagen": [], "berechnungen": [{"rechner": "frist", "angaben": [
            {"feld": "bezugstag", "wert": "02.03.2026", "dokument": d, "absatz": n,
             "zitat": "der Beklagten am 02.03.2026 zugestellt"},
            {"feld": "dauer", "wert": "2 Wochen", "dokument": d, "absatz": n,
             "zitat": "die Einspruchsfrist beträgt zwei Wochen"},
        ]}]}

    erg = chat.frage(akten, Attrappe(antwort), 32768, akte_id, "Wann endet die Einspruchsfrist?", rechner=True)
    a = erg["aussagen"][0]
    assert a["status"] == "belegt"
    assert a["berechnung"]["ergebnis"]["ende"] == "2026-03-16"
    assert "Montag, 16.03.2026" in a["text"]


def test_ohne_rechenfrage_kein_rechner(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    schemas = []
    chat.frage(akten, Attrappe(lambda p, s: schemas.append(s) or {"aussagen": []}), 32768, akte_id,
               "Wer ist die Beklagte?", rechner=True)
    assert "berechnungen" not in schemas[0]["properties"]


def test_gesetze_gehen_mit_und_werden_am_wortlaut_geprueft(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)

    def antwort(prompt, schema):
        nr = int(re.search(r"^\[G(\d+)\] § 280 BGB", prompt, re.M)[1])
        return {"aussagen": [
            {"text": "Schadensersatz setzt eine Pflichtverletzung voraus.", "art": "einschaetzung", "belege": [],
             "normbelege": [{"norm": nr, "zitat": "Verletzt der Schuldner eine Pflicht aus dem Schuldverhältnis"}]},
            {"text": "Erfunden.", "art": "einschaetzung", "belege": [],
             "normbelege": [{"norm": nr, "zitat": "Der Schuldner haftet stets und ohne jede Ausnahme"}]},
        ]}

    modell = Attrappe(antwort)
    erg = chat.frage(akten, modell, 32768, akte_id, "Welche Voraussetzungen hat der Schadensersatz?", gesetze=con)
    prompt = modell.anfragen[0]
    assert "Gesetze aus der Wissensbasis:" in prompt and "[G1] § 280 BGB" in prompt  # in der Akte zitiert
    assert "Fassung:" in prompt
    a, b = erg["aussagen"]
    assert a["status"] == "belegt" and a["normbelege"][0]["norm"] == "§ 280 Abs. 1 BGB"
    assert a["normbelege"][0]["ausschnitt"]["wert"].startswith("Verletzt der Schuldner")
    assert b["status"] == "ohne_beleg" and "normbelege" not in b
    assert "§ 280 BGB" in erg["wissen"]["gesetze"]


def test_beim_zinsrechner_fehlende_normen_werden_genannt(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    erg = chat.frage(akten, Attrappe(zinsantwort), 32768, akte_id, "Rechne die Zinsen aus.", rechner=True,
                     gesetze=con, heute=date(2026, 10, 23))
    # § 288 und § 247 BGB fehlen im Testauszug des BGB.
    assert "§ 288 BGB" in erg["wissen"]["fehlend"] and erg["wissen"]["rechner"] is True


def test_normen_bleiben_im_budget(con, akten, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    normen, _ = wissen.waehle_normen(con, akten, akte_id, None, "Schadensersatz Verjährung Mangel", budget=1500)
    assert sum(len(a["text"]) for n in normen for a in n["absaetze"]) <= 1500


def test_rpc_reicht_die_schalter_durch(con, tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    gesehen = []

    def antwort(prompt, schema):
        gesehen.append((prompt, schema))
        return {"aussagen": []}

    kern.ki_fabrik = lambda e, schluessel=None: Attrappe(antwort)
    akte_id = _akte(kern.akten, con, tmp_path)

    def aufruf(methode, **params):
        a = kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))
        assert "error" not in a, a
        return a["result"]

    aufruf("ki.einstellungen_setzen", anbieter="ollama", endpunkt="http://127.0.0.1:9", modell=Attrappe.modell)
    auftrag = aufruf("ki.chat_fragen", akte_id=akte_id, frage="Rechne die Zinsen aus.", rechner=True,
                     gesetze=True, land="BW")
    stand = _warte(lambda: aufruf("ki.auftrag", auftrag_id=auftrag["auftrag_id"]))
    assert stand["status"] == "fertig", stand
    assert "berechnungen" in gesehen[0][1]["properties"]
    assert stand["ergebnis"]["wissen"]["rechner"] is True and "gesetze" in stand["ergebnis"]["wissen"]
