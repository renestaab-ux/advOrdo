"""Sprachmodell-Anbindung: ohne echtes Modell, mit einer Attrappe und einem nachgebauten Ollama-Server.

Die Dokumente sind frei erfunden (angelehnt an die fiktive Testakte Brückner).
"""

import json
import re
import socket
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


# --- Lokal: dieses Gerät oder das eigene Netzwerk ------------------------------------------------


@pytest.mark.parametrize("endpunkt", ["http://localhost:11434", "http://127.0.0.1:11434/", "http://[::1]:1234",
                                      "https://127.0.0.2:8443", "http://192.168.1.20:11434", "http://10.0.0.5:1234",
                                      "http://172.20.1.2:1234", "http://[fd00::12]:1234", "http://gaming-pc:1234",
                                      "http://pc-buero.local:1234", "http://ki.fritz.box:11434"])
def test_lokale_endpunkte_sind_erlaubt(endpunkt):
    assert anbieter.pruefe_lokal(endpunkt) == endpunkt.rstrip("/")


@pytest.mark.parametrize("endpunkt", ["https://api.example.com", "http://localhost.evil.de", "http://8.8.8.8:1234",
                                      "http://172.32.0.1:1234", "http://100.64.1.1:1234", "http://0.0.0.0:1234",
                                      "http://224.0.0.1:1234", "http://[2001:db8::1]:1234", "ftp://127.0.0.1",
                                      "127.0.0.1:11434"])
def test_entfernte_endpunkte_werden_abgelehnt(endpunkt):
    with pytest.raises(ValueError):
        anbieter.pruefe_lokal(endpunkt)


@pytest.mark.parametrize(("endpunkt", "ort"), [
    ("http://127.0.0.1:1234", "geraet"), ("http://localhost:11434", "geraet"), ("http://[::1]:1234", "geraet"),
    ("http://192.168.178.20:1234", "netzwerk"), ("http://gaming-pc:1234", "netzwerk"),
    ("http://mac-mini.local:11434", "netzwerk")])
def test_endpunkt_ort(endpunkt, ort):
    assert anbieter.endpunkt_ort(endpunkt) == ort


def test_rechnername_muss_ins_eigene_netz_zeigen(monkeypatch):
    def aufloesen(adresse):
        return lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (adresse, 1234))]

    monkeypatch.setattr(socket, "getaddrinfo", aufloesen("192.168.178.20"))
    anbieter._pruefe_aufloesung("http://gaming-pc:1234")
    monkeypatch.setattr(socket, "getaddrinfo", aufloesen("203.0.113.7"))
    with pytest.raises(anbieter.KiFehler, match="außerhalb des eigenen Netzes"):
        anbieter._pruefe_aufloesung("http://gaming-pc:1234")
    with pytest.raises(anbieter.KiFehler, match="außerhalb des eigenen Netzes"):
        anbieter.Ollama("http://gaming-pc:1234", "m").modelle()


def test_modus_nennt_den_ort(tmp_path):
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    assert kern.ki_modus()["ort"] == "geraet"
    anbieter.speichere_einstellungen(kern.ki_datei, anbieter.KiEinstellungen("openai", "http://192.168.178.20:1234"))
    assert kern.ki_modus() == {"aus": False, "aktiv": "lokal", "titel": None, "modell": "",
                                "ort": "netzwerk"}


