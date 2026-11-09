from pathlib import Path

import pytest

from juracore.dokumente import akte
from juracore.gesetze import wissensbasis

from .conftest import schreibe_pdf

ZEILE = "Der Anspruch auf Rückzahlung folgt aus §§ 437 Nr. 2, 440, 323 BGB; die Beklagte schuldet nach"


@pytest.fixture
def akten(tmp_path):
    con = akte.oeffne(tmp_path / "akten.sqlite")
    yield con
    con.close()


def _klage(tmp_path):
    return schreibe_pdf(
        tmp_path / "klage.pdf",
        [
            ["(1) " + ZEILE, "§ 280 Abs. 1 BGB Schadensersatz, ein Recht nach § 437 Nr. 4 BGB gibt es nicht."],
            ["- 2 -", "(2) Gerichtsstand nach § 23 Nr. 1 GVG; Beweiswürdigung nach § 286 Abs. 2 ZPO."],
        ],
    )


def test_import_legt_original_ab_und_verknuepft_normen(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Brückner ./. Autohaus")
    ablage = tmp_path / "ablage"
    pdf = _klage(tmp_path)
    ergebnis = akte.importiere(akten, con, a["id"], pdf, ablage, ocr=False)
    assert ergebnis["neu"] is True
    assert ergebnis["zitate"] == {"belegt": 3, "nicht_gefunden": 3, "unbekanntes_gesetz": 1}

    # Original unverändert unter seiner Prüfsumme.
    doks = akte.dokumente(akten, a["id"])
    assert len(doks) == 1
    original = Path(doks[0]["original"])
    assert original.read_bytes() == pdf.read_bytes()
    assert original.name == f"{doks[0]['sha256']}.pdf"
    assert doks[0]["randnummern"] == 2

    # Dieselbe Datei wird nicht doppelt übernommen.
    assert akte.importiere(akten, con, a["id"], pdf, ablage, ocr=False)["neu"] is False


def test_fundstellen_mit_seite_und_randnummer(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Akte")
    d = akte.importiere(akten, con, a["id"], _klage(tmp_path), tmp_path / "ablage", ocr=False)
    inhalt = akte.dokument(akten, d["dokument_id"])
    zitate = {z["zitat"]: (z, abschnitt) for abschnitt in inhalt["abschnitte"] for z in abschnitt["zitate"]}

    z, abschnitt = zitate["§ 437 Nr. 4 BGB"]
    assert z["status"] == "nicht_gefunden"
    assert z["hinweis"] == "Nr. 4 wurde in der Fundstelle nicht gefunden."
    assert abschnitt["rn"] == 1 and z["seite"] == 1
    assert abschnitt["text"][z["start"] : z["ende"]] == "437 Nr. 4"
    assert abschnitt["text"][z["treffer_start"] : z["treffer_ende"]] == "§ 437 Nr. 4 BGB"

    belegt, _ = zitate["§ 286 Abs. 2 ZPO"]
    assert belegt["status"] == "belegt"
    assert belegt["fassung_id"] is not None
    assert belegt["seite"] == 2
    assert zitate["§ 23 Nr. 1 GVG"][0]["status"] == "unbekanntes_gesetz"


def test_normenuebersicht_und_neue_pruefung(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Akte")
    akte.importiere(akten, con, a["id"], _klage(tmp_path), tmp_path / "ablage", ocr=False)
    normen = akte.normen(akten, a["id"])
    # Probleme zuerst.
    assert normen[0]["status"] == "nicht_gefunden"
    assert normen[-1]["status"] == "belegt"
    eintrag = next(n for n in normen if n["zitat"] == "§ 280 Abs. 1 BGB")
    assert eintrag["fundstellen"][0]["rn"] == 1
    assert akte.zitate_neu_pruefen(akten, con, a["id"]) == {"dokumente": 1}
    assert len(akte.normen(akten, a["id"])) == len(normen)


def test_fehler(akten, con, tmp_path):
    with pytest.raises(ValueError):
        akte.akte_anlegen(akten, "  ")
    with pytest.raises(LookupError):
        akte.importiere(akten, con, 99, _klage(tmp_path), tmp_path, ocr=False)
    a = akte.akte_anlegen(akten, "Akte")
    with pytest.raises(FileNotFoundError):
        akte.importiere(akten, con, a["id"], tmp_path / "fehlt.pdf", tmp_path, ocr=False)


def test_dokument_loeschen_entfernt_kopie_nicht_original(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Akte")
    ablage = tmp_path / "ablage"
    pdf = _klage(tmp_path)
    d = akte.importiere(akten, con, a["id"], pdf, ablage, ocr=False)
    kopie = Path(akte.dokumente(akten, a["id"])[0]["original"])
    ergebnis = akte.dokument_loeschen(akten, d["dokument_id"], ablage)
    assert ergebnis["hinweis"] is None
    assert not kopie.exists()
    assert pdf.exists()
    # Text, Zitate und Tags sind mit weg.
    for tabelle in ("abschnitt", "normzitat", "seite", "tag"):
        assert akten.execute(f"SELECT COUNT(*) FROM {tabelle}").fetchone()[0] == 0
    with pytest.raises(LookupError):
        akte.dokument_loeschen(akten, d["dokument_id"], ablage)
    # Danach lässt sich dieselbe Datei wieder einlesen.
    assert akte.importiere(akten, con, a["id"], pdf, ablage, ocr=False)["neu"] is True


def test_akte_loeschen(akten, con, tmp_path):
    ablage = tmp_path / "ablage"
    a = akte.akte_anlegen(akten, "Weg damit")
    b = akte.akte_anlegen(akten, "Bleibt")
    akte.importiere(akten, con, a["id"], _klage(tmp_path), ablage, ocr=False)
    akte.importiere(akten, con, b["id"], _klage(tmp_path), ablage, ocr=False)
    ergebnis = akte.akte_loeschen(akten, a["id"], ablage)
    assert ergebnis == {"akte_id": a["id"], "name": "Weg damit", "dokumente": 1, "hinweis": None}
    assert not (ablage / f"akte-{a['id']}").exists()
    assert [x["name"] for x in akte.akten(akten)] == ["Bleibt"]
    assert len(akte.dokumente(akten, b["id"])) == 1
    assert (ablage / f"akte-{b['id']}").is_dir()
    with pytest.raises(LookupError):
        akte.akte_loeschen(akten, a["id"], ablage)


@pytest.mark.parametrize(
    ("ordner", "tag"),
    [
        ("Kläger", "Kläger"),
        ("01_Klaegerin", "Kläger"),
        ("2 - Beklagte", "Beklagter"),
        ("Gericht", "Gericht"),
        ("Landgericht", "Gericht"),
        ("A) Sachverständiger", "Sachverständiger"),
        ("Anlagen", "Anlagen"),
        ("2025", "2025"),
    ],
)
def test_tag_vorschlag(ordner, tag):
    assert akte.tag_vorschlag(ordner) == tag


def test_ordner_pruefen_mit_unterordnern(tmp_path):
    wurzel = tmp_path / "Akte Brückner"
    for teil in ("Kläger/Anlagen", "Beklagter", "Gericht", ".versteckt"):
        (wurzel / teil).mkdir(parents=True)
    (wurzel / "Notiz.txt").write_text("Notiz", "utf-8")
    (wurzel / "Kläger" / "Klage.docx").write_bytes(b"x")
    (wurzel / "Kläger" / "~$Klage.docx").write_bytes(b"x")
    (wurzel / "Kläger" / "Anlagen" / "K1.pdf").write_bytes(b"x")
    (wurzel / "Kläger" / "Anlagen" / "Foto.jpg").write_bytes(b"x")
    (wurzel / "Beklagter" / "Erwiderung.pdf").write_bytes(b"x")
    (wurzel / "Gericht" / "Beschluss.pdf").write_bytes(b"x")
    (wurzel / ".versteckt" / "x.pdf").write_bytes(b"x")

    funde = akte.ordner_pruefen(wurzel)
    assert funde["name"] == "Akte Brückner"
    assert [d["relativ"] for d in funde["dateien"]] == [
        "Notiz.txt",
        "Beklagter/Erwiderung.pdf",
        "Gericht/Beschluss.pdf",
        "Kläger/Klage.docx",
        "Kläger/Anlagen/K1.pdf",
    ]
    assert funde["unterordner"] == [
        {"herkunft": "", "dateien": 1, "tags": []},
        {"herkunft": "Beklagter", "dateien": 1, "tags": ["Beklagter"]},
        {"herkunft": "Gericht", "dateien": 1, "tags": ["Gericht"]},
        {"herkunft": "Kläger", "dateien": 1, "tags": ["Kläger"]},
        {"herkunft": "Kläger/Anlagen", "dateien": 1, "tags": ["Kläger", "Anlagen"]},
    ]
    assert funde["uebersprungen"] == ["Kläger/Anlagen/Foto.jpg"]
    with pytest.raises(FileNotFoundError):
        akte.ordner_pruefen(tmp_path / "fehlt")


def test_tags_beim_import_und_von_hand(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Akte")
    ablage = tmp_path / "ablage"
    pdf = _klage(tmp_path)
    d = akte.importiere(akten, con, a["id"], pdf, ablage, ocr=False, tags=["Kläger", " kläger "], herkunft="Kläger")
    dok = akte.dokumente(akten, a["id"])[0]
    assert dok["tags"] == [{"name": "Kläger", "quelle": "ordner"}]
    assert dok["herkunft"] == "Kläger"
    # Erneut eingelesen: Tags werden ergänzt, nicht ersetzt.
    akte.importiere(akten, con, a["id"], pdf, ablage, ocr=False, tags=["Anlagen"])
    assert [t["name"] for t in akte.dokumente(akten, a["id"])[0]["tags"]] == ["Anlagen", "Kläger"]
    # Von Hand: Kläger bleibt aus dem Ordner, Gericht kommt manuell dazu, Anlagen fällt weg.
    assert akte.tags_setzen(akten, d["dokument_id"], ["Kläger", "Gericht", ""]) == [
        {"name": "Gericht", "quelle": "manuell"},
        {"name": "Kläger", "quelle": "ordner"},
    ]
    assert akte.tags_setzen(akten, d["dokument_id"], []) == []
    with pytest.raises(LookupError):
        akte.tags_setzen(akten, 99, ["x"])


def test_alte_akten_werden_migriert(tmp_path):
    import sqlite3

    pfad = tmp_path / "akten.sqlite"
    alt = sqlite3.connect(pfad)
    alt.executescript(
        """CREATE TABLE akte (id INTEGER PRIMARY KEY, name TEXT NOT NULL, angelegt_am TEXT NOT NULL);
           CREATE TABLE dokument (id INTEGER PRIMARY KEY, akte_id INTEGER NOT NULL, dateiname TEXT NOT NULL,
               format TEXT NOT NULL, sha256 TEXT NOT NULL, groesse INTEGER NOT NULL, original TEXT NOT NULL,
               importiert_am TEXT NOT NULL, seiten INTEGER, lesart TEXT NOT NULL, ocr_konfidenz REAL,
               hinweise TEXT NOT NULL, UNIQUE (akte_id, sha256));
           INSERT INTO akte VALUES (1, 'Alt', '2026-10-12');
           INSERT INTO dokument VALUES (1, 1, 'a.pdf', 'pdf', 'x', 1, '/a', '2026-10-12', 1, 'textebene', NULL, '[]');
           PRAGMA user_version = 1;"""
    )
    alt.close()
    con = akte.oeffne(pfad)
    dok = akte.dokumente(con, 1)[0]
    assert dok["herkunft"] is None and dok["tags"] == []
    assert con.execute("PRAGMA user_version").fetchone()[0] == akte.SCHEMA_VERSION
    con.close()


def test_herkunft_jurabox_wird_advordo(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Akte")
    ablage = tmp_path / "ablage"
    akte.importiere(akten, con, a["id"], _klage(tmp_path), ablage, ocr=False, herkunft="Von JuraBox erzeugt")
    akten.close()
    neu = akte.oeffne(tmp_path / "akten.sqlite")
    try:
        assert akte.dokumente(neu, a["id"])[0]["herkunft"] == "Von advOrdo erzeugt"
    finally:
        neu.close()


def test_eigene_schreibweise_prueft_alle_akten_neu(akten, con, tmp_path):
    a = akte.akte_anlegen(akten, "Akte")
    akte.importiere(akten, con, a["id"], _klage(tmp_path), tmp_path / "ablage", ocr=False)
    gvg = next(n for n in akte.normen(akten, a["id"]) if n["gesetz"] == "GVG")
    assert gvg["status"] == "unbekanntes_gesetz" and gvg["gemeint"] is None

    wissensbasis.schreibweise_setzen(con, "GVG", "ZPO")
    assert akte.normzitate_eines_gesetzes_neu_pruefen(akten, con, ["GVG"]) == {"dokumente": 1}
    gvg = next(n for n in akte.normen(akten, a["id"]) if n["gesetz"] == "GVG")
    assert gvg["zitat"] == "§ 23 Nr. 1 GVG"  # wie im Text
    assert gvg["gemeint"] == "ZPO"
    assert gvg["hinweis"].startswith("Im Text steht „GVG“; zugeordnet zu ZPO")

    wissensbasis.schreibweise_loeschen(con, "GVG")
    assert akte.normzitate_eines_gesetzes_neu_pruefen(akten, con, ["GVG"]) == {"dokumente": 1}
    assert next(n for n in akte.normen(akten, a["id"]) if n["gesetz"] == "GVG")["gemeint"] is None
