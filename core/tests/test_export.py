"""Ausgabe der KI-Ergebnisse als Markdown, Text, Word, PDF und Excel sowie zum Drucken."""

from __future__ import annotations

import json
import re
import zipfile
from datetime import UTC, datetime
from xml.etree import ElementTree

import pypdfium2 as pdfium
import pytest

from juracore import ausgabe, rpc
from juracore.ausgabe import Bericht, Eintrag, Ueberschrift, pdf
from juracore.dokumente import akte
from juracore.ki import export, speicher

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def fundstelle(dok_id, dateiname, seite, rn, wert, partei, treffer="woertlich"):
    return {"dokument_id": dok_id, "dateiname": dateiname, "abschnitt": 3, "seite": seite, "rn": rn,
            "parteien": [partei], "treffer": treffer,
            "ausschnitt": {"davor": "… davor ", "wert": wert, "danach": " danach …"}}


@pytest.fixture
def kern(tmp_path, con):
    k = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    a = akte.akte_anlegen(k.akten, "Brückner ./. Autohaus")
    ids = []
    for name in ("05_Klageschrift.md", "06_Klageerwiderung.md"):
        pfad = tmp_path / name
        pfad.write_text(f"Text von {name}.", encoding="utf-8")
        ids.append(akte.importiere(k.akten, con, a["id"], pfad, tmp_path / "ablage", ocr=False)["dokument_id"])
    k.test_akte, k.test_dokumente = a["id"], ids
    modell = k.aktives_modell()
    kl = fundstelle(ids[0], "05_Klageschrift.md", 3, 12, "am 27.06.2025 besichtigt", "Kläger")
    be = fundstelle(ids[1], "06_Klageerwiderung.md", 2, None, "=erst am 30.06.2025 → besichtigt", "Beklagter",
                    "angenaehert")
    dokumente = [{"dokument_id": i, "dateiname": n} for i, n in zip(ids, ("05", "06"), strict=True)]
    jetzt = "2026-10-23T09:05:00+00:00"
    speicher.schreibe(k.akten, "w", "widersprueche", modell, {
        "modell": "gemma", "erstellt_am": jetzt, "angaben": 12, "verworfen": 1,
        "dokumente": [{**d, "angaben": 6, "verworfen": 0} for d in dokumente],
        "widersprueche": [{"thema": "Tag der Besichtigung", "art": "widerspruch", "erklaerung": "Datum weicht ab.",
                           "einordnung": ["zwischen_parteien"],
                           "angaben": [{"text": "Besichtigung am 27.06.", "haltung": "behauptet", "fundstelle": kl},
                                       {"text": "Besichtigung am 30.06.", "haltung": "bestritten", "fundstelle": be}]}],
    }, akte_id=a["id"])
    speicher.schreibe(k.akten, "c", "chronologie", modell, {
        "modell": "gemma", "erstellt_am": jetzt, "angaben": 2, "verworfen": 0, "dokumente": dokumente,
        "ereignisse": [{"datum": "2025-06-27", "anzeige": "27.06.2025", "art": "ereignis", "ereignis": "Besichtigung",
                        "streitig": True, "status": "belegt",
                        "quellen": [{"text": "Besichtigung am 27.06.", "haltung": "behauptet", "fundstelle": kl}]}],
    }, akte_id=a["id"])
    speicher.schreibe(k.akten, "z", "zusammenfassung_akte", modell, {
        "modell": "gemma", "erstellt_am": jetzt, "dokumente": dokumente[:1], "zaehlung": {"belegt": 1, "ohne_beleg": 1},
        "aussagen": [{"text": "Der Kläger verlangt Rücktritt (§ 437 BGB).", "art": "vortrag", "status": "belegt",
                      "fundstellen": [kl]},
                     {"text": "Erfundene Aussage.", "art": "sonstiges", "status": "ohne_beleg", "fundstellen": []}],
    }, akte_id=a["id"])
    speicher.schreibe(k.akten, "d", "zusammenfassung_dokument", modell, {
        "modell": "gemma", "erstellt_am": jetzt, "zaehlung": {"belegt": 1, "ohne_beleg": 0},
        "aussagen": [{"text": "Klage auf Rückzahlung.", "art": "antrag", "status": "belegt", "fundstellen": [kl]}],
    }, akte_id=a["id"], dokument_id=ids[0])
    return k


