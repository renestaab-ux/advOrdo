"""Schriftstücke aus der Akte: Platzhalter, Rubrum, Füllen von Word-Vorlagen, Grundvorlagen und eigene Vorlagen."""

from __future__ import annotations

import io
import struct
import zipfile
import zlib
from datetime import date
from pathlib import Path
from xml.etree import ElementTree

import pytest

from juracore import rpc
from juracore.aktenverwaltung import beteiligte, stammdaten, verfahren
from juracore.dokumente import akte
from juracore.eigene import daten as eigene
from juracore.schriftstuecke import fuellen, grundvorlagen, platzhalter, vorlagen

PROFILE = Path(__file__).parents[2] / "testdaten" / "eigene-daten"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
HEUTE = date(2026, 10, 27)


@pytest.fixture
def kern(tmp_path, con):
    k = rpc.Kern(tmp_path / "wissen.sqlite", tmp_path / "archiv")
    eigene.importieren(k.akten, PROFILE / "kanzlei.json")
    a = akte.akte_anlegen(k.akten, "Brückner ./. Autohaus Rehnfeld")
    aid = a["id"]
    stammdaten.speichern(k.akten, aid, {"gegenstand": "Rücktritt vom Kaufvertrag", "gegenstandswert": "18.450,00",
                                        "eigene_rolle": "Prozessbevollmächtigter des Klägers"})
    stammdaten.vergeben(k.akten, aid, "12/26")
    m = beteiligte.speichern(k.akten, "person", {"anrede": "Frau", "titel": "Dr.", "vorname": "Lena",
                                                 "nachname": "Brückner", "strasse": "Talstraße 4", "plz": "79102",
                                                 "ort": "Freiburg im Breisgau"})
    g = beteiligte.speichern(k.akten, "organisation", {"name": "Autohaus Rehnfeld", "rechtsform": "GmbH",
                                                       "strasse": "Industriestraße 12", "plz": "79108",
                                                       "ort": "Freiburg im Breisgau"},
                             vertreter=[{"anrede": "Herr", "vorname": "Max", "nachname": "Rehnfeld",
                                         "funktion": "Geschäftsführer"}])
    gv = beteiligte.speichern(k.akten, "organisation", {"name": "Kanzlei Vogt & Partner", "kategorie": "Kanzlei",
                                                        "strasse": "Bertoldstraße 1", "plz": "79098",
                                                        "ort": "Freiburg im Breisgau"})
    stammdaten.beteiligung_hinzufuegen(k.akten, aid, "mandant", beteiligter_id=m["id"])
    stammdaten.beteiligung_hinzufuegen(k.akten, aid, "gegner", beteiligter_id=g["id"])
    stammdaten.beteiligung_hinzufuegen(k.akten, aid, "bevollmaechtigter_gegner", beteiligter_id=gv["id"],
                                       aktenzeichen="V-77/25")
    verfahren.speichern(k.akten, aid, {"art": "klage", "gericht": "Landgericht Freiburg im Breisgau",
                                       "spruchkoerper": "2. Zivilkammer", "aktenzeichen": "2 O 233/26"},
                        gericht_daten={"strasse": "Salzstraße 17", "plz": "79098", "ort": "Freiburg im Breisgau"})
    k.test_akte = aid
    k.test_bet = {b["rolle"]: b["id"] for b in stammdaten.beteiligungen(k.akten, aid)}
    return k


def werte(kern, rolle=None):
    return platzhalter.werte(kern.akten, kern.test_akte, kern.test_bet.get(rolle), heute=HEUTE)["werte"]


