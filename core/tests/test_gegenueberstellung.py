"""Gegenüberstellung von Schriftsatz und zitierter Entscheidung, ohne echtes Modell. Alles frei erfunden."""

import json
import re

from juracore import rpc
from juracore.ki import chat, gegenueberstellung
from juracore.ki.analyse import Analyse

from .test_ki import Attrappe, _warte
from .test_wissen import _akte, _akte_mit_urteil, akten  # noqa: F401  (Fixture)


def _nr(prompt: str, marke: str, stueck: str) -> int:
    for n, text in re.findall(rf"^\[{marke}(\d+)[^\]]*\] (.*)$", prompt, re.M):
        if stueck in text:
            return int(n)
    raise AssertionError(f"{stueck!r} nicht im Prompt")


def antwort_traegt(prompt: str, schema: dict) -> dict:
    assert schema["required"][-1] == "begruendung"
    return {
        "behauptung": "Die Beklagte meint, eine Abnahme könne stillschweigend erfolgen.",
        "schriftsatz_belege": [{"nr": _nr(prompt, "S", "stillschweigend"),
                                "zitat": "dass eine Abnahme auch stillschweigend erfolgen kann"}],
        "entscheidung": "Der BGH nennt die vorbehaltlose Zahlung als Beispiel.",
        "urteil_belege": [{"nr": _nr(prompt, "U", "vorbehaltlosen"),
                           "zitat": "in der vorbehaltlosen Zahlung des restlichen Werklohns"}],
        "ergebnis": "traegt",
        "begruendung": "Die Stelle sagt das so.",
    }


def test_je_zitat_schriftsatz_und_entscheidung(akten, con, tmp_path):  # noqa: F811
    akte_id, uid = _akte_mit_urteil(akten, con, tmp_path)
    gesehen = []

    def antwort(prompt, schema):
        gesehen.append(prompt)
        return antwort_traegt(prompt, schema)

    g = gegenueberstellung.gegenueberstellen(Analyse(akten, Attrappe(antwort)), akte_id)
    assert g["anzahl"] == 2 and len(gesehen) == 1  # ohne Volltext fragt die App das Modell nicht
    prompt = gesehen[0]
    assert "(zitierende Stelle)" in prompt and "[U1 Leitsatz]" in prompt and "Rn. 22]" in prompt
    assert "Rn. 31]" not in prompt  # nur die zitierte Rn. und ihre Nachbarn
    bgh = next(z for z in g["zitate"] if z["urteil_id"] == uid)
    assert bgh["ergebnis"] == "traegt" and bgh["status"] == "belegt" and bgh["rn_zitiert"] == 22
    assert bgh["urteil_belege"][0]["stelle"] == "Rn. 22"
    assert bgh["schriftsatz_belege"][0]["ausschnitt"]["wert"].startswith("dass eine Abnahme")
    assert bgh["zitierstelle"]["dateiname"] == "05_Klageerwiderung.md"
    olg = next(z for z in g["zitate"] if z["urteil_id"] is None)
    assert olg["ergebnis"] == "nicht_pruefbar" and "Volltext" in olg["hinweis"]

    # Gespeichert: ein zweiter Lauf und die Abfrage ohne Modell fragen nicht noch einmal.
    wieder = gegenueberstellung.gegenueberstellen(Analyse(akten, Attrappe(antwort)), akte_id)
    assert len(gesehen) == 1 and next(z for z in wieder["zitate"] if z["urteil_id"])["gespeichert"] is True


def test_traegt_ohne_zitat_aus_der_entscheidung_bleibt_ohne_beleg(akten, con, tmp_path):  # noqa: F811
    akte_id, _ = _akte_mit_urteil(akten, con, tmp_path)

    def antwort(prompt, schema):
        a = antwort_traegt(prompt, schema)
        a["urteil_belege"] = [{"nr": 1, "zitat": "jede Mitteilung des Bestellers genügt stets"}]
        return a

    g = gegenueberstellung.gegenueberstellen(Analyse(akten, Attrappe(antwort)), akte_id)
    bgh = next(z for z in g["zitate"] if z["urteil_id"])
    assert bgh["status"] == "ohne_beleg" and bgh["urteil_belege"] == []