def bericht(kern, **kw):
    return export.bericht(kern.akten, kern.test_akte, kern.aktives_modell(), jetzt=datetime(2026, 10, 23, 11, 0,
                                                                                         tzinfo=UTC), **kw)


def test_markdown_mit_fundstellen_und_ohne_beleg(kern):
    md = ausgabe.schreiben(bericht(kern), "md").decode()
    assert md.startswith("# KI-Auswertung: Brückner ./. Autohaus")
    assert "## Widersprüche" in md and "## Chronologie" in md and "## Zusammenfassung der Akte" in md
    assert "### 05\\_Klageschrift.md" in md  # Zusammenfassung je Dokument
    assert "05\\_Klageschrift.md, S. 3, Rn. 12 (Kläger): „am 27.06.2025 besichtigt“" in md
    assert "06\\_Klageerwiderung.md, S. 2 (Beklagter) (Zitat angenähert)" in md
    assert "Erfundene Aussage. *(ohne Beleg)*" in md
    assert "Einschätzung des Modells: Datum weicht ab." in md
    assert "*(streitig)*" in md
    # Die Chronologie entstand aus beiden Dokumenten, die Zusammenfassung der Akte nur aus einem: veraltet.
    assert md.count("Die Dokumente der Akte haben sich seitdem geändert") == 1
    assert "| Ausgegeben am | 23.10.2026, 11:00 |" in md and "| Sprachmodell | gemma |" in md
    assert "(1 Angabe ohne auffindbares Zitat verworfen)" in md


def test_text_ohne_zitate_und_nur_gewaehlte_teile(kern):
    txt = ausgabe.schreiben(bericht(kern, teile=["chronologie"], zitate=False), "txt").decode()
    assert "Chronologie\n-----------" not in txt and "Chronologie\n===========" in txt
    assert "Widersprüche" not in txt and "Zusammenfassung der Akte" not in txt
    assert "27.06.2025 – Besichtigung [streitig]" in txt
    assert "- Besichtigung am 27.06. (behauptet) – 05_Klageschrift.md, S. 3, Rn. 12 (Kläger)" in txt
    assert "besichtigt“" not in txt


def test_ohne_ergebnisse_gibt_es_nichts_auszugeben(kern):
    leer = akte.akte_anlegen(kern.akten, "Leer")
    with pytest.raises(ValueError, match="noch keine Ergebnisse"):
        export.bericht(kern.akten, leer["id"], kern.aktives_modell())
    with pytest.raises(ValueError, match="Unbekannter Teil"):
        bericht(kern, teile=["chat"])


def test_word_datei(kern):
    daten = ausgabe.schreiben(bericht(kern), "docx")
    with zipfile.ZipFile(__import__("io").BytesIO(daten)) as z:
        assert {"[Content_Types].xml", "word/document.xml", "word/styles.xml", "word/footer1.xml"} <= set(z.namelist())
        dokument = ElementTree.fromstring(z.read("word/document.xml"))
        ElementTree.fromstring(z.read("word/styles.xml"))
        assert "NUMPAGES" in z.read("word/footer1.xml").decode()
    absaetze = ["".join(t.text or "" for t in p.iter(f"{W}t")) for p in dokument.iter(f"{W}p")]
    assert "KI-Auswertung: Brückner ./. Autohaus" in absaetze
    assert any(a.startswith("Besichtigung am 30.06. (bestreitet) – 06_Klageerwiderung.md, S. 2 (Beklagter) "
                            "(Zitat angenähert): „=erst am 30.06.2025 → besichtigt“") for a in absaetze)
    stile = {p.find(f"{W}pPr/{W}pStyle").get(f"{W}val") for p in dokument.iter(f"{W}p")
             if p.find(f"{W}pPr/{W}pStyle") is not None}
    assert {"Titel", "Ueberschrift1", "Ueberschrift2", "Ueberschrift3", "Beleg", "Kopf"} <= stile