def test_absender_bearbeiter_und_akte(kern):
    w = werte(kern)
    assert w["Absender.Name"] == "Albrecht Tiedemann Rechtsanwälte"
    assert w["Absender.Zeile"] == ("Albrecht Tiedemann Rechtsanwälte · Kaiser-Joseph-Straße 300 · "
                                   "79098 Freiburg im Breisgau")
    assert "Sophie Albrecht, Rechtsanwältin, Fachanwältin für Verkehrsrecht" in w["Absender.Berufsträger"]
    assert "Martin Tiedemann, Rechtsanwalt, Fachanwalt für Bau- und Architektenrecht" in w["Absender.Berufsträger"]
    assert w["Absender.Kontakt"].startswith("Telefon 0761 000000-0 · kanzlei@")
    assert w["Bearbeiter.Name"] == "Sophie Albrecht"
    assert w["Bearbeiter.Telefon"] == "0761 000000-0"  # keine Durchwahl: Telefon der Kanzlei
    assert w["Akte.Aktenzeichen"] == "12/26"
    assert w["Akte.Gegenstandswert"] == "18.450,00 €"
    assert w["Datum"] == "27. Oktober 2026" and w["Datum.Kurz"] == "27.10.2026"
    assert w["Datum.Ort"] == "Freiburg im Breisgau, 27. Oktober 2026"


def test_empfaenger_anschrift_und_anrede(kern):
    w = werte(kern, "mandant")
    assert w["Empfänger.Anschrift"] == "Frau\nDr. Lena Brückner\nTalstraße 4\n79102 Freiburg im Breisgau"
    assert w["Empfänger.Anrede"] == "Sehr geehrte Frau Dr. Brückner,"
    w = werte(kern, "bevollmaechtigter_gegner")
    assert w["Empfänger.Anrede"] == "Sehr geehrte Kolleginnen und Kollegen,"
    assert w["Empfänger.Zeichen"] == "V-77/25"
    w = werte(kern, "gericht")
    assert w["Empfänger.Anschrift"] == ("Landgericht Freiburg im Breisgau\n2. Zivilkammer\nSalzstraße 17\n"
                                        "79098 Freiburg im Breisgau")
    assert w["Empfänger.Zeichen"] == "2 O 233/26"
    assert w["Empfänger.Anrede"] == "Sehr geehrte Damen und Herren,"


def test_rubrum(kern):
    w = werte(kern)
    r = w["Rubrum"].split("\n")
    assert r[0] == "In dem Rechtsstreit"
    assert r[2] == "Dr. Lena Brückner, Talstraße 4, 79102 Freiburg im Breisgau"
    assert r[3] == "\t– Klägerin –"
    assert r[4].startswith("Prozessbevollmächtigte: Albrecht Tiedemann Rechtsanwälte, Kaiser-Joseph-Straße 300")
    assert "gegen" in r
    assert ("Autohaus Rehnfeld GmbH, vertreten durch den Geschäftsführer Max Rehnfeld, Industriestraße 12, "
            "79108 Freiburg im Breisgau") in r
    assert "\t– Beklagte –" in r
    assert r[-1] == "wegen Rücktritt vom Kaufvertrag"
    assert w["Rubrum.Kurz"] == "Brückner ./. Autohaus Rehnfeld GmbH"
    assert w["Gegner.Vertreter"] == "vertreten durch den Geschäftsführer Max Rehnfeld"


def test_rubrum_beklagtenseite_und_antragsverfahren(kern):
    stammdaten.speichern(kern.akten, kern.test_akte, {"eigene_rolle": "Prozessbevollmächtigter des Beklagten"})
    w = werte(kern)
    assert w["Rubrum"].index("Autohaus") < w["Rubrum"].index("Brückner")
    assert "\t– Beklagte –" in w["Rubrum"] and "\t– Klägerin –" in w["Rubrum"]
    assert w["Rubrum.Kurz"] == "Autohaus Rehnfeld GmbH ./. Brückner"
    v = verfahren.speichern(kern.akten, kern.test_akte, {"art": "eilverfahren", "gericht": "Amtsgericht Freiburg"})
    eil = next(x for x in v if x["art"] == "eilverfahren")
    w = platzhalter.werte(kern.akten, kern.test_akte, verfahren_id=eil["id"], heute=HEUTE)["werte"]
    assert w["Rubrum"].startswith("In dem Verfahren")
    assert "\t– Antragsgegnerin –" in w["Rubrum"] and "\t– Antragstellerin –" in w["Rubrum"]
    assert w["Gericht.Name"] == "Amtsgericht Freiburg"