def test_ki_abschalten(tmp_path, monkeypatch):
    """Ausgeschaltet fragt die App kein Modell, prüft keine Verbindung und behält die übrigen Einstellungen."""
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    anbieter.speichere_einstellungen(kern.ki_datei, anbieter.KiEinstellungen("openai", "http://127.0.0.1:1234", "m"))

    def kein_netz(*_a, **_k):
        raise AssertionError("ausgeschaltet keine Verbindung")

    monkeypatch.setattr(anbieter, "erzeuge", kein_netz)
    kern.ki_fabrik = kein_netz
    stand = kern.ki_schalten(False)
    assert stand["abgeschaltet"] is True and stand["bereit"] is False
    assert stand["lokal"]["hinweis"] == anbieter.AUSGESCHALTET
    assert kern.ki_modus()["aus"] is True
    assert kern.ki_status()["abgeschaltet"] is True
    with pytest.raises(ValueError, match="ausgeschaltet"):
        kern.ki_starten("widersprueche", akte_id=1)
    with pytest.raises(ValueError, match="ausgeschaltet"):
        kern.ki_chat_fragen(1, "Frage?")
    assert kern.metadaten_ki(1) == {"status": "aus", "abgeschaltet": True}
    assert kern.ki_gegenueberstellung(1)["zitate"] == []

    e = anbieter.lade_einstellungen(kern.ki_datei)
    assert (e.abgeschaltet, e.anbieter, e.modell) == (True, "openai", "m")
    monkeypatch.undo()
    assert kern.ki_schalten(True)["abgeschaltet"] is False
    assert kern.ki_modus()["aus"] is False


def test_einstellungen_speichern_und_laden(tmp_path):
    pfad = tmp_path / "ki.json"
    assert anbieter.lade_einstellungen(pfad).anbieter == "ollama"
    anbieter.speichere_einstellungen(pfad, anbieter.KiEinstellungen("ollama", "http://localhost:11434", "qwen3:14b"))
    assert anbieter.lade_einstellungen(pfad).modell == "qwen3:14b"
    with pytest.raises(ValueError):
        anbieter.speichere_einstellungen(pfad, anbieter.KiEinstellungen("ollama", "http://203.0.113.5:11434", "x"))
    # Eine von Hand auf eine fremde Adresse geänderte Datei fällt auf die Voreinstellung zurück.
    pfad.write_text(json.dumps({"endpunkt": "http://203.0.113.5:11434", "modell": "x"}), encoding="utf-8")
    assert anbieter.lade_einstellungen(pfad).endpunkt == "http://127.0.0.1:11434"


def test_antwort_mit_denkabschnitt_und_codezaun():
    assert anbieter.lies_json('<think>hm</think>\n```json\n{"a": 1}\n```') == {"a": 1}
    assert anbieter.lies_json('Hier: {"a": [1]} fertig') == {"a": [1]}
    for text, abgeschnitten, meldung in (("", False, "leer"), ('{"angaben": [{"text": "x', False, "mitten im JSON"),
                                         ('{"a": 1}', True, "abgeschnitten")):
        with pytest.raises(anbieter.KiFehler, match=meldung):
            anbieter.lies_json(text, abgeschnitten)
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


def test_unbrauchbarer_teil_bricht_nicht_ab(akten, con, tmp_path):
    akte_id, _ = _akte(akten, con, tmp_path)

    def antwort(prompt, schema):
        if "widersprueche" in schema["properties"] or "ereignisse" in schema["properties"]:
            raise anbieter.KiFehler("Die Antwort des Modells ist kein JSON.")
        return modell_antwort(prompt, schema)

    modell = Attrappe(antwort)
    ergebnis = Analyse(akten, modell).widersprueche(akte_id)
    # Beide Versuche unbrauchbar: Der Teil fehlt, der Lauf geht weiter, das Ergebnis wird nicht gespeichert.
    assert ergebnis["luecken"] == [1] and ergebnis["teile"] == 1 and ergebnis["widersprueche"] == []
    assert ergebnis["gespeichert"] is False
    chrono = Analyse(akten, modell).chronologie(akte_id)
    assert chrono["luecken"] == [1] and chrono["gespeichert"] is False

    modell.antwort = modell_antwort
    zweiter = Analyse(akten, modell).widersprueche(akte_id)
    assert zweiter["luecken"] == [] and len(zweiter["widersprueche"]) == 2 and zweiter["gespeichert"] is False
    assert Analyse(akten, modell).widersprueche(akte_id)["gespeichert"] is True


