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
from juracore.ki.anbieter import KiFehler

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

    assert "Rechne Zinsen, Fristen, Anwalts- oder Gerichtskosten nicht selbst" in modell.anfragen[0]
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


URTEIL = (
    "Urteil\n\n"
    "Die Beklagte wird verurteilt, an die Klägerin 14.448,73 € nebst Zinsen in Höhe von fünf Prozentpunkten über dem "
    "Basiszinssatz seit dem 30.07.2025 zu zahlen. Die Beklagte trägt die Kosten des Rechtsstreits.\n\n"
    "Der Streitwert wird auf 14.555,40 € festgesetzt."
)


def _urteilsakte(akten, con, tmp_path) -> int:
    a = akte.akte_anlegen(akten, "Brückner ./. Autohaus")
    pfad = tmp_path / "08_Urteil.md"
    pfad.write_text(URTEIL, encoding="utf-8")
    akte.importiere(akten, con, a["id"], pfad, tmp_path / "ablage", ocr=False)
    return a["id"]


def _kostenangaben(prompt: str) -> list[dict]:
    d, n = _zeile(prompt, "Streitwert wird")
    return [{"feld": "streitwert", "wert": "14.555,40 €", "dokument": d, "absatz": n,
             "zitat": "Der Streitwert wird auf 14.555,40 € festgesetzt"}]


def test_rvg_kosten_mit_dem_prozesskostenrechner(akten, con, tmp_path):
    akte_id = _urteilsakte(akten, con, tmp_path)
    modell = Attrappe(lambda p, s: {"aussagen": [], "berechnungen": [
        {"rechner": "prozesskosten", "angaben": _kostenangaben(p)}]})
    erg = chat.frage(akten, modell, 32768, akte_id, "Bitte rechne die RVG-Kosten aus, die die Gegenseite "
                     "erstatten muss.", rechner=True, heute=date(2026, 10, 30))

    assert '"prozesskosten"' in modell.anfragen[0]
    a = erg["aussagen"][0]
    b = a["berechnung"]
    assert b["rechner"] == "prozesskosten" and a["status"] == "belegt"
    assert {e["feld"]: e["quelle"] for e in b["eingaben"]} == {
        "streitwert": None, "instanz": "annahme", "ende": "annahme"}
    # 14.555,40 €, erste Instanz mit Urteil, Gebührenrecht seit 01.06.2025: volle Gebühr RVG 762 €, GKG 344 €
    # (Anlage 2 RVG/GKG, Wertstufe bis 16.000 €).
    assert b["ergebnis"]["gebuehr_rvg"] == "762.0" and b["ergebnis"]["gebuehr_gkg"] == "344.0"
    # (1,3 + 1,2) × 762 € = 1.905 € + 20 € Pauschale = 1.925 € + 19 % USt = 2.290,75 €; Gericht 3,0 × 344 €
    assert b["ergebnis"]["summe_eigene"] == "2290.75"
    assert b["ergebnis"]["summe_gericht"] == "1032.00"
    assert "eigene Anwaltskosten 2.290,75 €" in a["text"] and "Gerichtskosten 1.032,00 €" in a["text"]
    assert any("§ 60 RVG" in h for h in b["ergebnis"]["hinweise"])


def test_bei_erstattungsfrage_der_erstattungsbetrag(akten, con, tmp_path):
    akte_id = _urteilsakte(akten, con, tmp_path)
    erg = chat.frage(akten, Attrappe(lambda p, s: {"aussagen": [], "berechnungen": []}), 32768, akte_id,
                     "Welche Rechtsanwaltsvergütung nach RVG kann ich von der Gegenseite ersetzt verlangen?",
                     rechner=True, heute=date(2026, 10, 30))
    a = erg["aussagen"][0]
    # 2.290,75 € eigene Anwaltskosten + 1.032,00 € Gerichtskosten
    assert a["text"].startswith("Von der Gegenseite zu erstatten") and "3.322,75 €" in a["text"]
    assert any("Vorbem. 3 Abs. 4 VV RVG" in h for h in a["berechnung"]["ergebnis"]["hinweise"])


