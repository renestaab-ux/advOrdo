"""Kostennote aus der Akte: RVG-Posten, Anrechnung, Vorschüsse, Rechnungsnummern und Word-Datei."""

from __future__ import annotations

import zipfile
from datetime import date
from decimal import Decimal

import pytest

from juracore.eigene import daten as eigene
from juracore.rechner import prozesskosten
from juracore.schriftstuecke import kostennote

from .test_schriftstuecke import kern  # noqa: F401  (Akte Brückner ./. Autohaus Rehnfeld mit Kanzleiprofil)

TAG = date(2026, 10, 28)


def _summen(r: dict) -> dict:
    return {z["nr"]: z["betrag"] for a in r["abschnitte"] for z in a["zeilen"]}


def test_vorgerichtlich_und_klage_wie_prozesskostenrechner():
    """10.000 €, Geschäftsgebühr 1,3, dann Klage mit Termin: gleiche Beträge wie im Prozesskostenrechner."""
    r = kostennote.berechne({"auftrag": "2026-01-10", "gegenstandswert": "10.000",
                             "posten": [{"nr": "2300"}, {"nr": "3100"}, {"nr": "3104"}], "anrechnung": {}})
    assert r["fassung"] == "2025"
    z = _summen(r)
    assert z["Nr. 2300"] == "847.60" and z["Nr. 3100"] == "847.60" and z["Nr. 3104"] == "782.40"
    assert z["Vorbem. 3 Abs. 4"] == "-423.80"  # 0,65 von 652 €
    # je Angelegenheit eine Pauschale
    assert [p["betrag"] for a in r["abschnitte"] for p in a["zeilen"] if p["nr"] == "Nr. 7002"] == ["20.00", "20.00"]
    assert r["netto"] == "2093.80" and r["umsatzsteuer"] == "397.82" and r["brutto"] == "2491.62"
    pk = prozesskosten.berechne(prozesskosten.Eingabe(streitwert=Decimal(10_000), geschaeftsgebuehr=Decimal("1.3")))
    assert pk["summe_eigene"] == r["brutto"]


def test_fassung_nach_auftragsdatum_und_mehrvertretung():
    r = kostennote.berechne({"auftrag": "2024-05-01", "gegenstandswert": "10000", "auftraggeber": 2,
                             "posten": [{"nr": "2300"}]})
    assert r["fassung"] == "2021"
    z = r["abschnitte"][0]["zeilen"][0]
    assert z["satz"] == "1.6" and z["betrag"] == "982.40"  # 1,6 × 614 €
    assert "Erhöhung 0,3 nach Nr. 1008" in z["text"]
    with pytest.raises(ValueError, match="vor dem 01.01.2021"):
        kostennote.berechne({"auftrag": "2020-12-31", "gegenstandswert": "1000", "posten": [{"nr": "2300"}]})


def test_rahmen_und_fehlende_angaben():
    with pytest.raises(ValueError, match="außerhalb des Rahmens"):
        kostennote.berechne({"gegenstandswert": "5000", "posten": [{"nr": "2300", "satz": "2,6"}]})
    with pytest.raises(ValueError, match="Gegenstandswert"):
        kostennote.berechne({"posten": [{"nr": "3100"}]})
    with pytest.raises(ValueError, match="keine Posten"):
        kostennote.berechne({"gegenstandswert": "5000", "posten": []})
    r = kostennote.berechne({"gegenstandswert": "5000", "posten": [{"nr": "2300", "satz": "1,5"}],
                             "anrechnung": {"satz": "1.5"}})
    assert any("über 1,3" in h for h in r["hinweise"])
    assert any("Anrechnung der Geschäftsgebühr entfällt" in h for h in r["hinweise"])


def test_stunden_auslagen_und_vorschuss_abzug():
    r = kostennote.berechne({
        "posten": [
            {"typ": "stunden", "text": "Besprechung", "stunden": "2,5", "stundensatz": "250", "quelle": "zeit:7"},
            {"typ": "auslage", "nr": "7003", "betrag": "12,60"},
            {"typ": "auslage", "text": "Gerichtskostenvorschuss", "betrag": "438", "ust": False},
        ],
        "abzuege": [{"nummer": "2026-0001", "betrag": "595"}],
    })
    assert r["netto"] == "637.60"  # 625 + 12,60, ohne Pauschale (keine gesetzlichen Gebühren)
    assert r["umsatzsteuer"] == "121.14"
    assert r["brutto"] == "1196.74"  # mit 438 € ohne USt
    assert r["abzuege"][0]["ust"] == "95.00" and r["abzuege"][0]["text"] == "Vorschuss Rechnung 2026-0001"
    assert r["zahlbetrag"] == "601.74"
    assert r["abschnitte"][0]["zeilen"][0]["quelle"] == "zeit:7"
    ohne = kostennote.berechne({"umsatzsteuer": 0, "posten": [{"typ": "auslage", "betrag": "10"}]})
    assert ohne["umsatzsteuer"] == "0.00" and ohne["brutto"] == "10.00"


