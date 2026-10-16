import { describe, expect, it } from "vitest";
import {
  abgleichZusammenfassung,
  dauerText,
  groesseText,
  veraltet,
  formatiereBuilddate,
  fundstelle,
  istZitat,
  lesartText,
  rechtsprechungUmfang,
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

describe("Ergänzte Urteile", () => {
  it("nennt Quelle und Datei", () => {
    expect(urteilHerkunft({ herkunft: "juris", dateiname: "BGH VIII ZR 999-20.pdf" })).toBe("juris, BGH VIII ZR 999-20.pdf");
    expect(urteilHerkunft({ herkunft: null, dateiname: "urteil.pdf" })).toBe("urteil.pdf");
  });
});