def test_bei_kosten_kein_zinsrechner(akten, con, tmp_path):
    """Fragt der Nutzer nach Kosten, zählt ein Vorschlag für den Zinsrechner nicht; die App fragt gezielt nach den
    Angaben für den Prozesskostenrechner (Fall aus dem Test am 30.10.2026)."""
    akte_id = _urteilsakte(akten, con, tmp_path)

    def antwort(prompt, schema):
        if "Beantworte die Frage nicht" in prompt:
            assert "„prozesskosten“" in prompt
            return {"berechnungen": [{"rechner": "prozesskosten", "angaben": _kostenangaben(prompt)}]}
        d, n = _zeile(prompt, "14.448,73")
        return {"aussagen": [], "berechnungen": [{"rechner": "zinsen", "angaben": [
            {"feld": "hauptbetrag", "wert": "14.448,73 €", "dokument": d, "absatz": n, "zitat": "14.448,73 €"},
            {"feld": "zinsbeginn", "wert": "30.07.2025", "dokument": d, "absatz": n, "zitat": "seit dem 30.07.2025"},
            {"feld": "zinssatz", "wert": "5 Prozentpunkte über dem Basiszinssatz", "dokument": d, "absatz": n,
             "zitat": "fünf Prozentpunkten über dem Basiszinssatz"},
        ]}]}

    chat.frage(akten, Attrappe(lambda p, s: {"aussagen": []}), 32768, akte_id,
               "Welche Rechtsanwaltsvergütung nach RVG kann ich von der Gegenseite ersetzt verlangen?")
    erg = chat.frage(akten, Attrappe(antwort), 32768, akte_id, "Bitte rechne das aus.", rechner=True,
                     heute=date(2026, 10, 30))
    rechner = [a["berechnung"]["rechner"] for a in erg["aussagen"] if a["art"] == "berechnung"]
    assert rechner == ["prozesskosten"]


def test_streitwert_findet_die_app_selbst(akten, con, tmp_path):
    """Das Modell liefert keine Angaben, auch nicht auf die Nachfrage (Test von René am 30.10.2026): Die App liest
    den Streitwert selbst aus dem Urteil, mit Fundstelle."""
    akte_id = _urteilsakte(akten, con, tmp_path)
    modell = Attrappe(lambda p, s: {"aussagen": [
        {"text": "Die Dokumente enthalten keine Informationen zur Berechnung der Rechtsanwaltsvergütung nach RVG.",
         "art": "hinweis", "belege": []}], "berechnungen": []})
    erg = chat.frage(akten, modell, 32768, akte_id, "Bitte rechne diese Kosten aus.", rechner=True,
                     heute=date(2026, 10, 30))
    a = erg["aussagen"][0]
    assert a["berechnung"]["rechner"] == "prozesskosten" and a["status"] == "belegt"
    streitwert = a["berechnung"]["eingaben"][0]
    assert streitwert["wert"] == "14.555,40 €" and streitwert["fundstelle"] is not None
    assert len(modell.anfragen) == 1  # keine Nachfrage nötig
    assert not any(x["art"] == "hinweis" for x in erg["aussagen"])


def test_streitwert_des_dokuments_geht_dem_modell_vor(akten, con, tmp_path):
    akte_id = _urteilsakte(akten, con, tmp_path)
    erg = chat.frage(akten, Attrappe(lambda p, s: {"aussagen": [], "berechnungen": [{"rechner": "prozesskosten",
                     "angaben": [{"feld": "streitwert", "wert": "14.900,00 €", "dokument": 1, "absatz": 1,
                                  "zitat": "Urteil"}]}]}),
                     32768, akte_id, "Bitte berechne die Prozesskosten.", rechner=True)
    e = erg["aussagen"][0]["berechnung"]["eingaben"][0]
    assert e["wert"] == "14.555,40 €" and e["status"] == "belegt"