def test_rechnungsnummern_nach_muster(kern):  # noqa: F811
    assert kostennote.naechste_nummer(kern.akten, TAG) == "2026-0001"
    org = eigene.stand(kern.akten, mit_archiv=False)["organisation"]
    eigene.organisation_speichern(kern.akten, org["daten"] | {"rechnungsnummer_muster": "R{JJ}/{NNN}"})
    assert kostennote.naechste_nummer(kern.akten, TAG) == "R26/001"


def test_erzeugen_vorschuss_dann_schlussrechnung(kern, tmp_path):  # noqa: F811
    aid = kern.test_akte
    v = kostennote.vorschlag(kern.akten, aid, TAG)
    assert v["nummer"] == "2026-0001" and v["gegenstandswert"] == "18450.00"
    assert v["empfaenger_id"] == kern.test_bet["mandant"]
    assert v["hinweise"] == []  # Testprofil hat Steuernummer und IBAN
    vorschuss = {"art": "vorschuss", "nummer": v["nummer"], "datum": TAG.isoformat(), "auftrag": "2026-02-01",
                 "gegenstandswert": v["gegenstandswert"], "empfaenger_id": v["empfaenger_id"],
                 "posten": [{"nr": "3100"}]}
    e = kostennote.erzeugen(kern.akten, kern.con, kern.umgebungen.ordner(), kern.ablage, aid, vorschuss)
    assert e["dateiname"] == "2026-10-28 Vorschussrechnung 2026-0001.docx" and e["dokument_id"]
    with pytest.raises(ValueError, match="schon vergeben; nächste freie: 2026-0002"):
        kostennote.erzeugen(kern.akten, kern.con, kern.umgebungen.ordner(), kern.ablage, aid, vorschuss)

    v = kostennote.vorschlag(kern.akten, aid, TAG)
    assert v["nummer"] == "2026-0002"
    assert v["offene_vorschuesse"] == [{"nummer": "2026-0001", "datum": "2026-10-28",
                                        "betrag": e["ergebnis"]["brutto"]}]
    ziel = tmp_path / "entwurf.docx"
    rechnung = vorschuss | {"art": "rechnung", "nummer": v["nummer"], "leistungszeitraum": "Februar bis Oktober 2026",
                            "posten": [{"nr": "3100"}, {"nr": "3104"}],
                            "abzuege": [{"nummer": o["nummer"], "betrag": o["betrag"]}
                                        for o in v["offene_vorschuesse"]]}
    # Nur als Datei: Entwurf, keine Nummer vergeben
    kostennote.erzeugen(kern.akten, kern.con, kern.umgebungen.ordner(), kern.ablage, aid, rechnung, pfad=ziel,
                        in_akte=False)
    assert kostennote.naechste_nummer(kern.akten, TAG) == "2026-0002"
    with zipfile.ZipFile(ziel) as z:
        xml = z.read("word/document.xml").decode()
    for text in ("Kostennote Nr. 2026-0002", "Leistungszeitraum: Februar bis Oktober 2026", "Nr. 7008 VV RVG",
                 "Gegenstandswert: 18.450,00 €", "IBAN DE89 3704 0044 0532 0130 00", "Steuernummer 06142/12345",
                 "abzüglich Vorschuss Rechnung 2026-0001", "Sehr geehrte Frau Dr. Brückner,", "berechnen wir"):
        assert text in xml, text
    assert "{{" not in xml

    kostennote.erzeugen(kern.akten, kern.con, kern.umgebungen.ordner(), kern.ablage, aid, rechnung)
    v = kostennote.vorschlag(kern.akten, aid, TAG)
    assert v["offene_vorschuesse"] == []
    assert [(k["nummer"], k["art"]) for k in v["kostennoten"]] == [("2026-0001", "vorschuss"),
                                                                    ("2026-0002", "rechnung")]
    # Storno: Nummer bleibt vergeben
    kostennote.stornieren(kern.akten, v["kostennoten"][1]["id"])
    assert kostennote.naechste_nummer(kern.akten, TAG) == "2026-0003"
    assert kostennote.vorschlag(kern.akten, aid, TAG)["offene_vorschuesse"][0]["nummer"] == "2026-0001"


def test_geschaeftsgebuehr_aus_frueherer_rechnung(kern):  # noqa: F811
    aid = kern.test_akte
    kostennote.erzeugen(kern.akten, kern.con, kern.umgebungen.ordner(), kern.ablage, aid,
                        {"nummer": "2026-0001", "datum": TAG.isoformat(), "gegenstandswert": "18450",
                         "posten": [{"nr": "2300", "satz": "1.5"}]})
    g = kostennote.vorschlag(kern.akten, aid, TAG)["geschaeftsgebuehr"]
    assert g == {"nummer": "2026-0001", "satz": "1.5", "wert": "18450.00"}


def test_iban_pruefung():
    assert eigene.iban_gueltig("DE89 3704 0044 0532 0130 00")
    assert not eigene.iban_gueltig("DE89 3704 0044 0532 0130 01")
    assert "Die IBAN stimmt nicht: Länge oder Prüfziffer passen nicht." in eigene.plausibel({"iban": "DE12"}, "kanzlei")