def _blaetter(daten: bytes) -> dict[str, list[list[str]]]:
    with zipfile.ZipFile(__import__("io").BytesIO(daten)) as z:
        mappe = ElementTree.fromstring(z.read("xl/workbook.xml"))
        namen = [s.get("name") for s in mappe.iter(f"{S}sheet")]
        aus = {}
        for i, name in enumerate(namen, start=1):
            blatt = ElementTree.fromstring(z.read(f"xl/worksheets/sheet{i}.xml"))
            aus[name] = [["".join(t.text or "" for t in c.iter(f"{S}t")) or (c.findtext(f"{S}v") or "")
                          for c in r.iter(f"{S}c")] for r in blatt.iter(f"{S}row")]
        return aus


def test_excel_je_teil_ein_blatt(kern):
    blaetter = _blaetter(ausgabe.schreiben(bericht(kern), "xlsx"))
    assert list(blaetter) == ["Übersicht", "Widersprüche", "Chronologie", "Zusammenfassung Akte",
                              "Zusammenfassungen Dokumente"]
    w = blaetter["Widersprüche"]
    assert w[0][-1] == "Zitat aus dem Dokument" and len(w) == 3
    assert w[2][7:] == ["06_Klageerwiderung.md", "S. 2", "Beklagter", "=erst am 30.06.2025 → besichtigt"]
    assert blaetter["Chronologie"][1][:6] == ["2025-06-27", "27.06.2025", "Ereignis", "Besichtigung", "ja", "ja"]
    z = blaetter["Zusammenfassung Akte"]
    assert z[2][:4] == ["2", "Sonstiges", "Erfundene Aussage.", "nein"]
    assert ["Akte", "Brückner ./. Autohaus"] in blaetter["Übersicht"]
    ohne = _blaetter(ausgabe.schreiben(bericht(kern, zitate=False), "xlsx"))
    assert "Zitat aus dem Dokument" not in ohne["Widersprüche"][0]


def _pdf_text(daten: bytes) -> list[str]:
    doc = pdfium.PdfDocument(daten)
    try:
        return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
    finally:
        doc.close()


def test_pdf_mit_umlauten_und_seitenzahl(kern):
    seiten = _pdf_text(ausgabe.schreiben(bericht(kern), "pdf"))
    text = " ".join(" ".join(s.split()) for s in seiten)
    assert "KI-Auswertung: Brückner ./. Autohaus" in text
    assert "05_Klageschrift.md, S. 3, Rn. 12 (Kläger): „am 27.06.2025 besichtigt“" in text
    assert "=erst am 30.06.2025 -> besichtigt" in text  # Pfeil liegt außerhalb von WinAnsi
    assert "§ 437 BGB" in text and "[ohne Beleg]" in text
    assert f"Seite 1 von {len(seiten)}" in seiten[0]


def test_pdf_bricht_um_und_beginnt_neue_seiten():
    lang = "Ein sehr langer Satz mit Fundstelle und Zitat, der umbrochen werden muss. " * 6
    b = Bericht("Langer Bericht", [Ueberschrift("Teil")] + [
        Eintrag(f"Aussage {i}: {lang}", f"{i}.", kompakt=True, belege=[ausgabe.Beleg("Dok.pdf, S. 1", "Zitat")])
        for i in range(1, 60)] + [Eintrag("Wortohneleerzeichen" * 30, "60.")])
    seiten = _pdf_text(pdf.schreiben(b))
    assert len(seiten) > 3
    assert all(f"Seite {n} von {len(seiten)}" in s for n, s in enumerate(seiten, start=1))
    text = re.sub(r"\s+", "", "".join(seiten))
    assert "Aussage59:" in text and ("Wortohneleerzeichen" * 30) in text
    # Keine Zeile ragt über den rechten Rand.
    doc = pdfium.PdfDocument(pdf.schreiben(b))
    try:
        for i in range(len(doc)):
            seite = doc[i].get_textpage()
            for n in range(seite.count_rects()):
                links, _, rechts, _ = seite.get_rect(n)
                assert links >= pdf.LINKS - 1 and rechts <= pdf.BREITE - pdf.RECHTS + 1
    finally:
        doc.close()