def test_abgeschnittene_angaben_werden_in_kleineren_stuecken_erfragt(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Lang")
    pfad = tmp_path / "lang.md"
    pfad.write_text("\n\n".join(f"({i}) Absatz {i}: Die Klägerin trägt vor." for i in range(1, 5)), encoding="utf-8")
    d = akte.importiere(akten, con, a["id"], pfad, tmp_path / "ablage", ocr=False)["dokument_id"]

    def antwort(prompt, schema):
        # Mehr als zwei Absätze auf einmal sind dem Modell zu lang, Absatz 4 gelingt nie.
        absaetze = re.findall(r"^\[(\d+)\] ", prompt, re.M)
        if len(absaetze) > 2 or "4" in absaetze:
            raise anbieter.KiFehler("Die Antwort des Modells ist abgeschnitten (Längengrenze erreicht), kein JSON.")
        return {"angaben": [{"text": f"Angabe {n}.", "haltung": "behauptet", "absatz": int(n),
                             "zitat": f"Absatz {n}: Die Klägerin trägt vor."} for n in absaetze]}

    modell = Attrappe(antwort)
    ergebnis = Analyse(akten, modell).angaben(d)
    # Abgeschnitten wird nicht wörtlich wiederholt, sondern halbiert: 1–4, 1–2, 3–4, 3, 4.
    assert len(modell.anfragen) == 5
    assert [x["text"] for x in ergebnis["angaben"]] == ["Angabe 1.", "Angabe 2.", "Angabe 3."]
    assert ergebnis["luecken"] == ["4"] and ergebnis["gespeichert"] is False
    assert "(Absätze 3 bis 4)" in modell.anfragen[2]


def test_abgeschnitten_nennt_denkphase():
    with pytest.raises(anbieter.KiFehler, match="Denkphase 5000 Zeichen, Antwort 8 Zeichen"):
        anbieter.lies_json('{"a": [1', True, 5000)


def test_nicht_erreichbar_bricht_weiter_ab(akten, con, tmp_path):
    akte_id, _ = _akte(akten, con, tmp_path)

    def antwort(prompt, schema):
        if "widersprueche" in schema["properties"]:
            raise anbieter.KiFehler("Das Sprachmodell ist nicht erreichbar.")
        return modell_antwort(prompt, schema)

    with pytest.raises(anbieter.KiFehler):
        Analyse(akten, Attrappe(antwort)).widersprueche(akte_id)


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
    with pytest.raises(RuntimeError, match="anderen Auftrag"):
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
    kern.ki_fabrik = lambda e, schluessel=None: Attrappe(modell_antwort)
    akte_id, _ = _akte(kern.akten, con, tmp_path)

    def aufruf(methode, **params):
        antwort = kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))
        assert "error" not in antwort, antwort
        return antwort["result"]

    fehler = kern.bearbeite(json.dumps({"id": 2, "method": "ki.starten", "params": {"aufgabe": "widersprueche",
                                                                                     "akte_id": akte_id}}))
    assert "Kein Sprachmodell gewählt" in fehler["error"]["message"]
    fehler = kern.bearbeite(json.dumps({"id": 3, "method": "ki.einstellungen_setzen", "params": {
        "anbieter": "ollama", "endpunkt": "http://203.0.113.9:11434", "modell": "x"}}))
    assert "eigenen Netzwerk" in fehler["error"]["message"]

    # Ein Port, an dem nichts läuft: Status meldet „nicht erreichbar“, speichert aber die Wahl.
    stand = aufruf("ki.einstellungen_setzen", anbieter="ollama", endpunkt="http://127.0.0.1:9", modell=Attrappe.modell)
    assert stand["lokal"]["erreichbar"] is False and "nicht erreichbar" in stand["hinweis"]

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
            self._antworte(200, {"choices": [{"message": {"content": '{"aussagen": [{"text": "x"}]}',
                                                          "reasoning_content": "Hm, ich überlege."}}]})


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
    assert gesendet["options"] == {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 8192}

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
    assert gesendet["max_tokens"] == 8192
    assert gesendet["chat_template_kwargs"] == {"enable_thinking": False}
    # Die Denkphase wird erkannt, damit der Probelauf davor warnen kann.
    assert anbieter.denkt(anbieter.erzeuge(e)) == len("Hm, ich überlege.")


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


