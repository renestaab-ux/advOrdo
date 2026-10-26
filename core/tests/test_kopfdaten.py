"""Kopfdaten einer selbst hinzugefügten Entscheidung (fiktive Beispiele in der Form üblicher Ausdrucke)."""

import json

import pytest

from juracore import rpc
from juracore.dokumente import akte, urteile
from juracore.rechtsprechung import kopfdaten


def _abschnitte(text: str) -> list[tuple[int, int | None, str]]:
    return [(i, 1, t) for i, t in enumerate(text.split("\n\n"), 1)]


def _werte(ergebnis: dict) -> dict:
    return {k: (v or {}).get("wert") for k, v in ergebnis.items()}


@pytest.mark.parametrize("text, erwartet", [
    ("Oberlandesgericht Hamm", "OLG Hamm"),
    ("OBERLANDESGERICHT FRANKFURT AM MAIN", "OLG Frankfurt am Main"),
    ("Landgericht Freiburg im Breisgau 3. Zivilkammer", "LG Freiburg im Breisgau"),
    ("LANDGERICHT FREIBURG IM BREISGAU", "LG Freiburg im Breisgau"),
    ("Landgericht Freiburg i. Br.", "LG Freiburg i. Br."),
    ("BUNDESGERICHTSHOF", "BGH"),
    ("Bundesarbeitsgericht Erfurt", "BAG"),
    ("OLG München 7. Zivilsenat", "OLG München"),
    ("Kammergericht", "KG"),
    ("Landgericht hat die Klage abgewiesen", None),
    ("Im Namen des Volkes", None),
])
def test_gericht_kurz(text, erwartet):
    assert kopfdaten.gericht_kurz(text) == erwartet


def test_juris_ausdruck_mit_beschriftung():
    text = """Gericht:\nOLG Hamm 28. Zivilsenat

Entscheidungsdatum:\n03.05.2022

Aktenzeichen:\n28 U 12/21

Dokumenttyp:\nUrteil

Quelle: juris

Tenor

Die Berufung wird zurückgewiesen."""
    e = kopfdaten.erkenne(_abschnitte(text))
    assert _werte(e) == {"gericht": "OLG Hamm", "aktenzeichen": "28 U 12/21", "datum": "2022-05-03",
                         "art": "Urteil", "herkunft": "juris"}
    # Jeder Wert mit Fundstelle.
    assert e["aktenzeichen"]["fundstelle"] == {"abschnitt": 3, "seite": 1, "text": "Aktenzeichen: 28 U 12/21"}


def test_beck_online_zitierzeile():
    text = """BGH, Urteil vom 17.03.2021 – VIII ZR 999/20

BeckRS 2021, 99999

Leitsatz

Die Erklärung ist auszulegen."""
    assert _werte(kopfdaten.erkenne(_abschnitte(text))) == {
        "gericht": "BGH", "aktenzeichen": "VIII ZR 999/20", "datum": "2021-03-17", "art": "Urteil",
        "herkunft": "beck-online"}


def test_ausfertigung_des_gerichts():
    text = """BUNDESGERICHTSHOF

IM NAMEN DES VOLKES

URTEIL

VIII ZR 999/20

Verkündet am: 17. März 2021

in dem Rechtsstreit"""
    assert _werte(kopfdaten.erkenne(_abschnitte(text))) == {
        "gericht": "BGH", "aktenzeichen": "VIII ZR 999/20", "datum": "2021-03-17", "art": "Urteil", "herkunft": None}


def test_art_aus_der_tenorformel_und_nichts_erfunden():
    text = """Landgericht Freiburg im Breisgau

Az.: 3 O 412/25

hat die 3. Zivilkammer beschlossen:

Der Antrag wird zurückgewiesen."""
    assert _werte(kopfdaten.erkenne(_abschnitte(text))) == {
        "gericht": "LG Freiburg im Breisgau", "aktenzeichen": "3 O 412/25", "datum": None, "art": "Beschluss",
        "herkunft": None}
    assert _werte(kopfdaten.erkenne(_abschnitte("Ein Brief ohne Gericht und Aktenzeichen."))) == dict.fromkeys(
        ("gericht", "aktenzeichen", "datum", "art", "herkunft"))


def test_vorschlag_und_ablegen_mit_art(tmp_path):
    datei = tmp_path / "juris_OLG_Hamm.txt"
    datei.write_text("Gericht: OLG Hamm\n\nAktenzeichen: 28 U 12/21\n\nEntscheidungsdatum: 03.05.2022\n\n"
                     "Dokumenttyp: Beschluss\n\n(1) Der Senat weist darauf hin.", encoding="utf-8")
    kern = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")

    def rufe(methode, **params):
        antwort = kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))
        assert "error" not in antwort, antwort
        return antwort["result"]

    v = rufe("rechtsprechung.vorschlag", pfad=str(datei))
    assert _werte({k: v[k] for k in ("gericht", "aktenzeichen", "datum", "art")}) == {
        "gericht": "OLG Hamm", "aktenzeichen": "28 U 12/21", "datum": "2022-05-03", "art": "Beschluss"}
    u = rufe("rechtsprechung.ergaenzen", pfad=str(datei), gericht="OLG Hamm", aktenzeichen="28 U 12/21",
             datum="2022-05-03", art="Beschluss")
    (eintrag,) = rufe("rechtsprechung.sammlung")
    assert eintrag["id"] == u["urteil_id"] and eintrag["kopf"]["doktyp"] == "Beschluss"
    # Ohne Art bleibt der Kopf leer wie bisher.
    con = akte.oeffne(tmp_path / "zweite.sqlite")
    ohne = urteile.ergaenzen(con, None, datei, tmp_path / "ablage", gericht="OLG Hamm", ocr=False)
    assert urteile.volltext(con, ohne["urteil_id"])["kopf"] is None
    con.close()
