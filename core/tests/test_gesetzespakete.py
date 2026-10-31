"""Gesetzespakete (Zivil-, Straf-, Verwaltungsrecht, Landesrecht Bayern) und der Leser für gesetze-bayern.de.

Der HTML-Auszug ist nachgebildet: Aufbau nach der Gesamtansicht auf gesetze-bayern.de, wie sie im
Browser erscheint (Kopf mit „Text gilt ab“ und Vollzitat, Inhaltsübersicht als Verweise, Artikel mit
Überschrift in der Zeile darunter, hochgestellte Satznummern). Die genaue Auszeichnung der echten Seite
war aus der Arbeitsumgebung nicht abrufbar; der Leser hängt deshalb nicht an Klassennamen.
"""

import io
import json
import urllib.error

import pytest

from juracore.gesetze import bayern, quelle, wissensbasis
from juracore.rpc import Kern

from .conftest import FIXTURES

SEITE = (FIXTURES / "bayern_gesetz_auszug.html").read_bytes()


# --- Pakete ---------------------------------------------------------------------------------------


def test_pakete_der_voreinstellung():
    pakete = {p["id"]: p for p in quelle.pakete()}
    assert list(pakete) == ["zivilrecht", "strafrecht", "verwaltungsrecht", "landesrecht_bayern"]
    assert pakete["zivilrecht"]["aktiv"] and pakete["zivilrecht"]["wirksam"]
    assert not pakete["strafrecht"]["aktiv"]
    assert pakete["landesrecht_bayern"]["teil_von"] == "verwaltungsrecht"
    gesetze = {g["abk"]: g for g in quelle.voreinstellung()}
    assert {"StGB", "StPO", "OWiG", "JGG"} <= {a for a, g in gesetze.items() if "strafrecht" in g["pakete"]}
    assert {"VwGO", "VwVfG", "BauGB", "BauNVO"} <= {a for a, g in gesetze.items() if "verwaltungsrecht" in g["pakete"]}
    assert {"BayBO", "PAG", "GO"} <= {a for a, g in gesetze.items() if "landesrecht_bayern" in g["pakete"]}
    # Gemeinsame Gesetze gehören mehreren Paketen an.
    assert gesetze["GVG"]["pakete"] == ["zivilrecht", "strafrecht"]
    assert sum(1 for g in quelle.voreinstellung() if g["abk"] == "GVG") == 1


def test_verfuegbar_nur_aus_eingeschalteten_paketen(tmp_path):
    schalter = tmp_path / "gesetzespakete.json"
    abk = {g["abk"] for g in quelle.verfuegbar(None, schalter)}
    assert "BGB" in abk and "StGB" not in abk and "BayBO" not in abk

    quelle.paket_schalten("strafrecht", True, None, schalter)
    abk = [g["abk"] for g in quelle.verfuegbar(None, schalter)]
    assert "StGB" in abk and abk.count("GVG") == 1

    # Landesrecht Bayern wirkt nur zusammen mit Verwaltungsrecht.
    pakete = {p["id"]: p for p in quelle.paket_schalten("landesrecht_bayern", True, None, schalter)}
    assert pakete["landesrecht_bayern"]["aktiv"] and not pakete["landesrecht_bayern"]["wirksam"]
    assert "BayBO" not in {g["abk"] for g in quelle.verfuegbar(None, schalter)}
    quelle.paket_schalten("verwaltungsrecht", True, None, schalter)
    assert {"BayBO", "VwGO"} <= {g["abk"] for g in quelle.verfuegbar(None, schalter)}

    # Zivilrecht ausschalten: GVG bleibt über das Strafrecht verfügbar, BGB nicht.
    quelle.paket_schalten("zivilrecht", False, None, schalter)
    abk = {g["abk"] for g in quelle.verfuegbar(None, schalter)}
    assert "GVG" in abk and "BGB" not in abk
    assert json.loads(schalter.read_text(encoding="utf-8"))["aktiv"] == [
        "landesrecht_bayern", "strafrecht", "verwaltungsrecht"]


def test_unbekanntes_paket(tmp_path):
    with pytest.raises(ValueError):
        quelle.paket_schalten("steuerrecht", True, None, tmp_path / "p.json")


def test_eigene_liste_ohne_pakete_ist_immer_an(tmp_path):
    liste = tmp_path / "gesetze.json"
    liste.write_text('{"gesetze": [{"abk": "HGB", "kuerzel": "hgb", "titel": "HGB", "gruppe": "X"}]}', encoding="utf-8")
    pakete = quelle.pakete(liste, tmp_path / "p.json")
    assert [(p["id"], p["wirksam"], p["gesetze"]) for p in pakete] == [("eigene", True, 1)]
    assert [g["abk"] for g in quelle.verfuegbar(liste, tmp_path / "p.json")] == ["HGB"]


def test_pakete_ueber_den_kern(tmp_path):
    kern = Kern(tmp_path / "db.sqlite", tmp_path / "archiv")
    assert {p["id"]: p["aktiv"] for p in kern.methoden["gesetze.pakete"]()}["strafrecht"] is False
    kern.methoden["gesetze.paket_schalten"](paket="strafrecht", aktiv=True)
    assert "StGB" in {g["abk"] for g in kern.methoden["gesetze.verfuegbar"]()}
    assert (tmp_path / "gesetzespakete.json").exists()


# --- Leser für gesetze-bayern.de ------------------------------------------------------------------


def test_bayern_erkennen():
    assert bayern.ist_bayern(SEITE)
    assert not bayern.ist_bayern((FIXTURES / "eurlex_dsgvo_auszug.html").read_bytes())
    assert bayern.abk_aus_titel(SEITE) == "BayBO"