def test_nicht_vorhandene_rn_wird_genannt(akten, con, tmp_path):  # noqa: F811
    akte_id, _ = _akte_mit_urteil(akten, con, tmp_path)
    with akten:
        akten.execute("UPDATE urteilszitat SET rn_zitiert = 99 WHERE rn_zitiert = 22")
    g = gegenueberstellung.gegenueberstellen(Analyse(akten, Attrappe(antwort_traegt)), akte_id)
    bgh = next(z for z in g["zitate"] if z["urteil_id"])
    assert "Rn. 99 gibt es im vorliegenden Volltext nicht" in bgh["hinweis"]


def test_chat_frage_nach_stuetzen_gibt_die_gegenueberstellung(akten, con, tmp_path):  # noqa: F811
    akte_id, _ = _akte_mit_urteil(akten, con, tmp_path)
    frage = "Stützen die zitierten Urteile (insb. BGH VII ZR 999/19) den Vortrag?"
    assert chat.soll_gegenueberstellen(frage) and not chat.soll_gegenueberstellen("Wann war die Abnahme?")
    gesehen = []

    def antwort(prompt, schema):
        if "begruendung" in schema["properties"]:
            return antwort_traegt(prompt, schema)
        gesehen.append(prompt)
        return {"aussagen": [
            {"text": "Ja, die zitierte Entscheidung trägt den Vortrag.", "art": "einschaetzung", "zitate": [1]},
            {"text": "Ja, die zitierte Entscheidung trägt den Vortrag.", "art": "einschaetzung", "zitate": [1]},
            {"text": "Eine Gegenüberstellung, die es nicht gibt.", "art": "einschaetzung", "zitate": [7]},
        ]}

    e = chat.frage(akten, Attrappe(antwort), 32768, akte_id, frage, rechtsprechung="akte")
    zitate = e["gegenueberstellung"]["zitate"]
    assert [z["aktenzeichen"] for z in zitate] == ["VII ZR 999/19"]  # Aktenzeichen in der Frage: nur dieses
    assert "[Z1] BGH, Urteil vom 14.01.2021 – VII ZR 999/19, Rn. 22" in gesehen[0]
    assert "Entscheidung, Rn. 22: „" in gesehen[0] and frage in gesehen[0]
    erste, zweite = e["aussagen"]  # die doppelte Aussage nur einmal
    assert erste["status"] == "belegt" and erste["urteilsbelege"][0]["stelle"] == "Rn. 22"
    assert erste["urteilsbelege"][0]["urteil"].startswith("BGH, Entscheidung vom 14.01.2021")
    assert erste["fundstellen"][0]["dateiname"] == "05_Klageerwiderung.md"
    assert zweite["status"] == "ohne_beleg"
    assert chat.verlauf(akten, akte_id)[-1]["gegenueberstellung"]["zitate"][0]["ergebnis"] == "traegt"
    # Ohne Rechtsprechung bleibt es die gewöhnliche Antwort.
    normal = chat.frage(akten, Attrappe(lambda p, s: {"aussagen": []}), 32768, akte_id, frage)
    assert "gegenueberstellung" not in normal


def test_rpc_starten_und_gespeichert(con, tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    kern.ki_fabrik = lambda e, schluessel=None: Attrappe(antwort_traegt)
    akte_id, _ = _akte_mit_urteil(kern.akten, con, tmp_path)

    def aufruf(methode, **params):
        a = kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))
        assert "error" not in a, a
        return a["result"]

    assert aufruf("ki.gegenueberstellung", akte_id=akte_id)["zitate"] == []  # noch kein Modell gewählt
    aufruf("ki.einstellungen_setzen", anbieter="ollama", endpunkt="http://127.0.0.1:9", modell=Attrappe.modell)
    vorher = aufruf("ki.gegenueberstellung", akte_id=akte_id)
    assert vorher["offen"] == 1 and len(vorher["zitate"]) == 1  # nur das Zitat ohne Volltext
    auftrag = aufruf("ki.starten", aufgabe="gegenueberstellung", akte_id=akte_id)
    stand = _warte(lambda: aufruf("ki.auftrag", auftrag_id=auftrag["auftrag_id"]))
    assert stand["status"] == "fertig", stand
    nachher = aufruf("ki.gegenueberstellung", akte_id=akte_id)
    assert nachher["offen"] == 0 and {z["ergebnis"] for z in nachher["zitate"]} == {"traegt", "nicht_pruefbar"}


