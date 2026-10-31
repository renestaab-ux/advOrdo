import zipfile
from datetime import datetime

import pytest

from juracore import aktenverwaltung
from juracore.ausgabe import Eintrag, Ueberschrift
from juracore.dokumente import akte, anmerkungen, anmerkungen_ausgabe, lesezeichen


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    aktenverwaltung.einrichten(con)
    anmerkungen.einrichten(con)
    lesezeichen.einrichten(con)
    yield con
    con.close()


TEXT = ("Die Klägerin kaufte am 14.03.2025 ein Fahrzeug.\n\n"
        "Der Kilometerstand betrug 45.000 km laut Vertrag.\n\n"
        "Die Beklagte bestreitet den Mangel mit Nichtwissen.")


def _akte(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Brückner ./. Autohaus")["id"]
    (tmp_path / "klage.md").write_text(TEXT, encoding="utf-8")
    d = akte.importiere(akten, con, a, tmp_path / "klage.md", tmp_path / "ablage", ocr=False)["dokument_id"]
    text = "\n".join(z["text"] for z in akten.execute(
        "SELECT text FROM abschnitt WHERE dokument_id = ? ORDER BY nr", (d,)))
    s = text.index("45.000 km")
    m1 = anmerkungen.anlegen(akten, d, s, s + len("45.000 km"), "rot", kommentar="**Bestritten**, siehe Gutachten")
    s = text.index("bestreitet")
    m2 = anmerkungen.anlegen(akten, d, s, s + len("bestreitet"), "blau", "unterstrichen")
    z = lesezeichen.anlegen(akten, d, text.index("Der Kilometer"), titel="Kilometer")
    o = lesezeichen.ordner_anlegen(akten, a, "Beweisfragen")
    return a, d, m1, m2, z, o


def test_bericht_nach_ordnern(akten, con, tmp_path):
    a, d, m1, m2, z, o = _akte(akten, con, tmp_path)
    ordner = [{"id": o["id"], "eintraege": [{"art": "markierung", "id": m1["id"]}]},
              {"id": None, "eintraege": [{"art": "lesezeichen", "id": z["id"]},
                                         {"art": "markierung", "id": m2["id"]}]}]
    b = anmerkungen_ausgabe.bericht(akten, a, ordner, auswahl="Streitig, Beweis",
                                    jetzt=datetime(2026, 10, 31, 12, 0))
    kopf = dict(b.bausteine[0].zeilen)
    assert kopf["Umfang"] == "2 Markierungen (1 mit Kommentar), 1 Lesezeichen"
    assert kopf["Auswahl"] == "Streitig, Beweis"
    assert kopf["Farben"] == "Blau = Beweis; Rot = Streitig"
    assert b.bausteine[0].zeilen[-1] == ("Ausgegeben am", "31.10.2026, 12:00")
    assert [x.text for x in b.bausteine if isinstance(x, Ueberschrift)] == ["Beweisfragen", "Ohne Ordner"]
    e = [x for x in b.bausteine if isinstance(x, Eintrag)]
    assert e[0].titel == "„45.000 km“" and e[0].marken == ["Streitig"]
    assert e[0].zeilen == ["Kommentar: Bestritten, siehe Gutachten"]
    assert e[0].belege[0].ort.startswith("klage")
    assert e[1].titel == "Lesezeichen: Kilometer"
    assert e[2].marken == ["Beweis", "unterstrichen"]
    assert [r[0] for r in b.tabellen[0].zeilen] == [1, 2, 3]
    assert b.tabellen[0].zeilen[0][2] == "Beweisfragen"


def test_bericht_nach_dokumenten_in_textfolge(akten, con, tmp_path):
    a, d, m1, m2, z, o = _akte(akten, con, tmp_path)
    ordner = [{"id": None, "eintraege": [{"art": "markierung", "id": m2["id"]},
                                         {"art": "markierung", "id": m1["id"]},
                                         {"art": "lesezeichen", "id": z["id"]}]}]
    b = anmerkungen_ausgabe.bericht(akten, a, ordner, "dokumente")
    e = [x.titel for x in b.bausteine if isinstance(x, Eintrag)]
    assert e == ["Lesezeichen: Kilometer", "„45.000 km“", "„bestreitet“"]
    # Das Dokument steht als Überschrift, die Fundstelle daher ohne Dokumentnamen
    assert not [x for x in b.bausteine if isinstance(x, Eintrag)][1].belege[0].ort.startswith("klage")


def test_verlorene_stelle_bleibt_drin(akten, con, tmp_path):
    a, d, m1, m2, z, o = _akte(akten, con, tmp_path)
    akten.execute("UPDATE abschnitt SET text = 'Ganz anderer Text.' WHERE dokument_id = ? AND text LIKE '%45.000%'",
                  (d,))
    akten.commit()
    b = anmerkungen_ausgabe.bericht(akten, a, [{"id": None, "eintraege": [{"art": "markierung", "id": m1["id"]}]}])
    e = [x for x in b.bausteine if isinstance(x, Eintrag)][0]
    assert "nicht mehr im Text" in e.marken
    assert "Stelle nicht mehr im Text" in e.belege[0].ort


def test_fremde_und_leere_auswahl(akten, con, tmp_path):
    a, d, m1, m2, z, o = _akte(akten, con, tmp_path)
    andere = akte.akte_anlegen(akten, "Andere")["id"]
    with pytest.raises(LookupError):
        anmerkungen_ausgabe.bericht(akten, andere, [{"id": None, "eintraege": [{"art": "markierung", "id": m1["id"]}]}])
    with pytest.raises(ValueError):
        anmerkungen_ausgabe.bericht(akten, a, [{"id": None, "eintraege": []}])


@pytest.mark.parametrize("format", ["docx", "pdf", "xlsx", "md", "txt"])
def test_alle_formate(akten, con, tmp_path, format):
    a, d, m1, m2, z, o = _akte(akten, con, tmp_path)
    ordner = [{"id": None, "eintraege": [{"art": "markierung", "id": m1["id"]}, {"art": "lesezeichen", "id": z["id"]}]}]
    r = anmerkungen_ausgabe.schreiben(akten, a, ordner, format, tmp_path / "aus")
    pfad = tmp_path / f"aus.{format}"
    assert r["pfad"] == str(pfad) and pfad.stat().st_size > 0
    if format in ("md", "txt"):
        inhalt = pfad.read_text(encoding="utf-8")
        assert "45.000 km" in inhalt and "Bestritten, siehe Gutachten" in inhalt and "Kilometer" in inhalt
    if format in ("docx", "xlsx"):
        assert zipfile.is_zipfile(pfad)


def test_druckansicht_und_dateiname(akten, con, tmp_path):
    a, d, m1, m2, z, o = _akte(akten, con, tmp_path)
    r = anmerkungen_ausgabe.druckansicht(akten, a, [{"id": None, "eintraege": [{"art": "markierung", "id": m1["id"]}]}])
    assert "45.000 km" in r["html"] and r["titel"].startswith("Anmerkungen: ")
    name = anmerkungen_ausgabe.dateiname(akten, a, datetime(2026, 10, 31))
    assert name == "Anmerkungen Brückner gg. Autohaus 2026-10-31"