def test_streitwert_aus_den_stammdaten(akten, con, tmp_path):
    from juracore.aktenverwaltung import einrichten
    from juracore.eigene import daten as eigene

    eigene.einrichten(akten)
    einrichten(akten)
    akte_id = _akte(akten, con, tmp_path)
    with akten:
        akten.execute("UPDATE akte SET gegenstandswert = '12500.00' WHERE id = ?", (akte_id,))
    erg = chat.frage(akten, Attrappe(lambda p, s: {"aussagen": [], "berechnungen": []}), 32768, akte_id,
                     "Welche Anwaltsgebühren fallen an?", rechner=True)
    e = erg["aussagen"][0]["berechnung"]["eingaben"][0]
    assert e["wert"] == "12.500,00 €" and e["quelle"] == "akte"


def test_ohne_streitwert_wird_er_als_fehlend_genannt(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    erg = chat.frage(akten, Attrappe(lambda p, s: {"aussagen": [], "berechnungen": []}), 32768, akte_id,
                     "Welche Anwaltsgebühren fallen an?", rechner=True)
    b = erg["aussagen"][0]["berechnung"]
    assert b["fehlt"] == ["Streitwert"] and "fehlt" in erg["aussagen"][0]["text"]


def test_streitwert_angabe_bevorzugt_festgesetzten_wert():
    texte = [{1: "Streitwert (vorläufig): 10.000,00 €"}, {4: "Der Streitwert wird auf 9.500,00 € festgesetzt."}]
    assert wissen.streitwert_angabe(texte)["wert"] == "9.500,00 €"
    texte = [{1: "Vorläufiger Streitwert: 10.000,00 €"}, {4: "Gegenstandswert: 9.500 €"}]
    assert wissen.streitwert_angabe(texte)["dokument"] == 2


def test_passende_rechner():
    assert wissen.passende_rechner("Bitte rechne diese Kosten aus.") == {wissen.PROZESSKOSTEN}
    assert wissen.passende_rechner("Rechne die Zinsen aus.") == {wissen.ZINSEN}
    assert wissen.passende_rechner("Rechne das aus.", "Wann endet die Frist?") == {wissen.FRIST}
    assert wissen.passende_rechner("Rechne das aus.") == set()


def test_prozesskosten_angaben_werden_geprueft(akten, con, tmp_path):
    akte_id = _urteilsakte(akten, con, tmp_path)

    def antwort(prompt, schema):
        d, n = _zeile(prompt, "Streitwert wird")
        return {"aussagen": [], "berechnungen": [{"rechner": "prozesskosten", "angaben": [
            *_kostenangaben(prompt),
            {"feld": "instanz", "wert": "berufung", "dokument": d, "absatz": n, "zitat": "Der Streitwert wird"},
            {"feld": "auftrag", "wert": "02.04.2025", "dokument": 0, "absatz": 0, "zitat": "Auftrag am 02.04.2025"},
        ]}]}

    erg = chat.frage(akten, Attrappe(antwort), 32768, akte_id,
                     "Welche Gebühren fallen an? Der Auftrag kam am 02.04.2025.", rechner=True)
    b = erg["aussagen"][0]["berechnung"]
    status = {e["feld"]: e["status"] for e in b["eingaben"]}
    assert status["instanz"] == "ohne_beleg" and status["auftrag"] == "belegt"
    assert b["ergebnis"]["fassung"] == "2021"


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


def test_nur_zitierte_normen_ohne_suche(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    mit, _ = wissen.waehle_normen(con, akten, akte_id, None, "Verjährung des Anspruchs")
    ohne, _ = wissen.waehle_normen(con, akten, akte_id, None, "Verjährung des Anspruchs", suche=False)
    assert {n["herkunft"] for n in mit} == {"zitiert", "suche"}
    assert [n["bezeichnung"] for n in ohne] == ["§ 280"]


def test_ergaenzte_normen_und_gesetze(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    normen, fehlend = wissen.waehle_normen(con, akten, akte_id, None, "Wer ist Partei?", suche=False,
                                           ergaenzt=["§ 437 BGB", "HGB", ""])
    assert [n["bezeichnung"] for n in normen] == ["§ 437", "§ 280"]  # ergänzte Norm zuerst
    assert fehlend == ["HGB"]  # nicht in der Wissensbasis
    # Ein geladenes Gesetz erweitert die Suche: Treffer aus der ZPO zu „Klage“.
    normen, _ = wissen.waehle_normen(con, akten, akte_id, None, "Klageerhebung Zustellung", ergaenzt=["ZPO"])
    assert any(n["gesetz"] == "ZPO" for n in normen)


def test_zu_lange_anfrage_wird_mit_weniger_gesetzen_wiederholt(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    anfragen = []

    class Knapp:
        modell = "attrappe:1b"

        def chat(self, system, nutzer, schema):
            anfragen.append(nutzer)
            if len(anfragen) == 1:
                raise KiFehler("LM Studio: The number of tokens to keep from the initial prompt is greater than "
                               "the context length.")
            return {"aussagen": []}

    erg = chat.frage(akten, Knapp(), 32768, akte_id, "Verjährung und Schadensersatz?", gesetze=con)
    assert len(anfragen) == 2 and len(anfragen[1]) < len(anfragen[0])
    assert erg["wissen"]["gekuerzt"] is True

    class ImmerZuLang(Knapp):
        def chat(self, system, nutzer, schema):
            raise KiFehler("context length exceeded")

    with pytest.raises(KiFehler, match="Context Length"):
        chat.frage(akten, ImmerZuLang(), 32768, akte_id, "Verjährung?", gesetze=con)


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
                     gesetze="zitiert", land="BW")
    stand = _warte(lambda: aufruf("ki.auftrag", auftrag_id=auftrag["auftrag_id"]))
    assert stand["status"] == "fertig", stand
    assert "berechnungen" in gesehen[0][1]["properties"]
    assert stand["ergebnis"]["wissen"]["rechner"] is True and "gesetze" in stand["ergebnis"]["wissen"]


def test_doppelte_aussagen_und_fundstellen_einmal(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)

    def antwort(prompt, schema):
        d, n = _zeile(prompt, "in Verzug")
        beleg = [{"dokument": d, "absatz": n, "zitat": "Die Beklagte befindet sich seit dem 15.04.2026 in Verzug"},
                 {"dokument": d, "absatz": n, "zitat": "Der Anspruch folgt aus § 280 Abs. 1 BGB"}]
        return {"aussagen": [
            {"text": "Die Beklagte ist seit dem 15.04.2026 in Verzug.", "art": "tatsache", "belege": beleg},
            {"text": "Die Beklagte ist seit dem 15.04.2026 in Verzug", "art": "einschaetzung", "belege": []},
        ]}

    erg = chat.frage(akten, Attrappe(antwort), 32768, akte_id, "Seit wann besteht Verzug?")
    assert len(erg["aussagen"]) == 1 and len(erg["aussagen"][0]["fundstellen"]) == 1


def test_antwort_ist_begrenzt_aber_nicht_fuer_externe(akten, con, tmp_path):
    from juracore.ki.anbieter import _streng

    akte_id = _akte(akten, con, tmp_path)
    schemas = []
    chat.frage(akten, Attrappe(lambda p, s: schemas.append(s) or {"aussagen": [], "berechnungen": []}), 32768,
               akte_id, "Rechne die Zinsen aus.", rechner=True, gesetze=con)
    s = schemas[0]
    assert s["properties"]["aussagen"]["maxItems"] == chat.HOECHSTENS
    assert s["properties"]["aussagen"]["items"]["properties"]["normbelege"]["maxItems"] == 2
    assert "maxItems" not in json.dumps(_streng(s)) and "maxLength" not in json.dumps(_streng(s))


# --- Rechtsprechung (Entscheidungen frei erfunden) -------------------------------------------------

SCHRIFTSATZ_MIT_URTEIL = (
    "Klageerwiderung\n\n"
    "Die Abnahme wurde nicht verweigert. Der Bundesgerichtshof hat entschieden, dass eine Abnahme auch "
    "stillschweigend erfolgen kann (BGH, Urteil vom 14.01.2021 – VII ZR 999/19, Rn. 22).\n\n"
    "Ferner verweist die Beklagte auf OLG München, Urteil vom 03.05.2022 – 28 U 9999/21."
)
LEITSATZ = "Eine konkludente Abnahme setzt ein Verhalten des Bestellers voraus, das die Billigung des Werks erkennen lässt."
RN_22 = ("Eine stillschweigende Abnahme kann insbesondere in der vorbehaltlosen Zahlung des restlichen Werklohns "
         "oder im Bezug des fertiggestellten Hauses liegen.")
RN_30 = "Die Mängelrüge nach Ablauf der Prüffrist steht der Annahme einer Billigung regelmäßig nicht entgegen."


def _akte_mit_urteil(akten, con, tmp_path) -> tuple[int, int]:
    a = akte.akte_anlegen(akten, "Weber ./. Bau GmbH")
    pfad = tmp_path / "05_Klageerwiderung.md"
    pfad.write_text(SCHRIFTSATZ_MIT_URTEIL, encoding="utf-8")
    akte.importiere(akten, con, a["id"], pfad, tmp_path / "ablage", ocr=False)
    with akten:
        uid = akten.execute(
            """INSERT INTO urteil (akte_id, zitat, gericht, aktenzeichen, az_norm, datum, quelle, herkunft, dateiname,
                                   format, sha256, original, lesart, hinweise, hinzugefuegt_am)
               VALUES (?, ?, 'BGH', 'VII ZR 999/19', 'VII ZR 999/19', '2021-01-14', 'rii', 'Test', 'x.zip', 'rii',
                       'abc', 'x', 'datei', '[]', '2026-10-25')""",
            (a["id"], "BGH, Urteil vom 14.01.2021 – VII ZR 999/19")).lastrowid
        akten.executemany(
            "INSERT INTO urteil_abschnitt (urteil_id, nr, seite, rn, text, teil) VALUES (?, ?, NULL, ?, ?, ?)",
            [(uid, 1, None, LEITSATZ, "leitsatz"), (uid, 2, 22, RN_22, "gruende"),
             (uid, 3, 30, RN_30, "gruende"), (uid, 4, 31, "Die Kosten trägt die Beklagte.", "gruende")])
    return a["id"], uid


def test_urteile_der_akte_leitsatz_zitierte_rn_und_fehlende(akten, con, tmp_path):
    akte_id, uid = _akte_mit_urteil(akten, con, tmp_path)
    urteile, fehlend = wissen.waehle_urteile(akten, akte_id, None, "Wann ist eine Abnahme erfolgt?", suche=False)
    assert [u["urteil_id"] for u in urteile] == [uid]
    assert [wissen._stelle(a) for a in urteile[0]["absaetze"]] == ["Leitsatz", "Rn. 22"]
    assert fehlend == ["OLG München, Urteil vom 03.05.2022 – 28 U 9999/21"]
    text = wissen.urteile_text(urteile)
    assert "[U1] BGH, Entscheidung vom 14.01.2021 – VII ZR 999/19" in text and "[U1 Rn. 22]" in text

    mit_suche, _ = wissen.waehle_urteile(akten, akte_id, None, "Hindert die Mängelrüge die Billigung?")
    assert "Rn. 30" in [wissen._stelle(a) for a in mit_suche[0]["absaetze"]]
    assert "Rn. 31" not in [wissen._stelle(a) for a in mit_suche[0]["absaetze"]]


def test_urteilsbelege_werden_am_volltext_geprueft(akten, con, tmp_path):
    akte_id, uid = _akte_mit_urteil(akten, con, tmp_path)
    gesehen = []

    def antwort(prompt, schema):
        gesehen.append((prompt, schema))
        d, n = _zeile(prompt, "stillschweigend")
        return {"aussagen": [
            {"text": "Die Zahlung des Restwerklohns kann eine Abnahme sein.", "art": "einschaetzung", "belege": [],
             "urteilsbelege": [{"urteil": 1, "zitat": "in der vorbehaltlosen Zahlung des restlichen Werklohns"}]},
            {"text": "Laut BGH genügt jede Mitteilung.", "art": "einschaetzung", "belege": [],
             "urteilsbelege": [{"urteil": 1, "zitat": "jede Mitteilung des Bestellers genügt stets"}]},
            {"text": "Die Beklagte beruft sich auf den BGH.", "art": "tatsache",
             "belege": [{"dokument": d, "absatz": n, "zitat": "eine Abnahme auch stillschweigend erfolgen kann"}],
             "urteilsbelege": []},
        ]}

    e = chat.frage(akten, Attrappe(antwort), 32768, akte_id, "Liegt eine Abnahme vor?", rechtsprechung="akte")
    prompt, schema = gesehen[0]
    assert "Rechtsprechung aus der Akte:" in prompt and wissen.ANWEISUNG_RECHTSPRECHUNG in prompt
    assert "urteilsbelege" in schema["properties"]["aussagen"]["items"]["required"]
    erste, zweite, dritte = e["aussagen"]
    assert erste["status"] == "belegt"
    assert erste["urteilsbelege"][0]["urteil_id"] == uid and erste["urteilsbelege"][0]["stelle"] == "Rn. 22"
    assert erste["urteilsbelege"][0]["ausschnitt"]["wert"].startswith("in der vorbehaltlosen")
    assert zweite["status"] == "ohne_beleg" and "urteilsbelege" not in zweite
    assert dritte["status"] == "belegt"
    assert e["wissen"]["urteile"] == ["BGH, Entscheidung vom 14.01.2021 – VII ZR 999/19"]
    assert e["wissen"]["urteile_fehlend"] == ["OLG München, Urteil vom 03.05.2022 – 28 U 9999/21"]


def test_ohne_rechtsprechung_kein_urteilstext(akten, con, tmp_path):
    akte_id, _ = _akte_mit_urteil(akten, con, tmp_path)
    gesehen = []
    e = chat.frage(akten, Attrappe(lambda p, s: gesehen.append((p, s)) or {"aussagen": []}), 32768, akte_id,
                   "Liegt eine Abnahme vor?")
    assert "Rechtsprechung aus der Akte" not in gesehen[0][0] and "wissen" not in e
    assert "urteilsbelege" not in json.dumps(gesehen[0][1])


def test_zu_lang_mit_rechtsprechung_nur_leitsaetze(akten, con, tmp_path):
    akte_id, _ = _akte_mit_urteil(akten, con, tmp_path)
    gesehen = []

    def antwort(prompt, schema):
        gesehen.append(prompt)
        if len(gesehen) == 1:
            raise KiFehler("Trying to keep the first 9000 tokens when context the overflows.")
        return {"aussagen": []}

    e = chat.frage(akten, Attrappe(antwort), 32768, akte_id, "Hindert die Mängelrüge die Billigung?",
                   rechtsprechung="suche")
    assert "[U1 Rn. 30]" in gesehen[0] and "[U1 Rn. 30]" not in gesehen[1] and "[U1 Leitsatz]" in gesehen[1]
    assert e["wissen"]["gekuerzt"] is True


def test_rpc_prueft_die_stufe_der_rechtsprechung(tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    a = kern.bearbeite(json.dumps({"id": 1, "method": "ki.chat_fragen",
                                   "params": {"akte_id": 1, "frage": "x", "rechtsprechung": "alles"}}))
    assert "Rechtsprechung" in a["error"]["message"]
