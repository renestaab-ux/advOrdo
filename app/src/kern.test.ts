import { describe, expect, it } from "vitest";
import {
  abgleichZusammenfassung,
  auswahlText,
  dauerText,
  groesseText,
  veraltet,
  formatiereBuilddate,
  fundstelle,
  istZitat,
  lesartText,
  rechtsprechungUmfang,
  renderBreite,
  markiereBegriffe,
  rnHinweis,
  segmente,
  tagsAusText,
  tagUebersicht,
  urteilHerkunft,
} from "./kern";

describe("istZitat", () => {
  it("erkennt Normzitate", () => {
    expect(istZitat("§ 280 Abs. 1 S. 2 BGB")).toBe(true);
    expect(istZitat("§ 253 ZPO")).toBe(true);
    expect(istZitat("Art. 3 GG")).toBe(true);
  });
  it("behandelt Suchbegriffe nicht als Zitat", () => {
    expect(istZitat("Verjährung")).toBe(false);
    expect(istZitat("§ 280")).toBe(false);
  });
});

describe("formatiereBuilddate", () => {
  it("formatiert den Quellstempel", () => {
    expect(formatiereBuilddate("20260901120000")).toBe("01.09.2026");
    expect(formatiereBuilddate(null)).toBe("unbekannt");
  });
});

describe("fundstelle", () => {
  it("nennt Seite und Randnummer", () => {
    expect(fundstelle({ seite: 2, seite_bis: 3, rn: 5 })).toBe("S. 2–3, Rn. 5");
    expect(fundstelle({ seite: null, rn: 4 })).toBe("Rn. 4");
    expect(fundstelle({ seite: null, rn: null, nr: 12 })).toBe("Abschn. 12");
  });
});

describe("segmente", () => {
  const z = (start: number, ende: number) =>
    ({ start, ende, zitat: "x", status: "belegt" }) as unknown as import("./kern").NormZitat;
  it("schneidet Zitate aus dem Text", () => {
    const text = "aus §§ 280 Abs. 1, 281 BGB folgt";
    const s = segmente(text, [z(19, 22), z(7, 17)]);
    expect(s.map((x) => x.text)).toEqual(["aus §§ ", "280 Abs. 1", ", ", "281", " BGB folgt"]);
    expect(s.filter((x) => x.zitat).length).toBe(2);
  });
  it("ignoriert überlappende Angaben", () => {
    expect(segmente("abcdef", [z(0, 4), z(2, 5)]).map((x) => x.text)).toEqual(["abcd", "ef"]);
  });
});

describe("lesartText", () => {
  it("beschreibt die Herkunft des Textes", () => {
    expect(lesartText({ lesart: "ocr", ocr_konfidenz: 94.2, format: "pdf" })).toBe("Scan (Texterkennung, Erkennung 94 %)");
    expect(lesartText({ lesart: "datei", ocr_konfidenz: null, format: "docx" })).toBe("Word");
  });
});

describe("tagsAusText", () => {
  it("trennt an Komma und Semikolon und entfernt Dubletten", () => {
    expect(tagsAusText(" Kläger,  Anlage   K 1; kläger, ")).toEqual(["Kläger", "Anlage K 1"]);
    expect(tagsAusText("")).toEqual([]);
  });
});

describe("tagUebersicht", () => {
  it("zählt Tags und stellt Beteiligte voran", () => {
    const d = (...namen: string[]) => ({ tags: namen.map((name) => ({ name, quelle: "manuell" as const })) });
    expect(tagUebersicht([d("Anlagen", "Kläger"), d("Gericht"), d("Kläger"), d()])).toEqual([
      { name: "Kläger", anzahl: 2 },
      { name: "Gericht", anzahl: 1 },
      { name: "Anlagen", anzahl: 1 },
    ]);
  });
});

describe("abgleichZusammenfassung", () => {
  it("zählt Abweichungen und Übereinstimmungen", () => {
    expect(abgleichZusammenfassung({ dokumente: 9, zaehlung: { abweichend: 7, uebereinstimmend: 4, einzeln: 0 } })).toBe(
      "7 mögliche Abweichungen, 4 Übereinstimmungen in 9 Dokumenten",
    );
    expect(abgleichZusammenfassung({ dokumente: 1, zaehlung: { abweichend: 1, uebereinstimmend: 1, einzeln: 2 } })).toBe(
      "1 mögliche Abweichung, 1 Übereinstimmung in 1 Dokument",
    );
  });
});