def test_rpc_schreibt_datei_und_liefert_druckansicht(kern, tmp_path):
    def aufruf(methode, **params):
        antwort = kern.bearbeite(json.dumps({"id": 1, "method": methode, "params": params}))
        assert "error" not in antwort, antwort
        return antwort["result"]

    name = aufruf("ki.export_name", akte_id=kern.test_akte)["name"]
    assert re.fullmatch(r"KI-Auswertung Brückner gg\. Autohaus \d{4}-\d{2}-\d{2}", name)
    r = aufruf("ki.export", akte_id=kern.test_akte, format="md", pfad=str(tmp_path / "bericht"))
    assert r["pfad"].endswith("bericht.md") and (tmp_path / "bericht.md").read_text(encoding="utf-8").startswith("#")
    druck = aufruf("ki.export_druck", akte_id=kern.test_akte, teile=["widersprueche"])
    assert '<div class="druckbericht">' in druck["html"] and "&lt;" not in druck["titel"]
    assert "Tag der Besichtigung" in druck["html"] and "Chronologie" not in druck["html"]
    fehler = kern.bearbeite(json.dumps({"id": 2, "method": "ki.export", "params": {
        "akte_id": kern.test_akte, "format": "exe", "pfad": str(tmp_path / "x")}}))
    assert "Unbekanntes Format" in fehler["error"]["message"]


def test_html_maskiert_inhalte():
    b = Bericht("<Titel>", [Eintrag("<script>alert(1)</script>", belege=[ausgabe.Beleg("a & b", "<i>")])])
    html = ausgabe.schreiben(b, "html").decode()
    assert "<script>" not in html and "&lt;script&gt;" in html and "„&lt;i&gt;“" in html


def test_pdf_mit_zeichen_ausserhalb_von_winansi():
    """Namen wie „Şahin“ oder „Łukasz“ bleiben erhalten: Die Schrift wird als Teilmenge eingebettet."""
    b = Bericht("Fristenbuch Şahin ./. Dąbrowski", [
        Ueberschrift("Beteiligte"),
        Eintrag("Frist für Gökhan Çelik", "1.", kompakt=True,
                belege=[ausgabe.Beleg("Dok.pdf, S. 2", "Jiří Dvořák und Ștefan Popescu", vorab="Zeuge")]),
        Eintrag("Chinesisch 中文", "2."),
    ])
    daten = pdf.schreiben(b)
    text = " ".join(_pdf_text(daten))
    for name in ("Şahin", "Dąbrowski", "Gökhan Çelik", "Jiří Dvořák", "Ștefan Popescu", "Seite 1 von 1"):
        assert name in text
    assert "Chinesisch ??" in text  # fehlt in der Schrift: Fragezeichen statt leerer Stelle
    assert b"/FontFile2" in daten and b"+LiberationSans-Bold" in daten and b"/Helvetica" not in daten
    assert len(daten) < 150_000  # nur die benutzten Glyphen


def test_pdf_ohne_sonderzeichen_bleibt_bei_standardschriften():
    daten = pdf.schreiben(Bericht("Brückner ./. Autohaus", [Ueberschrift("Fristen"), Eintrag("Frist § 276 ZPO", "1.")]))
    assert b"/Helvetica" in daten and b"/FontFile2" not in daten