def test_gleicher_streitpunkt_wird_ein_eintrag():
    from juracore.ki.analyse import _fasse_zusammen, _ohne_kennungen

    treffer = [
        {"nummern": {1, 2}, "thema": "Telefonat", "art": "spannung", "erklaerung": "Eins."},
        {"nummern": {5, 6}, "thema": "Wohnwagen", "art": "spannung", "erklaerung": "Zwei."},
        {"nummern": {2, 3}, "thema": "Angebot", "art": "widerspruch", "erklaerung": "Drei."},
        {"nummern": {3, 4}, "thema": "Ablehnung", "art": "spannung", "erklaerung": "Eins."},
    ]
    gruppen = _fasse_zusammen(treffer)
    assert [(g["thema"], g["nummern"], g["art"]) for g in gruppen] == [
        ("Wohnwagen", {5, 6}, "spannung"), ("Telefonat", {1, 2, 3, 4}, "widerspruch")]
    assert gruppen[1]["erklaerung"] == "Eins. Drei."

    alle = [{"fundstelle": {"dateiname": "03_Antwort.pdf"}}, {"fundstelle": {"dateiname": "06_Erwiderung.pdf"}}]
    assert _ohne_kennungen("68.400 km in A1 gegenüber [A2], nicht A9", alle) == (
        "68.400 km in 03_Antwort gegenüber 06_Erwiderung, nicht A9")


