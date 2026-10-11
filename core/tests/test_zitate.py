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
