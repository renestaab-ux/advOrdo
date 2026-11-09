import { describe, expect, it } from "vitest";
import {
  woerterText,
  wortSchritt,
  abschnittBeginne,
  auswahlRechtecke,
  anmerkungOrt,
  BEDEUTUNG_VORGABE,
  filtereAnmerkungen,
  formatiere,
  inline,
  KEIN_ANMERK_FILTER,
  kommentarText,
  markdownBloecke,
  stueckKlassen,
  stuecke,
  type Anmerkung,
  type SeitenWort,
  wortAn,
} from "./anmerkungLogik";

function anm(id: number, start: number, ende: number, mehr: Partial<Anmerkung> = {}): Anmerkung {
  return {
    id, dokument_id: 1, art: "markierung", farbe: "gelb", stil: "flaeche", start, ende, zitat: "x", seite: 1,
    abschnitt: 1, rn: null, kommentar: null, status: "gefunden", angelegt_am: "", geaendert_am: "", ...mehr,
  };
}

describe("Lage im Text", () => {
  it("Abschnitte beginnen nach dem Zeilenumbruch", () => {
    expect(abschnittBeginne([{ text: "abc" }, { text: "" }, { text: "de" }])).toEqual([0, 4, 5]);
  });

  it("zerlegt an den Grenzen überlappender Markierungen", () => {
    // Abschnitt beginnt bei 10, Text 0–20; Markierungen 12–17 und 15–40 (geht in den nächsten Abschnitt).
    const a = anm(1, 12, 17);
    const b = anm(2, 15, 40, { farbe: "rot" });
    const s = stuecke(0, 20, 10, [b, a, anm(3, 50, 60), anm(4, 12, 14, { status: "nicht_gefunden" })]);
    expect(s.map((x) => [x.von, x.bis, x.anmerkungen.map((m) => m.id)])).toEqual([
      [0, 2, []],
      [2, 5, [1]],
      [5, 7, [1, 2]],
      [7, 20, [2]],
    ]);
    expect(s[2].endeVon.map((m) => m.id)).toEqual([1]);
    expect(s[3].endeVon).toEqual([]); // b endet erst im nächsten Abschnitt
    expect(stuecke(3, 9, 0, [])).toEqual([{ von: 3, bis: 9, anmerkungen: [], endeVon: [] }]);
  });

  it("Klassen: jüngste Fläche gewinnt, Linien kommen dazu", () => {
    expect(stueckKlassen([anm(1, 0, 1), anm(2, 0, 1, { farbe: "blau" })])).toBe("anm anm-blau");
    expect(stueckKlassen([anm(1, 0, 1), anm(2, 0, 1, { farbe: "rot", stil: "unterstrichen" })])).toBe(
      "anm anm-gelb anm-unter anm-linie-rot",
    );
    expect(stueckKlassen([anm(1, 0, 1, { stil: "durchgestrichen", farbe: "gruen" })])).toBe(
      "anm anm-durch anm-linie-gruen",
    );
  });

  it("Ort für die Liste", () => {
    expect(anmerkungOrt({ seite: 3, rn: 12, abschnitt: 4, status: "gefunden" })).toBe("S. 3, Rn. 12");
    expect(anmerkungOrt({ seite: null, rn: null, abschnitt: 4, status: "gefunden" })).toBe("Abschn. 4");
    expect(anmerkungOrt({ seite: 3, rn: null, abschnitt: 4, status: "nicht_gefunden" })).toBe("Stelle nicht mehr gefunden");
  });
});

describe("Filter", () => {
  const liste = [
    anm(1, 0, 1, { zitat: "Rücktritt vom Kaufvertrag", farbe: "gruen" }),
    anm(2, 0, 1, { zitat: "Frist", kommentar: "Angemessenheit **bestritten**", farbe: "rot" }),
    anm(3, 0, 1, { zitat: "18.900,00 EUR" }),
  ];
  const ids = (f: Partial<typeof KEIN_ANMERK_FILTER>) =>
    filtereAnmerkungen(liste, { ...KEIN_ANMERK_FILTER, ...f }, BEDEUTUNG_VORGABE).map((a) => a.id);

  it("nach Farbe, Kommentar und Suchwörtern", () => {
    expect(ids({})).toEqual([1, 2, 3]);
    expect(ids({ farben: ["rot", "gelb"] })).toEqual([2, 3]);
    expect(ids({ nurKommentar: true })).toEqual([2]);
    expect(ids({ suche: "rucktritt" })).toEqual([1]);
    expect(ids({ suche: "streitig" })).toEqual([2]); // Bedeutung der Farbe
    expect(ids({ suche: "frist bestritten" })).toEqual([2]);
    expect(ids({ suche: "frist kauf" })).toEqual([]);
  });
});

