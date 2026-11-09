// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import {
  MAX_SPALTEN,
  MIN_ANTEIL,
  anordnungMerken,
  anordnungPruefen,
  anteileVon,
  fensterName,
  gemerkteAnordnung,
  gemerkteLage,
  lageMerken,
  lagePruefen,
  anlageAusTag,
  springTreffer,
  spalteEntfernen,
  terminAnordnung,
  vorTerminHolen,
  vorTerminMerken,
  spaltenZahl,
  standardAnordnung,
  trennerVerschieben,
  zielSpalte,
} from "./arbeitsfensterLogik";

describe("Anordnung des Arbeitsfensters", () => {
  beforeEach(() => localStorage.clear());

  it("startet mit zwei Spalten: Dokument und Notizen", () => {
    const a = standardAnordnung();
    expect(a.spalten.map((s) => s.art)).toEqual(["dokument", "notizen"]);
    expect(anteileVon(a)).toEqual([0.5, 0.5]);
  });

  it("erlaubt 1 bis 4 Spalten", () => {
    const a = standardAnordnung();
    expect(spaltenZahl(a, 4).spalten.map((s) => s.art)).toEqual(["dokument", "notizen", "leer", "leer"]);
    expect(spaltenZahl(a, 9).spalten).toHaveLength(MAX_SPALTEN);
    expect(spaltenZahl(a, 1).spalten.map((s) => s.art)).toEqual(["dokument"]);
    expect(spaltenZahl(a, 0).spalten).toHaveLength(1);
  });

  it("lässt die letzte Spalte stehen", () => {
    const eine = spaltenZahl(standardAnordnung(), 1);
    expect(spalteEntfernen(eine, 0)).toBe(eine);
    expect(spalteEntfernen(standardAnordnung(), 0).spalten.map((s) => s.art)).toEqual(["notizen"]);
  });

  it("verschiebt nur die beiden Nachbarn einer Trennlinie und hält die Mindestbreite", () => {
    const a = spaltenZahl(standardAnordnung(), 3);
    const b = trennerVerschieben(a, 0, 0.1);
    const [l, m, r] = anteileVon(b);
    expect(l).toBeCloseTo(1 / 3 + 0.1);
    expect(m).toBeCloseTo(1 / 3 - 0.1);
    expect(r).toBeCloseTo(1 / 3);
    const c = trennerVerschieben(a, 0, 5);
    expect(anteileVon(c)[1]).toBeCloseTo(MIN_ANTEIL);
    expect(trennerVerschieben(a, 2, 0.1)).toBe(a);
  });

  it("fällt bei kaputten oder fremden Daten auf den Standard zurück", () => {
    expect(anordnungPruefen(null)).toEqual(standardAnordnung());
    expect(anordnungPruefen({ spalten: [] })).toEqual(standardAnordnung());
    const a = anordnungPruefen({
      spalten: [{ art: "dokument", dokumentId: "x", modus: "seltsam" }, { art: "unbekannt" }, {}, {}, {}],
      anteile: [1, 1],
    });
    expect(a.spalten).toEqual([
      { art: "dokument", dokumentId: null, modus: "text" },
      { art: "leer" },
      { art: "leer" },
      { art: "leer" },
    ]);
    expect(a.anteile).toBeNull();
  });

  it("merkt die Anordnung je Akte, ohne Sprungziel", () => {
    const a = { spalten: [{ art: "dokument" as const, dokumentId: 7, modus: "original" as const, abschnitt: 3 }], anteile: null };
    anordnungMerken(1, a);
    expect(gemerkteAnordnung(1)).toEqual({ spalten: [{ art: "dokument", dokumentId: 7, modus: "original" }], anteile: null });
    expect(gemerkteAnordnung(2)).toEqual(standardAnordnung());
  });
});

describe("Ziel für ein Dokument aus einer Liste", () => {
  it("nimmt die nächste Dokument-Spalte", () => {
    const a = { spalten: [{ art: "dokument" as const }, { art: "normen" as const }, { art: "dokument" as const }], anteile: null };
    expect(zielSpalte(a, 1).index).toBe(0);
    expect(zielSpalte(a, 2).index).toBe(2);
  });

  it("nimmt sonst eine leere Spalte oder legt eine an", () => {
    const leer = { spalten: [{ art: "normen" as const }, { art: "leer" as const }], anteile: null };
    expect(zielSpalte(leer, 0).index).toBe(1);
    const voll = { spalten: [{ art: "normen" as const }, { art: "notizen" as const }], anteile: null };
    const z = zielSpalte(voll, 0);
    expect(z.index).toBe(1);
    expect(z.anordnung.spalten.map((s) => s.art)).toEqual(["normen", "leer", "notizen"]);
  });

  it("ersetzt bei vier vollen Spalten die Nachbarspalte", () => {
    const vier = {
      spalten: [{ art: "normen" as const }, { art: "notizen" as const }, { art: "rechtsprechung" as const }, { art: "anmerkungen" as const }],
      anteile: null,
    };
    expect(zielSpalte(vier, 1).index).toBe(2);
    expect(zielSpalte(vier, 3).index).toBe(2);
  });
});

