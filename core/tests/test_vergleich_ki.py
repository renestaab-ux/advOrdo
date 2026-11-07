"""Vergleich mit dem Sprachmodell: Werte mit Bezug, Zusammenordnen, Einschätzung, Rückfall auf die Regeln.

Ohne echtes Modell, mit einer Attrappe. Die Dokumente sind frei erfunden (angelehnt an die fiktive Testakte).
"""

import re
import time

import pytest

from juracore.dokumente import akte
from juracore.ki import vergleich
from juracore.ki.analyse import Analyse
from juracore.rpc import Kern

KAUFVERTRAG = """Kaufvertrag über ein gebrauchtes Kraftfahrzeug

Der Kaufpreis beträgt 14.900,00 €. Die Käuferin leistet eine Anzahlung von 1.000,00 €.

Kilometerstand bei Übergabe: 68.400 km.
"""

RUECKTRITT = """Sehr geehrte Damen und Herren,

namens unserer Mandantin erklären wir den Rücktritt und fordern die Rückzahlung des Kaufpreises von 14.990,00 €.
"""

KLAGEERWIDERUNG = """Klageerwiderung

(1) Bei Auslieferung zeigte der Tacho 64.800 km. Heute zeigt der Tacho 72.600 km.

(2) Bestritten wird, dass die Klägerin 15.500,00 € gezahlt hat.
"""


def _nr(prompt: str, stueck: str) -> int:
    for nr, text in re.findall(r"^\[(\d+)\] (.*)$", prompt, re.M):
        if stueck in text:
            return int(nr)
    raise AssertionError(f"{stueck!r} nicht im Prompt")


def _kennung(prompt: str, praefix: str, stueck: str) -> str:
    for k, text in re.findall(rf"^\[({praefix}\d+)\] (.*)$", prompt, re.M):
        if stueck in text:
            return k
    raise AssertionError(f"{stueck!r} nicht im Prompt")


class Modell:
    """Antwortet wie ein brauchbares Modell, mit einem erfundenen und einem bestrittenen Wert."""

    modell = "attrappe:1b"

    def __init__(self, einschaetzung="abweichung"):
        self.anfragen: list[str] = []
        self.einschaetzung = einschaetzung

    def chat(self, system, nutzer, schema):
        self.anfragen.append(nutzer)
        felder = schema["properties"]
        kopf = nutzer.split("\n", 1)[0]
        if "werte" in felder:
            if "Kaufvertrag" in kopf:
                return {"werte": [
                    {"wert": "14.900,00 €", "bezug": "Kaufpreis des Fahrzeugs", "haltung": "behauptet",
                     "absatz": _nr(nutzer, "Kaufpreis"), "zitat": "Der Kaufpreis beträgt 14.900,00 €"},
                    {"wert": "1.000,00 €", "bezug": "Anzahlung", "haltung": "behauptet",
                     "absatz": _nr(nutzer, "Anzahlung"), "zitat": "leistet eine Anzahlung von 1.000,00 €"},
                    {"wert": "68.400 km", "bezug": "Kilometerstand bei Übergabe", "haltung": "behauptet",
                     "absatz": _nr(nutzer, "68.400"), "zitat": "Kilometerstand bei Übergabe: 68.400 km"},
                ]}
            if "Klageerwiderung" in kopf:
                return {"werte": [
                    {"wert": "64.800 km", "bezug": "Tachostand bei Auslieferung", "haltung": "behauptet",
                     "absatz": _nr(nutzer, "Auslieferung"), "zitat": "Bei Auslieferung zeigte der Tacho 64.800 km"},
                    {"wert": "72.600 km", "bezug": "heutiger Kilometerstand", "haltung": "behauptet",
                     "absatz": _nr(nutzer, "Heute"), "zitat": "Heute zeigt der Tacho 72.600 km"},
                    {"wert": "15.500,00 €", "bezug": "gezahlter Betrag", "haltung": "bestritten",
                     "absatz": _nr(nutzer, "Bestritten"), "zitat": "dass die Klägerin 15.500,00 € gezahlt hat"},
                    {"wert": "99.999 km", "bezug": "erfunden", "haltung": "behauptet", "absatz": 1,
                     "zitat": "Das steht nirgends in diesem Text"},
                ]}
            return {"werte": []}  # Der Kaufpreis im Rücktrittsschreiben entgeht dem Modell; die Regeln finden ihn.
        if "gruppen" in felder:
            if "(Kilometer)" in nutzer:
                return {"gruppen": [{"titel": "Kilometerstand bei Übergabe", "bezuege": [
                    _kennung(nutzer, "B", "Kilometerstand bei Übergabe"),
                    _kennung(nutzer, "B", "Tachostand bei Auslieferung"), "B99"]}]}
            return {"gruppen": []}
        if "bewertungen" in felder:
            return {"bewertungen": [
                {"kennung": k, "einschaetzung": self.einschaetzung, "erklaerung": f"Einschätzung zu {titel}."}
                for k, titel in re.findall(r"^\[(M\d+)\] (.*)$", nutzer, re.M)]}
        if "angaben" in felder:
            return {"angaben": []}
        return {"widersprueche": []}


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    yield con
    con.close()


