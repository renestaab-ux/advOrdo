

def test_paragraphenzeichen_nachgebessert():
    from juracore.dokumente.ocr import paragraphen_nachbessern

    def f(s: str) -> str:
        return " ".join(paragraphen_nachbessern(s.split()))

    assert f("8& 1 Leistungen") == "§ 1 Leistungen"
    assert f("$& 10 Gerichtsstand, Schlussbestimmungen") == "§ 10 Gerichtsstand, Schlussbestimmungen"
    assert f("$ 10 Gerichtsstand, Schlussbestimmungen") == "§ 10 Gerichtsstand, Schlussbestimmungen"
    assert f("nach 8 309 Nr. 7 BGB") == "nach § 309 Nr. 7 BGB"
    assert f("gemäß $ 307 Abs. 1 BGB") == "gemäß § 307 Abs. 1 BGB"
    assert f("88 305 bis 310 BGB") == "§§ 305 bis 310 BGB"
    # Echte Achten bleiben.
    for s in ("Der Vertrag läuft 8 Monate.", "8 12 Monate", "Kosten 8 25,00 €", "8 Wochen"):
        assert f(s) == s