def test_ohne_prozessrolle_hinweis(kern):
    stammdaten.speichern(kern.akten, kern.test_akte, {"eigene_rolle": ""})
    hinweise = platzhalter.werte(kern.akten, kern.test_akte, heute=HEUTE)["hinweise"]
    assert any("Prozessrolle" in h for h in hinweise)


def test_platzhalter_schreibweisen():
    assert platzhalter.bekannt("empfaenger.anschrift") == "Empfänger.Anschrift"
    assert platzhalter.bekannt(" Bearbeiter.EMail ") == "Bearbeiter.E-Mail"
    assert platzhalter.bekannt("Gericht.Spruchkoerper") == "Gericht.Spruchkörper"
    assert platzhalter.bekannt("Mandant.Telefonnummer") is None


# --------------------------------------------------------------------------- Word-Dateien füllen


def docx(dokument_xml: str, typ: str = fuellen.DOKUMENT_TYP, makro: bool = False) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("[Content_Types].xml", f'<Types><Override PartName="/word/document.xml" ContentType="{typ}"/>'
                                          "</Types>")
        z.writestr("word/document.xml", dokument_xml)
        if makro:
            z.writestr("word/vbaProject.bin", b"")
    return puffer.getvalue()


KOPF = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'


def text_absaetze(daten: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        wurzel = ElementTree.fromstring(z.read("word/document.xml"))
    ergebnis = []
    for p in wurzel.iter(f"{W}p"):
        t = ""
        for e in p.iter():
            if e.tag == f"{W}t":
                t += e.text or ""
            elif e.tag == f"{W}br":
                t += "\n"
            elif e.tag == f"{W}tab":
                t += "\t"
        ergebnis.append(t)
    return ergebnis


def test_platzhalter_ueber_mehrere_laeufe():
    xml = (KOPF + '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>An {{Man</w:t></w:r><w:proofErr w:type="spellStart"/>'
           '<w:r><w:t>dant.</w:t></w:r><w:r><w:t xml:space="preserve">Name}} &amp; Co</w:t></w:r></w:p>'
           "<w:p><w:r><w:t>{{Empfänger.Anschrift}}</w:t></w:r></w:p>"
           "<w:p><w:r><w:t>{{Tippfehler.Name}} bleibt</w:t></w:r></w:p></w:body></w:document>")
    daten = docx(xml)
    assert fuellen.platzhalter_finden(daten) == ["Mandant.Name", "Empfänger.Anschrift", "Tippfehler.Name"]
    werte_ = {"Mandant.Name": "Müller <GmbH>", "Empfänger.Anschrift": "Frau\nLena\tB."}
    neu = fuellen.fuellen(daten, lambda p: werte_.get(p.strip()) if p.strip() in werte_ else None)
    assert text_absaetze(neu) == ["An Müller <GmbH> & Co", "Frau\nLena\tB.", "{{Tippfehler.Name}} bleibt"]
    with zipfile.ZipFile(io.BytesIO(neu)) as z:
        dok = z.read("word/document.xml").decode()
    # Der Wert steht im ersten Lauf und ist dort fett; die übrigen Läufe des Platzhalters sind leer.
    assert '<w:rPr><w:b/></w:rPr><w:t xml:space="preserve">An Müller &lt;GmbH&gt;</w:t>' in dok
    assert '<w:proofErr w:type="spellStart"/>' in dok


def test_dotx_wird_dokument_und_makros_abgelehnt():
    xml = KOPF + "<w:p><w:r><w:t>{{Datum}}</w:t></w:r></w:p></w:body></w:document>"
    neu = fuellen.fuellen(docx(xml, fuellen.VORLAGE_TYP), lambda p: "heute")
    with zipfile.ZipFile(io.BytesIO(neu)) as z:
        assert fuellen.DOKUMENT_TYP in z.read("[Content_Types].xml").decode()
    with pytest.raises(fuellen.KeineVorlage):
        fuellen.platzhalter_finden(docx(xml, makro=True))
    with pytest.raises(fuellen.KeineVorlage):
        fuellen.platzhalter_finden(b"kein zip")


# --------------------------------------------------------------------------- Grundvorlagen


def png(breite: int, hoehe: int) -> bytes:
    def block(art: bytes, inhalt: bytes) -> bytes:
        return struct.pack(">I", len(inhalt)) + art + inhalt + struct.pack(">I", zlib.crc32(art + inhalt))

    zeilen = b"".join(b"\x00" + b"\x00\x00\x00" * breite for _ in range(hoehe))
    return (b"\x89PNG\r\n\x1a\n" + block(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 2, 0, 0, 0))
            + block(b"IDAT", zlib.compress(zeilen)) + block(b"IEND", b""))


