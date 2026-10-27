"""Metadaten je Dokument (Ansicht „Details“): Vorschläge mit Fundstelle, Speichern, Verlauf.

Die Texte stammen aus der fiktiven Testakte „Brückner ./. Weber Haustechnik GmbH“.
"""

import pytest

from juracore.aktenverwaltung import beteiligte, einrichten, stammdaten
from juracore.dokumente import akte, metadaten
from juracore.eigene import daten as eigene
from juracore.rpc import Kern

VERFUEGUNG = [
    "Landgericht Freiburg im Breisgau",
    "2. Zivilkammer",
    "Salzstraße 17, 79098 Freiburg im Breisgau",
    "Aktenzeichen: 2 O 233/26",
    "Freiburg, 27.08.2026",
    "In dem Rechtsstreit",
    "Dr. Lena Brückner ./. Weber Haustechnik GmbH",
    "Verfügung",
    "1. Die Anspruchsbegründung vom 20.08.2026 ist der Beklagten zuzustellen.",
]
SCHREIBEN = [
    "Albrecht Tiedemann Rechtsanwälte",
    "Kaiser-Joseph-Straße 300 · 79098 Freiburg im Breisgau",
    "Weber Haustechnik GmbH",
    "Elzstraße 21",
    "79312 Emmendingen",
    "Freiburg, den 23.06.2026",
    "Betreff: Brückner ./. Weber Haustechnik GmbH – Heizungsanlage, Rechnung vom 02.05.2026",
    "Sehr geehrter Herr Weber,",
    "wir zeigen an, dass uns Frau Dr. Brückner mit der Wahrnehmung ihrer Interessen beauftragt hat.",
]


@pytest.fixture
def akten(tmp_path):
    verbindung = akte.oeffne(tmp_path / "akten.sqlite")
    eigene.einrichten(verbindung)
    einrichten(verbindung)
    yield verbindung
    verbindung.close()


def _dokument(akten, wissen, tmp_path, name, zeilen, akte_id=None):
    if akte_id is None:
        akte_id = akte.akte_anlegen(akten, "Brückner ./. Weber")["id"]
    datei = tmp_path / name
    datei.write_text("\n\n".join(zeilen), encoding="utf-8")
    return akte_id, akte.importiere(akten, wissen, akte_id, datei, tmp_path / "ablage", ocr=False)["dokument_id"]


def _beteiligte(akten, akte_id):
    lena = beteiligte.speichern(akten, "person", {"vorname": "Lena", "nachname": "Brückner", "titel": "Dr."})
    weber = beteiligte.speichern(akten, "organisation", {"name": "Weber Haustechnik GmbH"})
    gericht = beteiligte.speichern(akten, "organisation", {"name": "Landgericht Freiburg im Breisgau"})
    stammdaten.beteiligung_hinzufuegen(akten, akte_id, "mandant", beteiligter_id=lena["id"])
    stammdaten.beteiligung_hinzufuegen(akten, akte_id, "gegner", beteiligter_id=weber["id"])
    stammdaten.beteiligung_hinzufuegen(akten, akte_id, "gericht", beteiligter_id=gericht["id"])
    return {b["name"]: b["id"] for b in stammdaten.beteiligungen(akten, akte_id)}


def test_vorschlaege_aus_verfuegung(akten, con, tmp_path):
    akte_id, dok = _dokument(akten, con, tmp_path, "verfuegung.txt", VERFUEGUNG)
    ids = _beteiligte(akten, akte_id)
    m = metadaten.lesen(akten, dok)
    assert m["titel"] == "" and m["dateiname"] == "verfuegung.txt"
    titel = m["vorschlaege"]["titel"][0]
    assert titel["wert"] == "Verfügung LG Freiburg im Breisgau"
    assert titel["fundstelle"]["abschnitt"] == 8
    assert {v["wert"] for v in m["vorschlaege"]["schlagworte"]} == {"Gericht"}
    vorgeschlagen = {v["beteiligung_id"]: v for v in m["vorschlaege"]["beteiligte"]}
    assert set(vorgeschlagen) == set(ids.values())
    assert vorgeschlagen[ids["Landgericht Freiburg im Breisgau"]]["grund"] == "im Kopf des Dokuments als Gericht"
    # Nichts ist ohne Bestätigung eingetragen.
    assert m["beteiligte"] == [] and m["schlagworte"] == []
    assert m["datum"]["wert"] == "2026-08-27" and m["datum"]["quelle"] == "dokument"