describe("Lage des Fensters", () => {
  it("prüft gespeicherte Werte", () => {
    expect(lagePruefen({ x: -1500.4, y: 20, breite: 1400, hoehe: 900 })).toEqual({ x: -1500, y: 20, breite: 1400, hoehe: 900 });
    expect(lagePruefen({ x: 0, y: 0, breite: 50, hoehe: 900 })).toBeNull();
    expect(lagePruefen({ x: "a" })).toBeNull();
  });

  it("merkt die Lage je Akte", () => {
    lageMerken(3, { x: 10, y: 20, breite: 1200, hoehe: 800 });
    expect(gemerkteLage(3)).toEqual({ x: 10, y: 20, breite: 1200, hoehe: 800 });
    expect(gemerkteLage(4)).toBeNull();
  });

  it("benennt das Fenster nach der Akte", () => {
    expect(fensterName(12)).toBe("akte-12");
  });
});

describe("Terminmodus", () => {
  beforeEach(() => localStorage.clear());

  it("ordnet Sitzungsblatt, Dokument und Terminsnotizen an und übernimmt das offene Dokument", () => {
    const vorher = { spalten: [{ art: "notizen" as const }, { art: "dokument" as const, dokumentId: 6, modus: "original" as const }], anteile: null };
    const t = terminAnordnung(vorher);
    expect(t.spalten).toEqual([
      { art: "sitzungsblatt" },
      { art: "dokument", dokumentId: 6, modus: "original" },
      { art: "terminsnotizen" },
    ]);
    expect(anteileVon(t).reduce((a, b) => a + b, 0)).toBeCloseTo(1);
  });

  it("stellt die Anordnung nach dem Termin wieder her, auch nach einem zweiten Start", () => {
    const vorher = spaltenZahl(standardAnordnung(), 3);
    vorTerminMerken(1, vorher);
    vorTerminMerken(1, terminAnordnung(vorher));
    expect(vorTerminHolen(1).spalten.map((s) => s.art)).toEqual(["dokument", "notizen", "leer"]);
    expect(vorTerminHolen(1)).toEqual(standardAnordnung());
  });
});

describe("Springen per Kürzel", () => {
  const dokumente = [
    { id: 1, name: "01_Kaufvertrag_2025-03-14.pdf", tags: ["Anlage K 1"] },
    { id: 2, name: "02_Anwaltsschreiben_Nacherfuellung.pdf", tags: ["Kläger", "K2"] },
    { id: 3, name: "03_Antwortschreiben_Autohaus.pdf", tags: ["Anlage B 1"] },
  ];
  const normen = [
    {
      zitat: "§ 477 Abs. 1 BGB",
      fundstellen: [{ dokument_id: 5, dateiname: "05_Klageschrift.pdf", abschnitt: 12, seite: 2, rn: 4 }],
    },
    { zitat: "§ 323 Abs. 2 Nr. 1 BGB", fundstellen: [{ dokument_id: 5, dateiname: "05_Klageschrift.pdf", abschnitt: 9, seite: 2, rn: 3 }] },
  ];

  it("erkennt Anlagen in Tags", () => {
    expect(anlageAusTag("Anlage K 1")).toBe("K 1");
    expect(anlageAusTag("K2")).toBe("K 2");
    expect(anlageAusTag("b 1")).toBe("B 1");
    expect(anlageAusTag("Kläger")).toBeNull();
    expect(anlageAusTag("BGB 5")).toBeNull();
  });

  it("findet Anlagen, Randnummern, Normen und Namen", () => {
    expect(springTreffer("K 2", dokumente, normen, []).map((t) => t.dokumentId)).toEqual([2]);
    expect(springTreffer("anlage b1", dokumente, normen, [])[0]).toMatchObject({ titel: "Anlage B 1", dokumentId: 3 });
    expect(springTreffer("Rn. 14", dokumente, normen, [5, 6, 5])).toEqual([
      { titel: "Rn. 14", hinweis: "Dokument 5", dokumentId: 5, rn: 14 },
      { titel: "Rn. 14", hinweis: "Dokument 6", dokumentId: 6, rn: 14 },
    ]);
    expect(springTreffer("§ 477", dokumente, normen, [])).toEqual([
      { titel: "§ 477 Abs. 1 BGB", hinweis: "05_Klageschrift.pdf, Rn. 4", dokumentId: 5, abschnitt: 12 },
    ]);
    expect(springTreffer("antwort", dokumente, normen, []).map((t) => t.hinweis)).toEqual(["Anlage B 1"]);
    expect(springTreffer("  ", dokumente, normen, [])).toEqual([]);
  });
});
