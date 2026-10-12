import { describe, expect, it } from "vitest";
import { formatiereBuilddate, fundstelle, istZitat, lesartText, segmente } from "./kern";

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