def test_bayern_lesen():
    dok = bayern.parse_bayern_html(SEITE, "BAYBO")
    assert dok.langtitel.startswith("Bayerische Bauordnung (BayBO) in der Fassung der Bekanntmachung")
    assert not dok.langtitel.endswith("Bürgerservice") and "(Art. 1–84)" not in dok.langtitel
    assert dok.builddate == "20260501"
    assert "zuletzt durch § 2 des Gesetzes vom 23. April 2026" in dok.stand[0]
    normen = {n.bezeichnung: n for n in dok.normen}
    assert list(normen) == ["Art. 1", "Art. 2", "Art. 2a", "Art. 8"]

    art1 = normen["Art. 1"]
    assert art1.titel == "Anwendungsbereich"
    assert art1.typ == "artikel" and art1.nummer == "1"
    assert art1.gliederung == ["Erster Teil Allgemeine Vorschriften"]
    assert [a.nr for a in art1.absaetze] == ["1", "2"]
    assert [s.text for s in art1.absaetze[0].saetze] == [
        "Dieses Gesetz gilt für alle baulichen Anlagen und Bauprodukte.",
        "Es gilt auch für Grundstücke sowie für andere Anlagen und Einrichtungen, an die in diesem Gesetz "
        "Anforderungen gestellt werden.",
    ]
    assert [nr for nr, _ in art1.absaetze[1].saetze[0].nummern] == ["1", "2", "3"]

    art2 = normen["Art. 2"]
    abs1 = art2.absaetze[0]
    assert len(abs1.saetze) == 3
    assert abs1.saetze[2].text.startswith("Anlagen sind bauliche Anlagen")
    # Unterpunkt „a)“ steht im Text der Nummer davor.
    assert dict(abs1.saetze[1].nummern)["2"].endswith("a) soweit sie überdacht sind,")

    assert normen["Art. 2a"].weggefallen
    art8 = normen["Art. 8"]
    assert art8.gliederung == ["Erster Teil Allgemeine Vorschriften", "Abschnitt I Baugestaltung"]
    # Satznummern ohne Hochstellung („1Bauliche …“) werden ebenfalls entfernt.
    assert art8.absaetze[0].saetze[0].text.startswith("Bauliche Anlagen müssen")
    assert art8.absaetze[0].saetze[1].text.startswith("Bauliche Anlagen dürfen")


def test_bayern_ohne_artikel():
    with pytest.raises(ValueError):
        bayern.parse_bayern_html(b"<html><title>X: Y</title><body>Vollzitat: nichts</body></html>")


class Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture
def portal(monkeypatch):
    """Simuliert gesetze-bayern.de: kennt nur die Gesamtansicht der BayBO."""
    aufrufe = []

    def urlopen(anfrage, timeout):
        aufrufe.append(anfrage.full_url)
        if anfrage.full_url == "https://www.gesetze-bayern.de/Content/Document/BayBO/true":
            return Antwort(SEITE.replace(b"</body>", f"<!-- Sitzung {len(aufrufe)} --></body>".encode()))
        raise urllib.error.HTTPError(anfrage.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(bayern.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(bayern, "PAUSE", 0)
    return aufrufe


def test_bayern_laden_und_zitieren(portal, con, tmp_path):
    roh = quelle.lade_gesetz("BayBO", tmp_path)
    assert roh.archivpfad.suffix == ".html"
    ergebnis = wissensbasis.importiere(con, roh)
    assert ergebnis["abk"] == "BAYBO" and ergebnis["normen"] == 4

    beleg = wissensbasis.loese_zitat(con, "Art. 1 Abs. 1 S. 2 BayBO")
    assert beleg["status"] == "belegt"
    assert beleg["wortlaut"].startswith("Es gilt auch für Grundstücke")
    assert beleg["fassung"]["hinweis"] == bayern.HINWEIS
    assert wissensbasis.loese_zitat(con, "Art. 2 Abs. 1 S. 2 Nr. 3 BayBO")["wortlaut"].startswith("3. Stellplätze")

    # Zweiter Abruf: Die Seite ist anders (Sitzung), der Stand gleich – keine neue Fassung.
    with pytest.raises(quelle.NichtGeaendert):
        quelle.lade_gesetz("baybo", tmp_path)
    assert len(portal) == 2


def test_bayern_abk_der_voreinstellung(portal, tmp_path):
    """„PAG“ wird unter der Kennung „BayPAG“ geladen."""
    kern = Kern(tmp_path / "db.sqlite", tmp_path / "archiv")
    ergebnis = kern.importieren(["PAG"])
    assert "nicht gefunden" in ergebnis[0]["fehler"]
    assert portal[-1] == "https://www.gesetze-bayern.de/Content/Document/BayPAG/true"


def test_bayern_als_datei_importieren(tmp_path, con):
    datei = tmp_path / "BayBO.html"
    datei.write_bytes(SEITE)
    roh = quelle.lies_datei(datei, tmp_path / "archiv")
    assert roh.abk == "BAYBO"
    ergebnis = wissensbasis.importiere(con, roh)
    assert ergebnis["normen"] == 4
    assert wissensbasis.loese_zitat(con, "Art. 8 BayBO")["fassung"]["hinweis"] == bayern.HINWEIS


def test_gespeicherte_pag_seite_bekommt_abk_der_voreinstellung(tmp_path):
    datei = tmp_path / "pag.html"
    datei.write_bytes(SEITE.replace(b"<title>BayBO:", b"<title>BayPAG:"))
    assert quelle.lies_datei(datei, None).abk == "PAG"
