from pathlib import Path

import pytest

from juracore.dokumente import akte

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