describe("Sprachmodell", () => {
  it("zeigt Laufzeiten und Größen lesbar", () => {
    expect(dauerText(45)).toBe("45 s");
    expect(dauerText(185)).toBe("3:05 min");
    expect(groesseText(9_300_000_000)).toBe("9,3 GB");
    expect(groesseText(null)).toBe("");
  });
  it("erkennt, ob sich die Akte seit dem Ergebnis geändert hat", () => {
    const ergebnis = { dokumente: [{ dokument_id: 2 }, { dokument_id: 1 }] };
    expect(veraltet(ergebnis, [1, 2])).toBe(false);
    expect(veraltet(ergebnis, [1, 2, 3])).toBe(true);
    expect(veraltet(ergebnis, [1])).toBe(true);
    expect(veraltet(null, [1])).toBe(false);
  });
});

describe("Rechtsprechung", () => {
  it("beschreibt den Umfang des Verzeichnisses, größtes Gericht zuerst", () => {
    expect(
      rechtsprechungUmfang({
        gerichte: { BVerfG: { anzahl: 5, von: "1998-01-02", bis: null }, BGH: { anzahl: 40, von: "2010-01-04", bis: null } },
      }),
    ).toBe("BGH ab 2010, BVerfG ab 1998");
  });
});

describe("Randnummern", () => {
  it("sagt, ob die zitierte Randnummer im Volltext steht", () => {
    expect(rnHinweis({ rn_zitiert: 22, rn_vorhanden: true }, 67)).toBe("Rn. 22 zitiert");
    expect(rnHinweis({ rn_zitiert: 99, rn_vorhanden: false }, 67)).toBe("Rn. 99 zitiert, die Entscheidung hat nur Rn. 1–67");
    expect(rnHinweis({ rn_zitiert: null, rn_vorhanden: null }, 67)).toBeNull();
  });
});

describe("Ergänzte Urteile", () => {
  it("nennt Quelle und Datei", () => {
    expect(urteilHerkunft({ herkunft: "juris", dateiname: "BGH VIII ZR 999-20.pdf" })).toBe("juris, BGH VIII ZR 999-20.pdf");
    expect(urteilHerkunft({ herkunft: null, dateiname: "urteil.pdf" })).toBe("urteil.pdf");
  });
});

describe("Original-Ansicht", () => {
  it("rendert in gerundeter Breite, scharf auch bei hoher Pixeldichte", () => {
    expect(renderBreite(700, 1)).toBe(800);
    expect(renderBreite(700, 2)).toBe(1400);
    expect(renderBreite(100, 1)).toBe(400);
    expect(renderBreite(3000, 2)).toBe(2400);
  });
});

describe("Suche", () => {
  it("markiert Begriffe ohne Rücksicht auf Groß- und Kleinschreibung", () => {
    expect(markiereBegriffe("Der Rücktritt und der rücktritt.", ["Rücktritt"])).toEqual([
      { text: "Der ", treffer: false },
      { text: "Rücktritt", treffer: true },
      { text: " und der ", treffer: false },
      { text: "rücktritt", treffer: true },
      { text: ".", treffer: false },
    ]);
  });
  it("nimmt Sonderzeichen wörtlich und den längeren Begriff zuerst", () => {
    expect(markiereBegriffe("VIII ZR 103/15 (a+b)", ["ZR 103/15", "ZR", "(a+b)"]).filter((t) => t.treffer)).toEqual([
      { text: "ZR 103/15", treffer: true },
      { text: "(a+b)", treffer: true },
    ]);
    expect(markiereBegriffe("ohne", [])).toEqual([{ text: "ohne", treffer: false }]);
  });
});

describe("auswahlText", () => {
  it("nennt, was dem Modell vorlag", () => {
    expect(auswahlText({ vollstaendig: true, absaetze: 40, von: 40, dokumente: 3, dokumente_von: 3 })).toBe(
      "alle 3 Dokumente vollständig",
    );
    expect(auswahlText({ vollstaendig: true, absaetze: 12, von: 12, dokumente: 1, dokumente_von: 1 })).toBe(
      "das Dokument vollständig",
    );
    expect(auswahlText({ vollstaendig: false, absaetze: 120, von: 450, dokumente: 6, dokumente_von: 8 })).toBe(
      "120 von 450 Absätzen aus 6 von 8 Dokumenten, ausgewählt nach den Begriffen der Frage",
    );
    expect(auswahlText({ vollstaendig: false, absaetze: 30, von: 90, dokumente: 1, dokumente_von: 1 })).toBe(
      "30 von 90 Absätzen, ausgewählt nach den Begriffen der Frage",
    );
  });
});
