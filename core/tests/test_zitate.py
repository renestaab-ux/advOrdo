from juracore.gesetze.zitate import finde_zitate, parse_zitat


def test_vollstaendiges_zitat():
    z = parse_zitat("§ 280 Abs. 1 S. 2 BGB")
    assert (z.gesetz, z.nummer, z.absatz, z.satz, z.nr) == ("BGB", "280", "1", 2, None)
    assert str(z) == "§ 280 Abs. 1 S. 2 BGB"


def test_ausgeschriebene_form_und_nummer():
    z = parse_zitat("§ 253 Absatz 2 Nummer 2 ZPO")
    assert (z.nummer, z.absatz, z.nr, z.gesetz) == ("253", "2", "2", "ZPO")


def test_mehrere_paragraphen():
    zitate = finde_zitate("Der Anspruch folgt aus §§ 280 Abs. 1, 281 BGB und § 823 Abs. 2 BGB.")
    assert [str(z) for z in zitate] == ["§ 280 Abs. 1 BGB", "§ 281 BGB", "§ 823 Abs. 2 BGB"]


def test_buchstabenparagraph_und_ff():
    assert str(parse_zitat("§ 312g BGB")) == "§ 312g BGB"
    assert str(parse_zitat("§§ 194 ff. BGB")) == "§ 194 BGB"


def test_gesetze_mit_gemischter_schreibweise():
    assert parse_zitat("§ 15 InsO").gesetz == "InsO"
    assert parse_zitat("Art. 3 GG").zeichen == "Art."


def test_position_im_text():
    text = "vgl. § 286 ZPO"
    z = finde_zitate(text)[0]
    assert text[z.fundstelle_im_text[0] : z.fundstelle_im_text[1]] == "286"


def test_weitere_absaetze_derselben_norm():
    zitate = finde_zitate("Nutzungsentschädigung nach § 346 Abs. 1, Abs. 2 Satz 1 Nr. 1 BGB")
    assert [str(z) for z in zitate] == ["§ 346 Abs. 1 BGB", "§ 346 Abs. 2 S. 1 Nr. 1 BGB"]


def test_abgekuerzte_folgen():
    assert [str(z) for z in finde_zitate("nach §§ 280 Abs. 1, 2, 286 BGB")] == [
        "§ 280 Abs. 1 BGB",
        "§ 280 Abs. 2 BGB",
        "§ 286 BGB",
    ]
    assert [str(z) for z in finde_zitate("aus § 709 Satz 1 und 2 ZPO")] == ["§ 709 S. 1 ZPO", "§ 709 S. 2 ZPO"]
    # Eine größere Zahl ist ein eigener Paragraph.
    assert [str(z) for z in finde_zitate("§§ 437 Nr. 2, 440, 323 Abs. 1, 346 Abs. 1 BGB")] == [
        "§ 437 Nr. 2 BGB",
        "§ 440 BGB",
        "§ 323 Abs. 1 BGB",
        "§ 346 Abs. 1 BGB",
    ]


def test_verkettung_teilt_das_gesetz():
    zitate = finde_zitate("Anspruch aus § 280 Abs. 1 i.V.m. § 241 Abs. 2 BGB und § 3 des Vertrags.")
    assert [str(z) for z in zitate] == ["§ 280 Abs. 1 BGB", "§ 241 Abs. 2 BGB"]


def test_kein_gesetz_kein_zitat():
    assert finde_zitate("gemäß § 5 des Kaufvertrags und § 4 GmbH-Vertrag") == []


def test_treffer_umfasst_das_ganze_zitat():
    text = "aus §§ 280 Abs. 1, 281 BGB folgt"
    z = finde_zitate(text)
    assert text[z[0].treffer[0] : z[0].treffer[1]] == "§§ 280 Abs. 1, 281 BGB"
    assert text[z[1].fundstelle_im_text[0] : z[1].fundstelle_im_text[1]] == "281"
