import { describe, expect, it } from "vitest";
import {
  lesezeichenGruppen,
  ordnung,
  verdichteMarken,
  verschiebeLesezeichen,
  verschiebeOrdner,
  type Lesezeichen,
  type LesezeichenListe,
} from "./lesezeichenLogik";

function lz(id: number, ordner_id: number | null): Lesezeichen {
  return {
    id, dokument_id: 1, ordner_id, titel: `L${id}`, start: 0, ende: 1, zitat: "x", seite: 1, abschnitt: 1, rn: null,
    status: "gefunden", reihenfolge: id, angelegt_am: "", dokument: "Klage",
  };
}

const liste: LesezeichenListe = {
  ordner: [{ id: 10, name: "Beweis", reihenfolge: 0 }, { id: 11, name: "Später", reihenfolge: 1 }],
  lesezeichen: [lz(1, 10), lz(2, null), lz(3, 10), lz(4, 99)],
};

describe("Lesezeichen in Ordnern", () => {
  it("gruppiert nach Ordnern, Unbekanntes und Ohne Ordner zuletzt", () => {
    const g = lesezeichenGruppen(liste);
    expect(g.map((x) => [x.id, x.eintraege.map((e) => e.id)])).toEqual([
      [10, [1, 3]],
      [11, []],
      [null, [2, 4]],
    ]);
    expect(lesezeichenGruppen(liste, false).map((x) => x.id)).toEqual([10, null]);
  });

  it("verschiebt Lesezeichen und Ordner", () => {
    const g = lesezeichenGruppen(liste);
    const neu = verschiebeLesezeichen(g, 3, 11);
    expect(ordnung(neu)).toEqual([
      { id: 10, lesezeichen: [1] },
      { id: 11, lesezeichen: [3] },
      { id: null, lesezeichen: [2, 4] },
    ]);
    expect(neu[1].eintraege[0].ordner_id).toBe(11);
    expect(ordnung(verschiebeLesezeichen(g, 2, 10, 0))[0].lesezeichen).toEqual([2, 1, 3]);
    expect(verschiebeOrdner(g, 11, 10).map((x) => x.id)).toEqual([11, 10, null]);
    expect(verschiebeOrdner(g, 10, null).map((x) => x.id)).toEqual([11, 10, null]);
  });
});

describe("Marken an der Bildlaufleiste", () => {
  it("fasst nahe Marken gleicher Art zusammen", () => {
    const m = (lage: number, art: string) => ({ lage, art, ziel: 0, titel: "" });
    expect(verdichteMarken([m(0.5, "gelb"), m(0.1, "rot"), m(0.502, "gelb"), m(0.501, "lesezeichen")]).map((x) => [x.lage, x.art])).toEqual([
      [0.1, "rot"],
      [0.5, "gelb"],
      [0.501, "lesezeichen"],
    ]);
  });
});