describe("Markdown", () => {
  it("fett, kursiv und Code im Text", () => {
    expect(inline("a **fett** und *kursiv*, `x*y` _ja_ snake_case")).toEqual([
      { text: "a " },
      { text: "fett", fett: true },
      { text: " und " },
      { text: "kursiv", kursiv: true },
      { text: ", " },
      { text: "x*y", code: true },
      { text: " " },
      { text: "ja", kursiv: true },
      { text: " snake_case" },
    ]);
    expect(inline("<b>kein HTML</b>")).toEqual([{ text: "<b>kein HTML</b>" }]);
  });

  it("Absätze, Listen und Code-Blöcke", () => {
    const b = markdownBloecke("Erste Zeile\nzweite\n\n- eins\n- **zwei**\n1. a\n2. b\n```\ncode *nicht*\n```");
    expect(b.map((x) => x.art)).toEqual(["absatz", "liste", "liste", "code"]);
    expect(b[0]).toEqual({ art: "absatz", zeilen: [[{ text: "Erste Zeile" }], [{ text: "zweite" }]] });
    expect(b[1]).toEqual({ art: "liste", geordnet: false, punkte: [[{ text: "eins" }], [{ text: "zwei", fett: true }]] });
    expect(b[2]).toMatchObject({ geordnet: true });
    expect(b[3]).toEqual({ art: "code", text: "code *nicht*" });
    expect(kommentarText("**Beweis:** Anlage K2\n- Fax", 18)).toBe("Beweis: Anlage K2…");
  });

  it("Knöpfe setzen Markdown um die Auswahl", () => {
    expect(formatiere("ab cd", 3, 5, "fett")).toEqual({ text: "ab **cd**", von: 5, bis: 7 });
    expect(formatiere("ab cd", 0, 2, "kursiv").text).toBe("*ab* cd");
    expect(formatiere("eins\nzwei\n- drei", 2, 15, "liste").text).toBe("- eins\n- zwei\n- drei");
    expect(formatiere("x", 1, 1, "codeblock").text).toBe("x\n```\n\n```\n");
  });
});

describe("Wörter im Original wählen", () => {
  const w: SeitenWort[] = [
    ["Die", 1, 0.1, 0.1, 0.05, 0.02],
    ["Klage", 1, 0.17, 0.1, 0.08, 0.02],
    ["ist", 2, 0.1, 0.14, 0.04, 0.02],
    ["begründet.", 2, 0.16, 0.14, 0.12, 0.02],
  ];

  it("trifft das Wort unter der Maus, sonst das nächste derselben Zeile", () => {
    expect(wortAn(w, 0.2, 0.11)).toBe(1);
    expect(wortAn(w, 0.9, 0.15)).toBe(3); // rechts neben dem Zeilenende
    expect(wortAn(w, 0.05, 0.135)).toBe(2);
    expect(wortAn([], 0.5, 0.5)).toBeNull();
  });

  it("ein Rechteck je Zeile", () => {
    const r = auswahlRechtecke(w, 1, 3);
    expect(r).toHaveLength(2);
    expect(r[0]).toMatchObject({ x: 0.17, y: 0.1 });
    expect(r[1].x).toBeCloseTo(0.1);
    expect(r[1].b).toBeCloseTo(0.18);
  });
});

describe("Markieren im Original per Tastatur", () => {
  // Zwei Zeilen: „Der Kläger ver-“ / „langt Zahlung von 500 €“.
  const w: SeitenWort[] = [
    ["Der", 0, 0.1, 0.1, 0.05, 0.02],
    ["Kläger", 0, 0.16, 0.1, 0.1, 0.02],
    ["ver-", 0, 0.27, 0.1, 0.05, 0.02],
    ["langt", 1, 0.1, 0.13, 0.07, 0.02],
    ["Zahlung", 1, 0.18, 0.13, 0.1, 0.02],
    ["von", 1, 0.29, 0.13, 0.04, 0.02],
    ["500", 1, 0.34, 0.13, 0.04, 0.02],
  ];
  it("springt wortweise, zeilenweise und an Zeilen- und Seitenränder", () => {
    expect(wortSchritt(w, 0, "ArrowRight", false)).toBe(1);
    expect(wortSchritt(w, 0, "ArrowLeft", false)).toBe(0);
    expect(wortSchritt(w, 6, "ArrowRight", false)).toBe(6);
    expect(wortSchritt(w, 1, "ArrowDown", false)).toBe(4); // unter „Kläger“ steht „Zahlung“
    expect(wortSchritt(w, 5, "ArrowUp", false)).toBe(2);
    expect(wortSchritt(w, 5, "ArrowDown", false)).toBe(5);
    expect(wortSchritt(w, 5, "Home", false)).toBe(3);
    expect(wortSchritt(w, 3, "End", false)).toBe(6);
    expect(wortSchritt(w, 4, "End", true)).toBe(6);
    expect(wortSchritt(w, 4, "Home", true)).toBe(0);
    expect(wortSchritt(w, 4, "a", false)).toBeNull();
  });
  it("liest die Auswahl mit zusammengezogener Trennung vor", () => {
    expect(woerterText(w, 1, 4)).toBe("Kläger verlangt Zahlung");
    expect(woerterText(w, 0, 0)).toBe("Der");
  });
});
