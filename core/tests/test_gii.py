from pathlib import Path

from juracore.gesetze.gii import parse_gii_xml

FIXTURES = Path(__file__).parent / "fixtures"


def bgb():
    return parse_gii_xml((FIXTURES / "bgb_auszug.xml").read_bytes())


def norm(dok, bez):
    return next(n for n in dok.normen if n.bezeichnung == bez)


def test_stammdaten():
    dok = bgb()
    assert dok.abk == "BGB"
    assert dok.langtitel == "Bürgerliches Gesetzbuch"
    assert dok.builddate == "20260901120000"
    assert any("Zuletzt geändert" in s for s in dok.stand)


def test_gliederung_folgt_kennzahl():
    dok = bgb()
    assert norm(dok, "§ 1").gliederung == ["Buch 1 Allgemeiner Teil", "Abschnitt 1 Personen"]
    assert norm(dok, "§ 195").gliederung == ["Buch 1 Allgemeiner Teil", "Abschnitt 5 Verjährung"]
    assert norm(dok, "§ 280").gliederung == ["Buch 2 Recht der Schuldverhältnisse"]


def test_absaetze_und_saetze():
    n = norm(bgb(), "§ 280")
    assert n.typ == "paragraph" and n.nummer == "280"
    assert [a.nr for a in n.absaetze] == ["1", "2", "3"]
    abs1 = n.absaetze[0]
    assert abs1.text.startswith("Verletzt der Schuldner")
    assert [s.nr for s in abs1.saetze] == [1, 2]
    assert abs1.saetze[1].text == "Dies gilt nicht, wenn der Schuldner die Pflichtverletzung nicht zu vertreten hat."
    # "des § 286 verlangen." ist ein Satz, kein Satzende nach "§".
    assert len(n.absaetze[1].saetze) == 1


def test_norm_ohne_absatznummer():
    n = norm(bgb(), "§ 1")
    assert len(n.absaetze) == 1 and n.absaetze[0].nr is None
    assert n.absaetze[0].saetze[0].text == "Die Rechtsfähigkeit des Menschen beginnt mit der Vollendung der Geburt."


def test_aufzaehlung_bleibt_im_einleitenden_satz():
    n = norm(bgb(), "§ 199")
    abs1 = n.absaetze[0]
    assert len(abs1.saetze) == 1
    assert [nr for nr, _ in abs1.saetze[0].nummern] == ["1", "2"]
    assert "\n1. der Anspruch entstanden ist und" in abs1.text


def test_weggefallen():
    assert norm(bgb(), "§ 1300").weggefallen
    assert not norm(bgb(), "§ 280").weggefallen


def test_html_entitaeten_und_fussnotenmarker():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE dokumente SYSTEM "http://www.gesetze-im-internet.de/dtd/1.01/gii-norm.dtd">
<dokumente><norm><metadaten><jurabk>XG</jurabk><enbez>§ 1</enbez></metadaten>
<textdaten><text><Content><P>(1) Satz&nbsp;eins<SUP class="Rec">1)</SUP>.</P></Content></text></textdaten></norm></dokumente>"""
    dok = parse_gii_xml(xml)
    assert dok.normen[0].absaetze[0].text == "Satz eins."


def test_egbgb_artikel_als_gliederungseinheit():
    dokument = parse_gii_xml((FIXTURES / "egbgb_auszug.xml").read_bytes())
    assert dokument.abk == "BGBEG"
    assert [(n.bezeichnung, n.typ, n.nummer) for n in dokument.normen] == [
        ("Art 1", "artikel", "1"),
        ("Art 229 § 6", "artikel", "229 § 6"),
    ]
    art1, par6 = dokument.normen
    assert art1.gliederung == ["Erster Teil Allgemeine Vorschriften"]
    assert [a.nr for a in art1.absaetze] == ["1", "2"]
    assert par6.titel == "Überleitungsvorschrift zum Verjährungsrecht"
    assert par6.gliederung == ["Fünfter Teil Übergangsvorschriften", "Art 229 Weitere Überleitungsvorschriften"]
    assert len(par6.absaetze[0].saetze) == 2