def test_grundvorlagen_sind_gueltig_und_enthalten_logo(tmp_path):
    (tmp_path / "logo.png").write_bytes(png(400, 100))
    assert grundvorlagen.bildgroesse(png(400, 100)) == (400, 100)
    for art in grundvorlagen.GRUNDVORLAGEN:
        daten = grundvorlagen.erzeugen(art, grundvorlagen.logo_lesen(tmp_path))
        with zipfile.ZipFile(io.BytesIO(daten)) as z:
            for name in z.namelist():
                if name.endswith((".xml", ".rels")):
                    ElementTree.fromstring(z.read(name))  # wohlgeformt
            assert "word/media/logo.png" in z.namelist()
            assert 'Extension="png"' in z.read("[Content_Types].xml").decode()
            assert 'r:embed="rIdLogo"' in z.read("word/header1.xml").decode()
        gefunden = fuellen.platzhalter_finden(daten)
        assert all(platzhalter.bekannt(p) for p in gefunden), gefunden
    assert grundvorlagen.logo_hinweis(tmp_path) is None
    (tmp_path / "logo.png").unlink()
    (tmp_path / "logo.svg").write_text("<svg/>")
    assert "SVG" in grundvorlagen.logo_hinweis(tmp_path)


def test_brief_erzeugen_in_die_akte(kern, tmp_path):
    ergebnis = vorlagen.erzeugen(kern.akten, kern.con, tmp_path, kern.ablage, kern.test_akte, "grund:brief",
                                 kern.test_bet["bevollmaechtigter_gegner"], heute=HEUTE)
    assert ergebnis["dateiname"] == "2026-10-27 Brief an Kanzlei Vogt & Partner.docx"
    assert ergebnis["neu"] and ergebnis["unbekannt"] == []
    assert "Absender.Fax" not in ergebnis["leer"]  # steht nicht in der Grundvorlage
    assert "Absender.Register" not in ergebnis["leer"]  # bei einer GbR zu Recht leer
    dok = akte.dokument(kern.akten, ergebnis["dokument_id"])
    assert dok["dokument"]["herkunft"] == vorlagen.HERKUNFT
    text = "\n".join(a["text"] for a in dok["abschnitte"])
    assert "Kanzlei Vogt & Partner" in text and "Sehr geehrte Kolleginnen und Kollegen," in text
    assert "V-77/25" in text and "{{" not in text


def test_schriftsatz_unter_pfad_ohne_akte(kern, tmp_path):
    ziel = tmp_path / "ss.docx"
    ergebnis = vorlagen.erzeugen(kern.akten, kern.con, tmp_path, kern.ablage, kern.test_akte, "grund:schriftsatz",
                                 kern.test_bet["gericht"], pfad=ziel, in_akte=False, heute=HEUTE)
    assert "dokument_id" not in ergebnis and ziel.is_file()
    assert ergebnis["dateiname"] == "2026-10-27 Schriftsatz 2 O 233 26.docx"
    absaetze = text_absaetze(ziel.read_bytes())
    rubrum = next(a for a in absaetze if a.startswith("In dem Rechtsstreit"))
    assert "\t– Klägerin –" in rubrum and "wegen Rücktritt vom Kaufvertrag" in rubrum
    assert "Az.: 2 O 233/26" in absaetze