def _akte(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Brückner ./. Autohaus")
    for name, text, tag in (("01_Kaufvertrag.md", KAUFVERTRAG, "Kläger"),
                            ("04_Ruecktritt.md", RUECKTRITT, "Kläger"),
                            ("06_Klageerwiderung.md", KLAGEERWIDERUNG, "Beklagter")):
        pfad = tmp_path / name
        pfad.write_text(text, encoding="utf-8")
        akte.importiere(akten, con, a["id"], pfad, tmp_path / "ablage", ocr=False, tags=[tag])
    return a["id"]


def _merkmal(ergebnis, titel):
    return next(m for m in ergebnis["merkmale"] if m["titel"] == titel)


def test_bezug_statt_merkmalswort(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    modell = Modell()
    e = vergleich.vergleiche(Analyse(akten, modell), akte_id)
    assert e["quelle"] == "ki" and e["modell"] == "attrappe:1b"

    # Die Regeln kennen „Tacho bei Auslieferung“ nicht; das Modell ordnet ihn dem Kilometerstand bei Übergabe zu.
    km = _merkmal(e, "Kilometerstand bei Übergabe")
    assert km["status"] == "abweichend" and km["quelle"] == "ki"
    assert {w["wert"] for w in km["werte"]} == {"68400", "64800"}
    assert km["einordnung"] == ["zwischen_parteien"]
    assert km["erklaerung"] == "Einschätzung zu Kilometerstand bei Übergabe."
    f = next(w for w in km["werte"] if w["wert"] == "64800")["fundstellen"][0]
    assert f["bezug"] == "Tachostand bei Auslieferung" and f["haltung"] == "behauptet" and f["quelle"] == "ki"
    assert f["ausschnitt"]["wert"] == "64.800 km"

    # Heutiger Kilometerstand und Anzahlung sind etwas anderes und stehen für sich.
    assert _merkmal(e, "heutiger Kilometerstand")["status"] == "einzeln"
    assert _merkmal(e, "Anzahlung")["status"] == "einzeln"

    # Den Kaufpreis im Rücktrittsschreiben findet nur die Regel; er kommt in das Merkmal des Modells.
    preis = _merkmal(e, "Kaufpreis des Fahrzeugs")
    assert preis["status"] == "abweichend"
    regel = next(w for w in preis["werte"] if w["wert"] == "14990.00")["fundstellen"][0]
    assert regel["quelle"] == "regel" and regel["dateiname"] == "04_Ruecktritt.md"
    # Was beide finden, steht nur einmal da.
    assert len(next(w for w in preis["werte"] if w["wert"] == "14900.00")["fundstellen"]) == 1

    # Erfunden (Zitat nicht im Text) und bestritten zählen nicht.
    ke = next(d for d in e["ki_dokumente"] if d["dateiname"] == "06_Klageerwiderung.md")
    assert ke["verworfen"] == 1 and ke["bestritten"] == 1 and ke["werte"] == 2
    assert all(w["wert"] not in ("15500.00", "99999") for m in e["merkmale"] for w in m["werte"])
    assert e["zaehlung"]["abweichend"] == 2 and e["inhaltlich"]["widersprueche"] == []

    # Zweiter Lauf: alles aus dem Speicher, ohne neue Anfrage.
    vorher = len(modell.anfragen)
    wieder = vergleich.gespeichert(Analyse(akten, modell), akte_id)
    assert wieder["gespeichert"] is True and len(modell.anfragen) == vorher
    assert [m["titel"] for m in wieder["merkmale"]] == [m["titel"] for m in e["merkmale"]]


def test_verschiedenes_steht_eigens(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    e = vergleich.vergleiche(Analyse(akten, Modell(einschaetzung="verschiedenes")), akte_id)
    km = _merkmal(e, "Kilometerstand bei Übergabe")
    assert km["status"] == "verschieden" and km["erklaerung"]
    assert e["zaehlung"]["verschieden"] == 1
    # Die Einschätzung bekommt nur, was das Modell gesehen hat; der von der Regel ergänzte Kaufpreis bleibt
    # abweichend.
    assert _merkmal(e, "Kaufpreis des Fahrzeugs")["status"] == "abweichend"


def test_nur_zwei_dokumente(akten, con, tmp_path):
    akte_id = _akte(akten, con, tmp_path)
    ids = [z[0] for z in akten.execute("SELECT id FROM dokument ORDER BY dateiname")]
    e = vergleich.vergleiche(Analyse(akten, Modell()), akte_id, [ids[0], ids[2]])
    assert e["dokumente"] == 2
    assert all(f["dokument_id"] in (ids[0], ids[2])
               for m in e["merkmale"] for w in m["werte"] for f in w["fundstellen"])
    assert vergleich.gespeichert(Analyse(akten, Modell()), akte_id) is None  # ganze Akte noch nicht verglichen


def _warte(kern, auftrag_id):
    for _ in range(300):
        stand = kern.methoden["ki.auftrag"](auftrag_id=auftrag_id)
        if stand["status"] != "laeuft":
            return stand
        time.sleep(0.02)
    raise AssertionError("Auftrag läuft zu lange")


def test_rpc_ki_zuerst_regeln_als_rueckfall(tmp_path):
    kern = Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    akte_id = akte.akte_anlegen(kern.akten, "Brückner ./. Autohaus")["id"]
    for name, text in (("01_Kaufvertrag.md", KAUFVERTRAG), ("06_Klageerwiderung.md", KLAGEERWIDERUNG)):
        (tmp_path / name).write_text(text, encoding="utf-8")
        kern.methoden["akten.importieren"](akte_id=akte_id, pfad=str(tmp_path / name))
    # Ohne Modell: die Regeln.
    assert kern.methoden["ki.vergleich"](akte_id=akte_id) == {"status": "aus", "abgeschaltet": False}

    modell = Modell()
    kern.ki_fabrik = lambda e, schluessel=None: modell
    kern.methoden["ki.einstellungen_setzen"](anbieter="ollama", endpunkt="http://127.0.0.1:9", modell="attrappe:1b")
    start = kern.methoden["ki.vergleich"](akte_id=akte_id)
    assert start["status"] == "laeuft" and start["auftrag"]["titel"] == "KI-Vergleich"
    # Ein zweiter Aufruf (Doppelaufruf der Oberfläche) bekommt denselben Auftrag.
    zweit = kern.methoden["ki.vergleich"](akte_id=akte_id)
    assert zweit["status"] in ("laeuft", "fertig")
    stand = _warte(kern, start["auftrag"]["auftrag_id"])
    assert stand["status"] == "fertig", stand
    assert _merkmal(stand["ergebnis"], "Kilometerstand bei Übergabe")["status"] == "abweichend"

    vorher = len(modell.anfragen)
    fertig = kern.methoden["ki.vergleich"](akte_id=akte_id, automatisch=True)
    assert fertig["status"] == "fertig" and fertig["ergebnis"]["gespeichert"] is True
    assert len(modell.anfragen) == vorher

    # „KI verwenden“ aus: wieder die Regeln.
    kern.methoden["ki.schalten"](an=False)
    assert kern.methoden["ki.vergleich"](akte_id=akte_id)["status"] == "aus"


def test_externe_ki_vergleicht_nur_auf_knopfdruck(tmp_path):
    kern = Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    akte_id = akte.akte_anlegen(kern.akten, "Brückner ./. Autohaus")["id"]
    (tmp_path / "01.md").write_text(KAUFVERTRAG, encoding="utf-8")
    kern.methoden["akten.importieren"](akte_id=akte_id, pfad=str(tmp_path / "01.md"))
    modell = Modell()
    kern.ki_fabrik = lambda e, schluessel=None: modell
    kern.methoden["ki.extern_setzen"](freigegeben=True, anbieter="anthropic", modell="claude-opus-5-5",
                                      aktiv="extern", schluessel="sk-test")
    assert kern.methoden["ki.vergleich"](akte_id=akte_id, automatisch=True) == {"status": "extern"}
    assert modell.anfragen == []
    start = kern.methoden["ki.vergleich"](akte_id=akte_id)
    assert start["status"] == "laeuft"
    _warte(kern, start["auftrag"]["auftrag_id"])


def test_probelauf_mit_vergleich(tmp_path, monkeypatch, capsys):
    import json

    from juracore.ki import anbieter, pruefen

    ordner = tmp_path / "Akte"
    (ordner / "Kläger").mkdir(parents=True)
    (ordner / "Beklagter").mkdir()
    (ordner / "Kläger" / "01_Kaufvertrag.md").write_text(KAUFVERTRAG, encoding="utf-8")
    (ordner / "Kläger" / "04_Ruecktritt.md").write_text(RUECKTRITT, encoding="utf-8")
    (ordner / "Beklagter" / "06_Klageerwiderung.md").write_text(KLAGEERWIDERUNG, encoding="utf-8")
    erwartungen = tmp_path / "erwartungen.json"
    erwartungen.write_text(json.dumps({"widersprueche": [
        {"id": "W4", "thema": "Kilometerstand", "aussagen": [{"dok": "01", "text": "68.400 km"},
                                                             {"dok": "06", "text": "64.800 km"}]},
        {"id": "W3", "thema": "Kaufpreis", "aussagen": [{"dok": "01", "text": "14.900,00 €"},
                                                        {"dok": "04", "text": "14.990,00 €"}]},
    ]}), encoding="utf-8")
    monkeypatch.setattr(anbieter, "status", lambda e: {"bereit": True, "anbieter_titel": "Attrappe"})
    monkeypatch.setattr(anbieter, "erzeuge", lambda e: Modell())
    monkeypatch.setattr(anbieter, "denkt", lambda modell: 0)
    monkeypatch.chdir(tmp_path)
    e = anbieter.KiEinstellungen("ollama", "http://127.0.0.1:11434", "attrappe:1b")
    assert pruefen.main(ordner, e, erwartungen, False, mit_vergleich=True) == 0
    aus = capsys.readouterr().out
    assert "64.800 km  06_Klageerwiderung.md, Rn. 1 [Tachostand bei Auslieferung]" in aus
    assert "14.990,00 €  04_Ruecktritt.md, Abschn. 2 (Regel)" in aus and "[Tachostand bei Auslieferung]" in aus
    assert "Vom regelbasierten Abgleich gefunden: W3" in aus
    assert "Vom Vergleich mit KI (Zahlen und Daten) gefunden: W4, W3" in aus
    assert "Von keinem gefunden: keiner" in aus


def test_regel_abweichung_verschwindet_nicht(akten, con, tmp_path):
    """Trennt die KI Übergabe und Gefahrübergang, bleibt die Gegenüberstellung der Regeln mit Hinweis stehen."""
    from juracore.abgleich import abgleich as regeln

    a = akte.akte_anlegen(akten, "Urteil")["id"]
    pfad = tmp_path / "08_Urteil.md"
    pfad.write_text("Urteil\n\nDas Fahrzeug wurde am 18.03.2025 übergeben.\n\n"
                    "Seit dem Gefahrübergang am 21.03.2025 zeigte sich der Mangel.\n", encoding="utf-8")
    akte.importiere(akten, con, a, pfad, tmp_path / "ablage", ocr=False, tags=["Gericht"])
    _, angaben = regeln.angaben_der_akte(akten, a)
    assert [x["wert"] for x in angaben] == ["2025-03-18", "2025-03-21"]
    ki_teil = {"merkmale": [
        {"merkmal": f"ki:{i}", "titel": titel, "werte": [{"bezug": titel, "art": x["art"], "wert": x["wert"],
                                                          "haltung": "festgestellt", "fundstelle": x["fundstelle"]}]}
        for i, (titel, x) in enumerate(zip(["Datum der Übergabe", "Datum des Gefahrübergangs"], angaben,
                                           strict=True), 1)]}
    e = vergleich.zusammenfuehren(akten, a, None, ki_teil, {"widersprueche": []})
    regel = next(m for m in e["merkmale"] if m["merkmal"] == "regel:uebergabe")
    assert regel["status"] == "abweichend" and regel["quelle"] == "regel"
    assert "„Datum der Übergabe“; „Datum des Gefahrübergangs“" in regel["erklaerung"]
    assert [m["status"] for m in e["merkmale"] if m["quelle"] == "ki"] == ["einzeln", "einzeln"]


def test_eigene_gegendarstellung_ist_nicht_bestritten(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "KE")["id"]
    pfad = tmp_path / "06_Klageerwiderung.md"
    pfad.write_text("Klageerwiderung\n\n(2) Bestritten wird, dass die Klägerin den Mangel am 12.05.2025 angezeigt "
                    "hat. Die Klägerin hat sich erstmals Mitte Juni 2025 beschwert.\n", encoding="utf-8")
    d = akte.importiere(akten, con, a, pfad, tmp_path / "ablage", ocr=False, tags=["Beklagter"])["dokument_id"]

    class Gemma:
        modell = "gemma"

        def chat(self, system, nutzer, schema):
            nr = _nr(nutzer, "Bestritten")
            # Wie Gemma im Probelauf: beide Werte des Absatzes als bestritten.
            return {"werte": [
                {"wert": "12.05.2025", "bezug": "erste Mängelanzeige", "haltung": "bestritten", "absatz": nr,
                 "zitat": "dass die Klägerin den Mangel am 12.05.2025 angezeigt hat"},
                {"wert": "Mitte Juni 2025", "bezug": "erste Mängelanzeige", "haltung": "bestritten", "absatz": nr,
                 "zitat": "Die Klägerin hat sich erstmals Mitte Juni 2025 beschwert"},
            ]}

    w = vergleich.werte(Analyse(akten, Gemma()), d)
    assert [(x["wert"], x["haltung"]) for x in w["werte"]] == [("2025-06", "behauptet")]
    assert w["bestritten"] == 1


def test_verneinter_wert_mit_verneintem_bezug_zaehlt_nicht(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Urteil")["id"]
    pfad = tmp_path / "08_Urteil.md"
    pfad.write_text("Urteil\n\nEin Fehlerspeichereintrag P17BF ließ sich nicht feststellen; gespeichert war vielmehr "
                    "der Eintrag P189C.\n", encoding="utf-8")
    d = akte.importiere(akten, con, a, pfad, tmp_path / "ablage", ocr=False, tags=["Gericht"])["dokument_id"]

    class Gemma:
        modell = "gemma"

        def chat(self, system, nutzer, schema):
            nr = _nr(nutzer, "P17BF")
            return {"werte": [
                {"wert": "P17BF", "bezug": "Fehlerspeichereintrag (nicht vorhanden)", "haltung": "festgestellt",
                 "absatz": nr, "zitat": "Ein Fehlerspeichereintrag P17BF ließ sich nicht feststellen"},
                {"wert": "P189C", "bezug": "vorhandener Fehlerspeichereintrag", "haltung": "festgestellt",
                 "absatz": nr, "zitat": "gespeichert war vielmehr der Eintrag P189C"},
            ]}

    w = vergleich.werte(Analyse(akten, Gemma()), d)
    assert [x["wert"] for x in w["werte"]] == ["P189C"]
