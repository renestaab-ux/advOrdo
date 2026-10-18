import os
import sqlite3
import zipfile
from datetime import datetime

import pytest

from juracore.dokumente import akte, datum

from .conftest import schreibe_pdf

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
_CORE = (
    '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
    'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    '<dcterms:created xsi:type="dcterms:W3CDTF">2026-10-01T08:00:00Z</dcterms:created>'
    '<dcterms:modified xsi:type="dcterms:W3CDTF">{}</dcterms:modified></cp:coreProperties>'
)


def _docx(pfad, absaetze: list[str], geaendert: str | None = None):
    body = "".join(f"<w:p><w:r><w:t xml:space='preserve'>{t}</w:t></w:r></w:p>" for t in absaetze)
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("word/document.xml", f"<w:document {_W}><w:body>{body}</w:body></w:document>")
        if geaendert:
            z.writestr("docProps/core.xml", _CORE.format(geaendert))
    return pfad


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("Freiburg, den 23.06.2025", "2025-06-23"),
        ("Denzlingen, 30.06.2025", "2025-06-30"),
        ("Freiburg im Breisgau, den 1.12.2025", "2025-12-01"),
        ("Frankfurt a. M., 1. März 2025", "2025-03-01"),
        ("[ORT 2], 18.11.2025", "2025-11-18"),
        ("Verkündet am 14.09.2026", "2026-09-14"),
        ("Datum: 3. Januar 2024", "2024-01-03"),
        ("Unser Zeichen: 117/25 SA Freiburg, den 20.10.2025", "2025-10-20"),
    ],
)
def test_datumszeile(text, erwartet):
    gefunden = datum.aus_text([(4, 1, text)])
    assert gefunden["datum"] == erwartet
    assert gefunden["quelle"] == datum.DOKUMENT and gefunden["abschnitt"] == 4 and gefunden["seite"] == 1


@pytest.mark.parametrize(
    "text",
    [
        "Ihr Schreiben vom 23.06.2025 haben wir erhalten.",
        "Mit Kaufvertrag vom 14.03.2025, VW Golf Variant, …",
        "Am Montag, 3.11.2025 kam es zum Unfall.",
        "Freiburg, den 31.02.2025",
    ],
)
def test_daten_im_fliesstext_zaehlen_nicht(text):
    assert datum.aus_text([(1, None, text)]) is None


def test_erste_datumszeile_gilt():
    abschnitte = [(1, 1, "Kanzlei"), (2, 1, "Hamburg, den 02.02.2025"), (3, 2, "Berlin, den 01.01.2024")]
    assert datum.aus_text(abschnitte)["datum"] == "2025-02-02"


def test_word_ohne_datumszeile_nimmt_letztes_speichern(tmp_path):
    entwurf = _docx(tmp_path / "entwurf.docx", ["Entwurf", "Sehr geehrte Damen und Herren,"], "2026-10-17T21:30:00Z")
    d = datum.ermitteln([(1, None, "Entwurf")], "docx", entwurf, entwurf)
    erwartet = datetime.fromisoformat("2026-10-17T21:30:00+00:00").astimezone()
    assert d["quelle"] == datum.WORD and d["gespeichert_quelle"] == datum.WORD
    assert d["datum"] == erwartet.date().isoformat()
    assert d["gespeichert"] == erwartet.isoformat(timespec="seconds")
    assert d["abschnitt"] is None


def test_datei_datum_als_letzter_ausweg(tmp_path):
    datei = tmp_path / "notiz.md"
    datei.write_text("Nur eine Notiz ohne Datum.", encoding="utf-8")
    zeit = datetime(2025, 5, 4, 12, 0).timestamp()
    os.utime(datei, (zeit, zeit))
    d = datum.ermitteln([(1, None, "Nur eine Notiz ohne Datum.")], "md", datei, datei)
    assert d["quelle"] == datum.DATEI and d["datum"] == "2025-05-04"
    # Ohne die Datei am ursprünglichen Ort bleibt das Datum offen, statt den Zeitpunkt des Einlesens zu nehmen.
    assert datum.ermitteln([], "md", datei, None)["quelle"] == datum.UNBEKANNT


def test_import_speichert_datum_mit_fundstelle(con, tmp_path):
    akten = akte.oeffne(tmp_path / "akten.sqlite")
    a = akte.akte_anlegen(akten, "Akte")
    pdf = schreibe_pdf(tmp_path / "schreiben.pdf", [["Kanzlei Muster", "Freiburg, den 23.06.2025", "Sehr geehrte Damen"]])
    entwurf = _docx(tmp_path / "entwurf.docx", ["Entwurf einer Replik"], "2026-10-17T09:00:00Z")
    for pfad in (pdf, entwurf):
        akte.importiere(akten, con, a["id"], pfad, tmp_path / "ablage", ocr=False)
    doks = {d["dateiname"]: d for d in akte.dokumente(akten, a["id"])}

    brief = doks["schreiben.pdf"]
    assert (brief["datum"], brief["datum_quelle"], brief["datum_seite"]) == ("2025-06-23", "dokument", 1)
    assert brief["datum_text"] == "Freiburg, den 23.06.2025"
    assert brief["gespeichert_quelle"] == "datei"

    w = doks["entwurf.docx"]
    assert (w["datum_quelle"], w["gespeichert_quelle"]) == ("word", "word")
    assert w["datum"] == w["gespeichert_am"][:10]
    akten.close()


def test_aeltere_akten_erhalten_datum_beim_oeffnen(con, tmp_path):
    pfad = tmp_path / "akten.sqlite"
    akten = akte.oeffne(pfad)
    a = akte.akte_anlegen(akten, "Akte")
    pdf = schreibe_pdf(tmp_path / "urteil.pdf", [["Landgericht", "Verkündet am 14.09.2026", "Im Namen des Volkes"]])
    akte.importiere(akten, con, a["id"], pdf, tmp_path / "ablage", ocr=False)
    # Stand vor Schema 6 nachbilden: Datumsspalten leer.
    akten.execute("UPDATE dokument SET datum = NULL, datum_quelle = NULL, gespeichert_am = NULL")
    akten.commit()
    akten.close()

    akten = akte.oeffne(pfad)
    d = akte.dokumente(akten, a["id"])[0]
    assert (d["datum"], d["datum_quelle"]) == ("2026-09-14", "dokument")
    assert d["gespeichert_am"] is None  # das Dateidatum am ursprünglichen Ort ist nicht mehr bekannt
    akten.close()


def test_migration_ergaenzt_spalten(tmp_path):
    pfad = tmp_path / "alt.sqlite"
    alt = sqlite3.connect(pfad)
    alt.executescript(
        """CREATE TABLE akte (id INTEGER PRIMARY KEY, name TEXT NOT NULL, angelegt_am TEXT NOT NULL);
           CREATE TABLE dokument (id INTEGER PRIMARY KEY, akte_id INTEGER NOT NULL, dateiname TEXT NOT NULL,
               format TEXT NOT NULL, sha256 TEXT NOT NULL, groesse INTEGER NOT NULL, original TEXT NOT NULL,
               importiert_am TEXT NOT NULL, seiten INTEGER, lesart TEXT NOT NULL, ocr_konfidenz REAL,
               hinweise TEXT NOT NULL, UNIQUE (akte_id, sha256));"""
    )
    alt.close()
    akten = akte.oeffne(pfad)
    spalten = {z["name"] for z in akten.execute("PRAGMA table_info(dokument)")}
    assert {"datum", "datum_quelle", "datum_abschnitt", "datum_text", "gespeichert_am"} <= spalten
    akten.close()