def test_vorschau_nennt_fehlende_angaben(kern, tmp_path):
    v = vorlagen.vorschau(kern.akten, tmp_path, kern.test_akte, "grund:brief", kern.test_bet["gegner"], heute=HEUTE)
    zeilen = {z["platzhalter"]: z for z in v["zeilen"]}
    assert zeilen["Empfänger.Anschrift"]["wert"].startswith("Autohaus Rehnfeld GmbH\nIndustriestraße 12")
    assert zeilen["Absender.Register"]["wert"] == "" and zeilen["Absender.Register"]["wo"] == ""
    v = vorlagen.vorschau(kern.akten, tmp_path, kern.test_akte, "grund:brief", heute=HEUTE)
    zeilen = {z["platzhalter"]: z for z in v["zeilen"]}
    assert zeilen["Empfänger.Anschrift"]["wo"] == "Empfänger wählen bzw. Beteiligte der Akte"


# --------------------------------------------------------------------------- Eigene Vorlagen


def test_eigene_vorlagen_verwalten_und_fuellen(kern, tmp_path):
    umgebung = tmp_path / "umgebung"
    quelle = tmp_path / "Mandantenbrief.docx"
    quelle.write_bytes(docx(KOPF + "<w:p><w:r><w:t>{{Mandant.Anrede}} {{Akte.Aktenzeichen}} {{Unbekannt}}</w:t>"
                                   "</w:r></w:p></w:body></w:document>"))
    r = vorlagen.hinzufuegen(umgebung, quelle)
    assert r["neu"] == "Mandantenbrief.docx" and r["pruefung"]["unbekannt"] == ["Unbekannt"]
    assert vorlagen.hinzufuegen(umgebung, quelle)["neu"] == "Mandantenbrief (2).docx"
    liste = vorlagen.liste(umgebung)
    assert [e["titel"] for e in liste["eigene"]] == ["Mandantenbrief", "Mandantenbrief (2)"]
    assert len(liste["grund"]) == 3
    ergebnis = vorlagen.erzeugen(kern.akten, kern.con, umgebung, kern.ablage, kern.test_akte,
                                 "eigen:Mandantenbrief.docx", in_akte=False, pfad=tmp_path / "x.docx", heute=HEUTE)
    assert ergebnis["unbekannt"] == ["Unbekannt"]
    assert text_absaetze((tmp_path / "x.docx").read_bytes()) == ["Sehr geehrte Frau Dr. Brückner, 12/26 {{Unbekannt}}"]
    vorlagen.entfernen(umgebung, "Mandantenbrief (2).docx")
    assert len(vorlagen.liste(umgebung)["eigene"]) == 1
    with pytest.raises(LookupError):
        vorlagen.entfernen(umgebung, "../wissen.sqlite")
    leer = tmp_path / "kaputt.docx"
    leer.write_bytes(b"nein")
    with pytest.raises(ValueError):
        vorlagen.hinzufuegen(umgebung, leer)


def test_rpc(kern, tmp_path):
    m = kern.methoden
    assert any(e["platzhalter"] == "Rubrum" for e in m["schriftstuecke.katalog"]())
    assert [v["id"] for v in m["schriftstuecke.vorlagen"]()["grund"]] == [
        "grund:brief", "grund:schriftsatz", "grund:kurzrubrum"]
    ergebnis = m["schriftstuecke.erzeugen"](akte_id=kern.test_akte, vorlage="grund:kurzrubrum",
                                             empfaenger_id=kern.test_bet["gericht"])
    assert ergebnis["dokument_id"]
    ziel = tmp_path / "Grundvorlage.docx"
    m["schriftstuecke.grundvorlage_speichern"](vorlage="grund:brief", pfad=str(ziel))
    assert "Empfänger.Anschrift" in fuellen.platzhalter_finden(ziel.read_bytes())