def test_zitierte_rn_zuerst_und_hinweis_wenn_nur_leitsatz(akten, con, tmp_path):  # noqa: F811
    akte_id, _ = _akte_mit_urteil(akten, con, tmp_path)
    gesehen = []

    def antwort(prompt, schema):
        gesehen.append(prompt)
        a = antwort_traegt(prompt, schema)
        a["urteil_belege"] = [{"nr": _nr(prompt, "U", "konkludente"), "zitat": "Eine konkludente Abnahme setzt ein "
                               "Verhalten des Bestellers voraus"}]
        return a

    g = gegenueberstellung.gegenueberstellen(Analyse(akten, Attrappe(antwort)), akte_id)
    assert re.search(r"\[U\d+ Rn\. 22\] \(zitierte Stelle\)", gesehen[0]) and "Zitiere zuerst aus" in gesehen[0]
    bgh = next(z for z in g["zitate"] if z["urteil_id"])
    assert bgh["urteil_belege"][0]["stelle"] == "Leitsatz"
    assert bgh["hinweis"] == "Belegt nur mit Leitsatz, nicht mit der zitierten Rn. 22."


def test_umformulierte_wiederholung_nur_einmal():
    assert chat._aehnlich(set("zitierte entscheidung stützt ausführungen klägers".split()),
                          set("entscheidung stützt ausführungen klägers klageschrift".split()))
    assert not chat._aehnlich(set("entscheidung stützt ausführungen".split()), set("volltext fehlt olg".split()))


def test_kennungen_werden_lesbar():
    stellen = [{"u": 1, "stelle": "Leitsatz"}, {"u": 3, "stelle": "Rn. 67"}]
    t = gegenueberstellung._ohne_marken(
        "Der Schriftsatz behauptet in [S25], dass die Entscheidung in [U3 Rn. 67] und U1 das sagt (S31).", stellen)
    assert t == "Der Schriftsatz behauptet, dass die Entscheidung in Rn. 67 und Leitsatz das sagt."


def test_falsche_rn_zweiter_blick(akten, con, tmp_path):  # noqa: F811
    akte_id, uid = _akte_mit_urteil(akten, con, tmp_path)
    with akten:
        akten.execute("UPDATE urteil_abschnitt SET text = ? WHERE urteil_id = ? AND rn = 30",
                      ("Eine Abnahme kann stillschweigend erfolgen, wenn der Besteller das Werk nutzt.", uid))
    gesehen = []

    def antwort(prompt, schema):
        gesehen.append(prompt)
        if "trägt die Aussage nicht. Prüfe" not in prompt:
            return {**antwort_traegt(prompt, schema), "ergebnis": "traegt_nicht", "urteil_belege": []}
        return {"behauptung": "x", "schriftsatz_belege": [], "entscheidung": "y", "ergebnis": "traegt",
                "begruendung": "z", "urteil_belege": [{"nr": _nr(prompt, "U", "Werk nutzt"),
                                                        "zitat": "Eine Abnahme kann stillschweigend erfolgen"}]}

    g = gegenueberstellung.gegenueberstellen(Analyse(akten, Attrappe(antwort)), akte_id)
    assert len(gesehen) == 2 and "Rn. 22]" not in gesehen[1] and "Rn. 30]" in gesehen[1]
    bgh = next(z for z in g["zitate"] if z["urteil_id"])
    assert bgh["ergebnis"] == "traegt" and bgh["urteil_belege"][0]["stelle"] == "Rn. 30"
    assert "findet sich aber in Rn. 30" in bgh["hinweis"] and bgh["rn_zitiert"] == 22