def test_vorschlaege_aus_schreiben(akten, con, tmp_path):
    akte_id, dok = _dokument(akten, con, tmp_path, "schreiben.txt", SCHREIBEN)
    ids = _beteiligte(akten, akte_id)
    m = metadaten.lesen(akten, dok)
    assert m["vorschlaege"]["titel"][0]["grund"] == "Betreffzeile"
    assert m["vorschlaege"]["titel"][0]["wert"].startswith("Brückner ./. Weber Haustechnik GmbH – Heizungsanlage")
    vorgeschlagen = {v["beteiligung_id"]: v for v in m["vorschlaege"]["beteiligte"]}
    assert vorgeschlagen[ids["Weber Haustechnik GmbH"]]["grund"] == "im Kurzrubrum genannt"
    # „Frau Dr. Brückner“ im Text findet die Mandantin über den Nachnamen.
    assert vorgeschlagen[ids["Dr. Lena Brückner"]]["fundstelle"]["abschnitt"] in (7, 9)
    assert ids["Landgericht Freiburg im Breisgau"] not in vorgeschlagen


def test_speichern_und_verlauf(akten, con, tmp_path):
    akte_id, dok = _dokument(akten, con, tmp_path, "verfuegung.txt", VERFUEGUNG)
    ids = _beteiligte(akten, akte_id)
    m = metadaten.speichern(akten, dok, titel="  Verfügung   Termin ", schlagworte=["Gericht", "Termin"],
                            beteiligte_ids=[ids["Landgericht Freiburg im Breisgau"]])
    assert m["titel"] == "Verfügung Termin"
    assert [b["name"] for b in m["beteiligte"]] == ["Landgericht Freiburg im Breisgau"]
    assert {t["name"] for t in m["schlagworte"]} == {"Gericht", "Termin"}
    # Übernommene Vorschläge erscheinen nicht noch einmal.
    assert ids["Landgericht Freiburg im Breisgau"] not in {v["beteiligung_id"] for v in m["vorschlaege"]["beteiligte"]}
    assert m["vorschlaege"]["schlagworte"] == []
    felder = [e["feld"] for e in m["verlauf"] if e["art"] == "aenderung"]
    assert sorted(felder) == ["beteiligte", "schlagworte", "titel"]
    titel = next(e for e in m["verlauf"] if e.get("feld") == "titel")
    assert titel["alt"] is None and titel["neu"] == "Verfügung Termin"
    assert m["verlauf"][-1]["art"] == "fassung" and m["verlauf"][-1]["nr"] == 1
    # Unveränderte Werte erzeugen keinen Eintrag; der Titel steht auch in der Dokumentliste.
    m = metadaten.speichern(akten, dok, titel="Verfügung Termin", schlagworte=["Termin", "Gericht"])
    assert len([e for e in m["verlauf"] if e["art"] == "aenderung"]) == 3
    assert akte.dokumente(akten, akte_id)[0]["titel"] == "Verfügung Termin"
    # Beteiligte einer anderen Akte werden abgelehnt.
    with pytest.raises(ValueError):
        metadaten.speichern(akten, dok, beteiligte_ids=[9999])


def test_datum_von_hand_und_zurueck(akten, con, tmp_path):
    akte_id, dok = _dokument(akten, con, tmp_path, "verfuegung.txt", VERFUEGUNG)
    _beteiligte(akten, akte_id)
    m = metadaten.speichern(akten, dok, datum="2026-08-28")
    assert m["datum"]["wert"] == "2026-08-28" and m["datum"]["quelle"] == "manuell"
    assert m["datum"]["erkannt"]["datum"] == "2026-08-27"
    assert m["vorschlaege"]["datum"]["wert"] == "2026-08-27"
    assert m["vorschlaege"]["datum"]["fundstelle"]["text"] == "Freiburg, 27.08.2026"
    with pytest.raises(ValueError):
        metadaten.speichern(akten, dok, datum="28.08.2026")
    # Das Datum von Hand bleibt, wenn der Text neu gespeichert wird (z. B. neue Fassung).
    with akten:
        akte._datum_speichern(akten, dok, {"datum": "2026-08-29", "quelle": "dokument", "abschnitt": 5, "seite": None,
                                          "text": "Freiburg, 29.08.2026", "gespeichert": None,
                                          "gespeichert_quelle": None})
    m = metadaten.lesen(akten, dok)
    assert m["datum"]["wert"] == "2026-08-28" and m["vorschlaege"]["datum"]["wert"] == "2026-08-29"
    m = metadaten.speichern(akten, dok, datum="")
    assert m["datum"]["wert"] == "2026-08-29" and m["datum"]["quelle"] == "dokument"
    assert m["datum"]["erkannt"] is None and m["vorschlaege"]["datum"] is None
    datum = [(e["alt"], e["neu"]) for e in m["verlauf"] if e.get("feld") == "datum"]
    assert datum == [("2026-08-28", "2026-08-29"), ("2026-08-27", "2026-08-28")]


def test_beteiligte_verschwinden_mit_der_beteiligung(akten, con, tmp_path):
    akte_id, dok = _dokument(akten, con, tmp_path, "verfuegung.txt", VERFUEGUNG)
    ids = _beteiligte(akten, akte_id)
    metadaten.speichern(akten, dok, beteiligte_ids=list(ids.values()))
    stammdaten.beteiligung_entfernen(akten, ids["Weber Haustechnik GmbH"])
    assert {b["name"] for b in metadaten.lesen(akten, dok)["beteiligte"]} == {
        "Dr. Lena Brückner", "Landgericht Freiburg im Breisgau"}