def test_angaben_auch_bei_grossem_kontext_in_stuecken(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Lang")
    pfad = tmp_path / "lang.md"
    pfad.write_text("\n\n".join(f"({i}) Absatz {i}: " + "Die Klägerin trägt ausführlich vor. " * 25
                                for i in range(1, 41)), encoding="utf-8")
    d = akte.importiere(akten, con, a["id"], pfad, tmp_path / "ablage", ocr=False)["dokument_id"]
    modell = Attrappe(lambda prompt, schema: {"angaben": []})
    Analyse(akten, modell, kontext=32768).angaben(d)
    # Rund 37.000 Zeichen: bei 32.768 Token passten sie in eine Anfrage, für die Angaben werden es aber Stücke.
    assert len(modell.anfragen) == 4
    assert all(len(p) < 13500 for p in modell.anfragen)


# --- Chronologie ----------------------------------------------------------------------------------

REPLIK = """Replik

Freiburg, den 15.01.2026

(25) Ein Telefonat am 02.07.2025 hat nicht stattgefunden.
"""


def chronologie_antwort(prompt: str, schema: dict) -> dict:
    if "widersprueche" in schema["properties"]:
        return {"widersprueche": []}
    if "ereignisse" in schema["properties"]:
        untersuchung, angebot = kennung(prompt, "am 27.06.2025"), kennung(prompt, "bot am 02.07.2025")
        replik = re.search(r"^\[(D\d+)\] 07_Replik", prompt, re.M).group(1)
        kauf = re.search(r"^\[(D\d+)\] 01_Kaufvertrag", prompt, re.M).group(1)
        return {
            "ereignisse": [
                {"datum": "27.06.2025", "art": "ereignis", "ereignis": "Untersuchung beim Autohaus",
                 "streitig": False, "angaben": [untersuchung]},
                # Bestritten wird es in der Replik; streitig ergibt sich aus der Haltung, auch wenn das Modell es übersieht.
                {"datum": "02.07.2025", "art": "ereignis", "ereignis": "Telefonisches Nachbesserungsangebot",
                 "streitig": False, "angaben": [angebot, kennung(prompt, "nicht stattgefunden")]},
                {"datum": "05.07.2025", "art": "frist", "ereignis": "Erfundenes Datum", "streitig": False,
                 "angaben": [angebot]},
                {"datum": "irgendwann", "art": "ereignis", "ereignis": "Ohne Datum", "streitig": False,
                 "angaben": [angebot]},
                {"datum": "01.01.2025", "art": "ereignis", "ereignis": "Erfundene Kennung", "streitig": False,
                 "angaben": ["A99"]},
                {"datum": "27.06.2025", "art": "ereignis", "ereignis": "Doppelt", "streitig": False,
                 "angaben": [f"[{untersuchung}]"]},
            ],
            "dokumente": [
                {"kennung": replik, "bezeichnung": "Replik", "datum": "15.01.2026"},
                {"kennung": kauf, "bezeichnung": "Kaufvertrag", "datum": "14.03.2025"},  # steht nicht im Kopf
            ],
        }
    kopfzeile = prompt.split("\n", 1)[0]
    if "07_Replik" in kopfzeile:
        return {"angaben": [{"text": "Ein Telefonat am 02.07.2025 hat nicht stattgefunden.", "haltung": "bestritten",
                             "absatz": absatz(prompt, "nicht stattgefunden"),
                             "zitat": "Ein Telefonat am 02.07.2025 hat nicht stattgefunden."}]}
    antwort = angaben_antwort(prompt)
    if "Antwortschreiben" in kopfzeile:
        antwort["angaben"].append({"text": "Das Autohaus untersuchte das Fahrzeug am 27.06.2025.",
                                   "haltung": "behauptet", "absatz": absatz(prompt, "Augenschein"),
                                   "zitat": "wir haben das Fahrzeug am 27.06.2025 kurz in Augenschein genommen"})
    return antwort


def test_chronologie_mit_belegtem_datum(akten, con, tmp_path):
    akte_id, ids = _akte(akten, con, tmp_path)
    pfad = tmp_path / "07_Replik.md"
    pfad.write_text(REPLIK, encoding="utf-8")
    ids["07"] = akte.importiere(akten, con, akte_id, pfad, tmp_path / "ablage", ocr=False, tags=["Kläger"])["dokument_id"]
    modell = Attrappe(chronologie_antwort)
    ergebnis = Analyse(akten, modell).chronologie(akte_id)

    zeilen = [(e["anzeige"], e["art"], e["ereignis"], e["status"], e["streitig"]) for e in ergebnis["ereignisse"]]
    assert zeilen == [
        ("27.06.2025", "ereignis", "Untersuchung beim Autohaus", "belegt", False),
        ("02.07.2025", "ereignis", "Telefonisches Nachbesserungsangebot", "belegt", True),
        ("05.07.2025", "frist", "Erfundenes Datum", "ohne_beleg", False),
        ("15.01.2026", "dokument", "Replik", "belegt", False),
    ]
    assert ergebnis["verworfen"] == 3  # ohne Datum, erfundene Kennung, Datum nicht im Kopf des Kaufvertrags
    assert ergebnis["angaben"] == 3  # nur datierte Angaben
    angebot = ergebnis["ereignisse"][1]
    assert [q["fundstelle"]["dokument_id"] for q in angebot["quellen"]] == [ids["06"], ids["07"]]
    replik = ergebnis["ereignisse"][3]["quellen"][0]["fundstelle"]
    assert replik["ausschnitt"]["wert"] == "15.01.2026" and replik["dokument_id"] == ids["07"]

    # Die Tatsachenangaben teilt die Chronologie mit der Widerspruchssuche: keine neuen Anfragen dafür.
    anzahl = len(modell.anfragen)
    Analyse(akten, modell).widersprueche(akte_id)
    assert len(modell.anfragen) == anzahl + 1
    assert speicher.ergebnisse(akten, akte_id, modell.modell)["chronologie"]["ereignisse"][0]["datum"] == "2025-06-27"


def test_chronologie_teilt_abgeschnittene_antwort(akten, con, tmp_path):
    """Abgeschnittene Antwort: der Block wird halbiert, bis jede Hälfte eine vollständige Antwort bekommt."""
    akte_id, ids = _akte(akten, con, tmp_path)
    pfad = tmp_path / "07_Replik.md"
    pfad.write_text(REPLIK, encoding="utf-8")
    akte.importiere(akten, con, akte_id, pfad, tmp_path / "ablage", ocr=False, tags=["Kläger"])

    def antwort(prompt: str, schema: dict) -> dict:
        if "ereignisse" not in schema["properties"]:
            return chronologie_antwort(prompt, schema)
        zeilen = re.findall(r"^\[(A\d+)\] .*?(\d\d\.\d\d\.\d{4})", prompt, re.M)
        if len(zeilen) > 1:
            raise anbieter.KiFehler("Antwort abgeschnitten (Längengrenze erreicht), kein vollständiges JSON.")
        return {"ereignisse": [{"datum": d, "art": "ereignis", "ereignis": f"Ereignis {k}", "streitig": False,
                                "angaben": [k]} for k, d in zeilen], "dokumente": []}

    modell = Attrappe(antwort)
    ergebnis = Analyse(akten, modell).chronologie(akte_id)
    assert ergebnis["luecken"] == [] and not ergebnis["unvollstaendig"]
    assert ergebnis["teile"] == 3 == ergebnis["angaben"]
    assert {e["anzeige"] for e in ergebnis["ereignisse"]} == {"02.07.2025", "27.06.2025"}
    assert all(e["status"] == "belegt" for e in ergebnis["ereignisse"])


def test_kopf_reicht_bis_ort_und_datum_vor_den_unterschriften(akten, con, tmp_path):
    from juracore.ki import chronologie

    a = akte.akte_anlegen(akten, "Kopf")
    pfad = tmp_path / "vertrag.md"
    pfad.write_text("\n\n".join(["Kaufvertrag"] + [f"§ {i} " + "Regelung. " * 40 for i in range(1, 6)] + [
        "Denzlingen, den 14.03.2025", "gez. Markus Rehnfeld, Autohaus Rehnfeld GmbH", "gez. Dr. Lena Brückner",
        "(Anlage K1 zur Klageschrift vom 20.10.2025)", "Fiktives Testdokument."]), encoding="utf-8")
    d = akte.importiere(akten, con, a["id"], pfad, tmp_path / "ablage", ocr=False)["dokument_id"]
    texte = [x["text"] for x in chronologie.kopf(belege.lade_text(akten, d, ()))]
    assert "Denzlingen, den 14.03.2025" in texte and not any(t.startswith("§ 4") for t in texte)


def test_chronologie_monat_wie_im_dokument():
    from juracore.ki.chronologie import _anzeige, im_text, lies_datum

    monat = lies_datum("Juni 2025")
    treffer = im_text(monat, "Sie beschwerte sich erstmals Mitte Juni 2025.")
    text = "Sie beschwerte sich erstmals Mitte Juni 2025."
    assert _anzeige(monat, text[treffer.start:treffer.ende]) == "Mitte Juni 2025"
    assert im_text(monat, "am 12.06.2025") is not None and im_text(monat, "am 12.07.2025") is None
    assert im_text(lies_datum("12.05.2025"), "Mai 2025") is None


def test_probelauf_mit_chronologie(tmp_path, monkeypatch, capsys):
    from juracore.ki import pruefen

    ordner = tmp_path / "Akte"
    (ordner / "Kläger").mkdir(parents=True)
    (ordner / "Beklagter").mkdir()
    (ordner / "Kläger" / "01_Kaufvertrag.md").write_text(KAUFVERTRAG, encoding="utf-8")
    (ordner / "Beklagter" / "03_Antwortschreiben.md").write_text(ANTWORTSCHREIBEN, encoding="utf-8")
    (ordner / "Beklagter" / "06_Klageerwiderung.md").write_text(KLAGEERWIDERUNG, encoding="utf-8")
    (ordner / "Kläger" / "07_Replik.md").write_text(REPLIK, encoding="utf-8")
    erwartungen = tmp_path / "erwartungen.json"
    erwartungen.write_text(json.dumps({"widersprueche": [], "chronologie": [
        {"datum": "2025-06-27", "ereignis": "Untersuchung", "dok": ["03"]},
        {"datum": "2026-01-15", "ereignis": "Replik", "dok": ["07"]},
        {"datum": "2025-07-15", "ereignis": "Rücktritt", "dok": ["04"]},
    ]}), encoding="utf-8")
    monkeypatch.setattr(anbieter, "status", lambda e: {"bereit": True, "anbieter_titel": "Attrappe"})
    monkeypatch.setattr(anbieter, "erzeuge", lambda e: Attrappe(chronologie_antwort))
    monkeypatch.setattr(anbieter, "denkt", lambda modell: 0)
    monkeypatch.chdir(tmp_path)

    e = anbieter.KiEinstellungen("ollama", "http://127.0.0.1:11434", "attrappe:1b")
    assert pruefen.main(ordner, e, erwartungen, False, chronologie=True) == 0
    aus = capsys.readouterr().out
    assert "Telefonisches Nachbesserungsangebot (streitig)" in aus
    assert "Erfundenes Datum (Datum ohne Beleg)" in aus
    assert "Chronologie: 2 von 3 erwarteten Ereignissen gefunden" in aus

    # Zweiter Lauf auf unveränderter Testakte: nichts wird neu eingelesen oder neu gefragt.
    modell = Attrappe(chronologie_antwort)
    monkeypatch.setattr(anbieter, "erzeuge", lambda e: modell)
    assert pruefen.main(ordner, e, erwartungen, False, chronologie=True) == 0
    assert modell.anfragen == []
    assert "Lese " not in capsys.readouterr().err
    assert "fehlt: 2025-07-15 Rücktritt (04)" in aus
    protokoll = json.loads((tmp_path / "ki-pruefen-protokoll.json").read_text(encoding="utf-8"))
    assert len(protokoll["chronologie"]["ereignisse"]) == 4


def test_chronologie_monat_steht_an_seiner_stelle_im_monat():
    from juracore.ki.chronologie import sortiere

    def e(datum, anzeige, art="ereignis"):
        return {"datum": datum, "anzeige": anzeige, "art": art}

    reihe = sortiere([e("2026-02", "Ende Februar 2026"), e("2026-02-28", "28.02.2026"), e("2026-02-02", "02.02.2026"),
                      e("2026-02", "Mitte Februar 2026"), e("2026-02", "Februar 2026"), e("2026-03-01", "01.03.2026"),
                      e("2026-02-15", "15.02.2026", "frist"), e("2026-02-14", "14.02.2026")])
    assert [x["anzeige"] for x in reihe] == ["Februar 2026", "02.02.2026", "14.02.2026", "Mitte Februar 2026",
                                             "15.02.2026", "28.02.2026", "Ende Februar 2026", "01.03.2026"]


def test_gespeicherte_chronologie_wird_neu_geordnet(akten):
    speicher.einrichten(akten)
    a = akte.akte_anlegen(akten, "Akte")
    speicher.schreibe(akten, "k", "chronologie", "m", {"ereignisse": [
        {"datum": "2026-02", "anzeige": "Ende Februar 2026", "art": "ereignis"},
        {"datum": "2026-02-02", "anzeige": "02.02.2026", "art": "ereignis"}]}, akte_id=a["id"])
    c = speicher.ergebnisse(akten, a["id"], "m")["chronologie"]
    assert [x["anzeige"] for x in c["ereignisse"]] == ["02.02.2026", "Ende Februar 2026"]
