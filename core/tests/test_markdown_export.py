"""Markdown-Export: Gesetze (Nachbau von gii2md.py), Dokumente einer Akte und Urteile."""

from __future__ import annotations

import io
import zipfile

import pytest

from juracore import rpc
from juracore.ausgabe import markdown_export
from juracore.dokumente import akte, urteile
from juracore.gesetze import markdown as gii_markdown
from juracore.rechtsprechung import verzeichnis

from .conftest import FIXTURES
from .test_rechtsprechung import KLAGE
from .test_urteile import AUSDRUCK, _zip_auszug

# Ausgaben des Referenzskripts gii2md.py (Stand 20.11.2026) für dieselben XML-Dateien.
AUSZUEGE = ["bgb_auszug", "hgb_auszug", "zpo_auszug", "egbgb_auszug", "gii_markdown_auszug"]


@pytest.mark.parametrize("name", AUSZUEGE)
def test_gleiche_ausgabe_wie_das_skript(name):
    xml = (FIXTURES / f"{name}.xml").read_bytes()
    md, _ = gii_markdown.umwandeln(xml)
    assert md == (FIXTURES / "markdown" / f"{name}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["bgb_auszug", "hgb_auszug", "zpo_auszug", "egbgb_auszug"])
def test_pruefen_vollstaendig(name):
    xml = (FIXTURES / f"{name}.xml").read_bytes()
    md, _ = gii_markdown.umwandeln(xml)
    assert gii_markdown.pruefen(xml, md) == {}


def test_pruefen_meldet_fehlende_woerter():
    xml = (FIXTURES / "gii_markdown_auszug.xml").read_bytes()
    md, _ = gii_markdown.umwandeln(xml)
    gekuerzt = md.replace("Sie entscheidet nach Anhörung.", "")
    fehlt = gii_markdown.pruefen(xml, gekuerzt)
    assert fehlt["entscheidet"] == 1 and fehlt["Anhörung"] == 1


def test_aufbau():
    md, meta = gii_markdown.umwandeln((FIXTURES / "gii_markdown_auszug.xml").read_bytes())
    assert md.startswith("# Gesetz über die Prüfung von Mustertexten (MustG)\n")
    assert "- Fundstelle: BGBl I 2001, 123" in md
    # Inhaltsübersicht nicht übernommen, Gliederung und Paragrafen als Überschriften.
    assert "Teil 1 Allgemeine Vorschriften § 1 Zweck" not in md
    assert "## Teil 1 Allgemeine Vorschriften\n" in md and "### Abschnitt 1 Zweck und Begriffe\n" in md
    assert "#### § 1 Zweck\n" in md
    # Satznummern hochgestellt, verschachtelte Listen, Tabelle, Fußnoten.
    assert "(1) ¹Mustertexte sind **sorgfältig** zu prüfen. ²Die Prüfung" in md
    assert "\n    - a) die Vollständigkeit und\n" in md
    assert "| Text \\| mit Anlagen | 35 Euro |" in md
    assert "- Fußnote 1 Frist im Sinne des § 3." in md
    assert "> Fußnote: § 2: Gebühren" in md
    assert meta["abk"] == "MustG" and not meta["letztmalig"]


def test_dateiname_nimmt_letzte_aenderung():
    _, meta = gii_markdown.umwandeln((FIXTURES / "gii_markdown_auszug.xml").read_bytes())
    # Die Neufassung (5.6.2010) steht zuerst; maßgeblich ist „Zuletzt geändert … v. 9.10.2026“.
    assert gii_markdown.dateiname(meta) == "MustG_Gesetz-ueber-die-Pruefung-von-Mustertexten_Stand-2026-10-09.md"
    assert gii_markdown.stand_datum(["Neugefasst durch Bek. v. 2.1.2002 I 42"], "1896-08-18") == "2002-01-02"
    assert gii_markdown.stand_datum([], "1896-08-18") == "1896-08-18"
    assert gii_markdown.stand_datum([None], "") == "unbekannt"


def test_altfassung_letztmalig_und_html_entitaeten():
    xml = (FIXTURES / "gii_markdown_auszug.xml").read_text(encoding="utf-8")
    xml = xml.replace("Zuletzt geändert durch Art. 3 G v. 9.10.2026 I Nr. 250",
                      "Gesetz ist gem. § 9 letztmalig für den VZ 2005 anzuwenden; zuletzt geändert durch G v. 1.2.2005")
    xml = xml.replace("Zuständig ist die Prüfstelle.", "Zuständig ist die&nbsp;Prüfstelle.")
    md, meta = gii_markdown.umwandeln(xml.encode("utf-8"))
    assert meta["letztmalig"]
    assert meta["stand_datum"] == "2010-06-05"  # letztmalige Anwendung zählt nicht als Stand
    assert "Zuständig ist die Prüfstelle." in md


def test_kein_gii_dokument():
    with pytest.raises(ValueError):
        gii_markdown.umwandeln(b"<bayportalrsp/>")


# --- über den Kern -------------------------------------------------------------------------------------------------


@pytest.fixture
def kern(tmp_path):
    k = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    yield k
    k.con.close()
    k.akten.close()


def test_gesetz_aus_archiviertem_zip(kern, tmp_path):
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("BJNR000000001.xml", (FIXTURES / "gii_markdown_auszug.xml").read_bytes())
    (tmp_path / "xml.zip").write_bytes(puffer.getvalue())
    kern.methoden["gesetze.importieren_datei"](pfad=str(tmp_path / "xml.zip"))

    name = kern.methoden["markdown.name"](gesetz="MustG")
    assert name == {"name": "MustG_Gesetz-ueber-die-Pruefung-von-Mustertexten_Stand-2026-10-09.md", "warnung": None}
    r = kern.methoden["markdown.speichern"](pfad=str(tmp_path / "ausgabe"), gesetz="MustG")
    assert r["pfad"].endswith("ausgabe.md")
    erwartet = (FIXTURES / "markdown" / "gii_markdown_auszug.md").read_text(encoding="utf-8")
    assert (tmp_path / "ausgabe.md").read_text(encoding="utf-8") == erwartet


def test_gesetz_ohne_roharchiv_aus_der_wissensbasis(kern, tmp_path):
    kern.methoden["gesetze.importieren_datei"](pfad=str(FIXTURES / "bgb_auszug.xml"))
    kern.con.execute("UPDATE fassung SET roharchiv = NULL")
    erg = markdown_export.gesetz(kern.con, "BGB")
    md = erg["markdown"]
    assert erg["aus"] == "wissensbasis"
    assert md.startswith("# Bürgerliches Gesetzbuch (BGB)\n")
    assert "## Buch 1 Allgemeiner Teil\n" in md and "### Abschnitt 5 Verjährung\n" in md
    assert "(1) Verletzt der Schuldner eine Pflicht aus dem Schuldverhältnis" in md
    assert erg["name"].startswith("BGB_Buergerliches-Gesetzbuch_Stand-2026-09-01")


def test_eurlex_aus_der_wissensbasis(kern):
    kern.methoden["gesetze.importieren_datei"](pfad=str(FIXTURES / "eurlex_dsgvo_auszug.html"))
    erg = markdown_export.gesetz(kern.con, "DSGVO")
    assert erg["aus"] == "wissensbasis"
    assert "Amtsblatts der EU" in erg["markdown"] and "Art. 1 Gegenstand und Ziele" in erg["markdown"]


def test_unbekanntes_gesetz(kern):
    with pytest.raises(LookupError):
        kern.methoden["markdown.name"](gesetz="XYZ")
    with pytest.raises(ValueError):
        kern.methoden["markdown.name"](gesetz="BGB", dokument_id=1)


def test_dokument_mit_randnummern_und_kopf(kern, tmp_path):
    a = akte.akte_anlegen(kern.akten, "Brückner ./. Autohaus")
    datei = tmp_path / "05_Klageschrift.md"
    datei.write_text(f"Klageschrift\n\n(1) {KLAGE}\n\n(2) Der Beklagte schuldet Ersatz.", encoding="utf-8")
    dok = akte.importiere(kern.akten, kern.con, a["id"], datei, tmp_path / "ablage", ocr=False)["dokument_id"]

    name = kern.methoden["markdown.name"](dokument_id=dok)
    assert name["name"] == "05_Klageschrift.md"
    md = markdown_export.dokument(kern.akten, dok)["markdown"]
    assert md.startswith("# 05_Klageschrift.md\n")
    assert "- Akte: Brückner ./. Autohaus" in md and "- SHA-256 des Originals: " in md
    assert f"(1) {KLAGE}" in md and "(2) Der Beklagte schuldet Ersatz." in md


def test_absaetze_seiten_tabellen_fussnoten():
    md = "\n".join(markdown_export._absaetze([
        {"seite": 1, "rn": None, "art": "absatz", "text": "Vertrag"},
        {"seite": 1, "rn": None, "art": "tabelle", "text": "Leistung | Preis"},
        {"seite": 1, "rn": None, "art": "tabelle", "text": "Wartung | 20 €"},
        {"seite": 2, "rn": 3, "art": "absatz", "text": "Die Kündigung ist schriftlich zu erklären."},
        {"seite": 2, "rn": None, "art": "fussnote", "text": "1 Siehe § 568 BGB."},
    ]))
    assert md == ("[S. 1]\n\nVertrag\n\n| Leistung | Preis |\n| --- | --- |\n| Wartung | 20 € |\n\n[S. 2]\n\n"
                  "[Rn. 3] Die Kündigung ist schriftlich zu erklären.\n\n> Fußnote: 1 Siehe § 568 BGB.\n")


def test_urteil_selbst_ergaenzt(kern, tmp_path):
    datei = tmp_path / "juris-ausdruck.txt"
    datei.write_text(AUSDRUCK, encoding="utf-8")
    u = urteile.ergaenzen(kern.akten, None, datei, tmp_path / "ablage", gericht="BGH", aktenzeichen="VIII ZR 999/20",
                          datum="2021-03-17", ocr=False, art="Urteil")
    erg = markdown_export.urteil(kern.akten, u["urteil_id"])
    md = erg["markdown"]
    assert md.startswith("# BGH, Urteil vom 17.03.2021 – VIII ZR 999/20\n")
    assert "- Aktenzeichen: VIII ZR 999/20" in md and "- Quelle: Eigene Datei" in md
    assert "(1) Die Klägerin verlangt die Rückabwicklung eines Kaufvertrags." in md
    assert erg["name"] == "BGH Urteil 2021-03-17 VIII ZR 999-20.md"


def test_urteil_aus_rechtsprechung_im_internet(kern, tmp_path):
    a = akte.akte_anlegen(kern.akten, "Brückner")
    (tmp_path / "05_Klage.md").write_text(f"(13) {KLAGE}", encoding="utf-8")
    akte.importiere(kern.akten, kern.con, a["id"], tmp_path / "05_Klage.md", tmp_path / "ablage", ocr=False)
    daten = (FIXTURES / "rii_toc_auszug.xml").read_bytes()
    verzeichnis.importiere(kern.con, daten, "test", *verzeichnis.archiviere(daten, tmp_path / "archiv"))
    akte.zitate_neu_pruefen(kern.akten, kern.con, a["id"])
    urteile.volltexte_laden(kern.akten, kern.con, a["id"], tmp_path / "archiv", lambda doknr: _zip_auszug())
    bgh = next(e for e in akte.rechtsprechung(kern.akten, kern.con, a["id"]) if e["status"] == "belegt")

    r = kern.methoden["markdown.speichern"](pfad=str(tmp_path / "bgh.md"), urteil_id=bgh["urteil"]["id"])
    md = (tmp_path / "bgh.md").read_text(encoding="utf-8")
    assert r["pfad"].endswith("bgh.md")
    assert md.startswith("# BGH 8. Zivilsenat, Urteil vom 12.10.2016 – VIII ZR 103/15\n")
    assert "- Quelle: Rechtsprechung im Internet" in md and "- Akte: Brückner" in md
    assert "## Leitsatz\n" in md and "## Tenor\n" in md and "## Entscheidungsgründe\n" in md
    assert "[Rn. 22] bb) Die (bisherige) Rechtsprechung" in md


def test_kommandozeile_wie_das_skript(tmp_path, capsys):
    from juracore.__main__ import main

    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("BJNR000000001.xml", (FIXTURES / "gii_markdown_auszug.xml").read_bytes())
    (tmp_path / "xml.zip").write_bytes(puffer.getvalue())
    assert main(["--db", str(tmp_path / "w.sqlite"), "gii2md", str(tmp_path / "xml.zip")]) == 0
    ziel = tmp_path / "MustG_Gesetz-ueber-die-Pruefung-von-Mustertexten_Stand-2026-10-09.md"
    assert ziel.read_text(encoding="utf-8") == (FIXTURES / "markdown" / "gii_markdown_auszug.md").read_text(
        encoding="utf-8")
    assert main(["--db", str(tmp_path / "w.sqlite"), "gii2md", str(FIXTURES / "bgb_auszug.xml"),
                 str(tmp_path / "bgb.md"), "--pruefen"]) == 0
    assert "PRÜFUNG: vollständig" in capsys.readouterr().out