def test_metadaten_ueber_kern(tmp_path):
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    a = kern.methoden["akten.anlegen"](name="Brückner ./. Weber")
    datei = tmp_path / "verfuegung.txt"
    datei.write_text("\n\n".join(VERFUEGUNG), encoding="utf-8")
    dok = kern.methoden["akten.importieren"](akte_id=a["id"], pfad=str(datei))["dokument_id"]
    m = kern.methoden["akten.metadaten_speichern"](dokument_id=dok, titel="Terminsverfügung", datum="2026-08-27")
    assert m["titel"] == "Terminsverfügung" and m["datum"]["quelle"] == "manuell"
    assert kern.methoden["akten.metadaten"](dokument_id=dok)["titel"] == "Terminsverfügung"


def test_art_und_absender(akten, con, tmp_path):
    akte_id, dok = _dokument(akten, con, tmp_path, "verfuegung.txt", VERFUEGUNG)
    ids = _beteiligte(akten, akte_id)
    m = metadaten.lesen(akten, dok)
    assert m["art"] == "" and m["absender"] is None and "Schriftsatz" in m["arten"]
    assert m["vorschlaege"]["art"]["wert"] == "Verfügung"
    absender = m["vorschlaege"]["absender"]
    assert absender["wert"] == ids["Landgericht Freiburg im Breisgau"]
    assert absender["grund"] == "vom Landgericht Freiburg im Breisgau erlassen"

    m = metadaten.speichern(akten, dok, art="Verfügung", absender=absender["wert"])
    assert m["art"] == "Verfügung" and m["absender"]["name"] == "Landgericht Freiburg im Breisgau"
    assert m["vorschlaege"]["art"] is None and m["vorschlaege"]["absender"] is None
    m = metadaten.speichern(akten, dok, absender="eigene")
    assert m["absender"]["wert"] == "eigene"
    verlauf = [(e["alt"], e["neu"]) for e in m["verlauf"] if e.get("feld") == "absender"]
    assert verlauf[0] == ("Landgericht Freiburg im Breisgau (Gericht)", "Wir (eigene Seite)")
    with pytest.raises(ValueError):
        metadaten.speichern(akten, dok, absender=9999)
    assert metadaten.speichern(akten, dok, absender="")["absender"] is None


def test_absender_eigene_kanzlei_im_briefkopf(akten, con, tmp_path):
    akte_id, dok = _dokument(akten, con, tmp_path, "schreiben.txt", SCHREIBEN)
    _beteiligte(akten, akte_id)
    m = metadaten.lesen(akten, dok, ["Albrecht Tiedemann Rechtsanwälte"])
    assert m["vorschlaege"]["art"]["wert"] == "Schreiben"
    assert m["vorschlaege"]["absender"]["wert"] == "eigene"
    assert m["vorschlaege"]["absender"]["fundstelle"]["abschnitt"] == 1
    # Ohne Eigene Daten kein Vorschlag „Wir“; der Gegner steht nur in der Anschrift, nicht als Absender.
    assert metadaten.lesen(akten, dok)["vorschlaege"]["absender"] is None


def test_bezugszeile_ist_kein_titel(akten, con, tmp_path):
    zeilen = ["Albrecht Tiedemann Rechtsanwälte", "Dr. Lena Brückner",
              "UNSER ZEICHEN 3/26 RS | IHR ZEICHEN | AKTE Brückner ./. Autohaus Rehnfeld GmbH",
              "Rückabwicklung eines Kaufvertrags Brückner ./. Autohaus Rehnfeld GmbH", "Sehr geehrte Frau Dr. Brückner,"]
    _, dok = _dokument(akten, con, tmp_path, "brief.txt", zeilen)
    titel = [t["wert"] for t in metadaten.lesen(akten, dok)["vorschlaege"]["titel"]]
    assert titel == ["Rückabwicklung eines Kaufvertrags Brückner ./. Autohaus Rehnfeld GmbH"]


def test_absender_in_der_dokumentliste(tmp_path):
    kern = Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")
    a = kern.methoden["akten.anlegen"](name="Brückner ./. Weber")
    datei = tmp_path / "verfuegung.txt"
    datei.write_text("\n\n".join(VERFUEGUNG), encoding="utf-8")
    dok = kern.methoden["akten.importieren"](akte_id=a["id"], pfad=str(datei))["dokument_id"]
    assert kern.methoden["akten.dokumente"](akte_id=a["id"])[0]["absender"] is None
    kern.methoden["akten.metadaten_speichern"](dokument_id=dok, absender="eigene", art="Schreiben")
    d = kern.methoden["akten.dokumente"](akte_id=a["id"])[0]
    assert d["absender"]["wert"] == "eigene" and d["art"] == "Schreiben"
