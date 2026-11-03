import { describe, expect, it } from "vitest";
import { BEDEUTUNG_VORGABE, KEIN_ANMERK_FILTER } from "./anmerkungLogik";
import {
  auswahlText,
  eintragSchritt,
  ordnerSchritt,
  lesezeichenGruppen,
  ordnerGruppen,
  ordnung,
  schluessel,
  sichtbareOrdnung,
  verdichteMarken,
  verschiebeEintrag,
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

  it("Markierungen und Lesezeichen in gemeinsamen Ordnern", () => {
    const m = (id: number, ordner_id: number | null, reihenfolge: number) =>
      ({ id, ordner_id, reihenfolge, dokument_id: 1, art: "markierung", farbe: "gelb", stil: "flaeche", start: 0, ende: 1,
        zitat: "x", seite: 1, abschnitt: 1, rn: null, kommentar: null, status: "gefunden", angelegt_am: "", geaendert_am: "" }) as const;
    const g = ordnerGruppen(liste.ordner, liste.lesezeichen, [m(7, 10, 2), m(8, null, 0), m(9, null, 0)]);
    expect(g.map((x) => [x.id, x.eintraege.map(schluessel)])).toEqual([
      [10, ["l1", "m7", "l3"]],
      [11, []],
      [null, ["m8", "m9", "l2", "l4"]],
    ]);
    const neu = verschiebeEintrag(g, "m9", 11, null);
    expect(ordnung(neu)[1]).toEqual({ id: 11, eintraege: [{ art: "markierung", id: 9 }] });
    expect(neu[1].eintraege[0].art === "markierung" && neu[1].eintraege[0].a.ordner_id).toBe(11);
    expect(ordnung(verschiebeEintrag(g, "l2", 10, "m7"))[0].eintraege.map((e) => e.id)).toEqual([1, 2, 7, 3]);
    expect(verschiebeOrdner(g, 11, 10).map((x) => x.id)).toEqual([11, 10, null]);
    expect(verschiebeOrdner(g, 10, null).map((x) => x.id)).toEqual([11, 10, null]);
  });

  it("verschiebt schrittweise ohne Ziehen (Pfeiltasten und Knöpfe)", () => {
    const g = ordnerGruppen(liste.ordner, liste.lesezeichen, []);
    expect(eintragSchritt(g, "l3", -1)[0].eintraege.map(schluessel)).toEqual(["l3", "l1"]);
    expect(eintragSchritt(g, "l1", 1)[0].eintraege.map(schluessel)).toEqual(["l3", "l1"]);
    expect(eintragSchritt(g, "l1", -1)).toBe(g);
    expect(eintragSchritt(g, "l3", 1)).toBe(g);
    expect(ordnerSchritt(g, 11, -1).map((x) => x.id)).toEqual([11, 10, null]);
    expect(ordnerSchritt(g, 10, 1).map((x) => x.id)).toEqual([11, 10, null]);
    expect(ordnerSchritt(g, 11, 1)).toBe(g);
  });
});

describe("Ausgabe der angezeigten Einträge", () => {
  it("nimmt nur Sichtbares, ohne leere Ordner", () => {
    const g = lesezeichenGruppen(liste).map((x) => ({ ...x, eintraege: x.eintraege.map((z) => ({ art: "lesezeichen" as const, z })) }));
    expect(sichtbareOrdnung(g, (e) => e.art === "lesezeichen" && e.z.id !== 3)).toEqual([
      { id: 10, eintraege: [{ art: "lesezeichen", id: 1 }] },
      { id: null, eintraege: [{ art: "lesezeichen", id: 2 }, { art: "lesezeichen", id: 4 }] },
    ]);
  });

  it("beschreibt die Auswahl in Worten", () => {
    expect(auswahlText("alle", KEIN_ANMERK_FILTER, BEDEUTUNG_VORGABE)).toBeNull();
    expect(auswahlText("lesezeichen", { farben: ["rot"], nurKommentar: true, suche: "x" }, BEDEUTUNG_VORGABE)).toBe("nur Lesezeichen");
    expect(auswahlText("markierungen", { farben: ["rot", "gelb"], nurKommentar: true, suche: " Gutachten " }, BEDEUTUNG_VORGABE)).toBe(
      "nur Markierungen und Kommentare; Bedeutung Wichtig, Streitig; nur mit Kommentar; Suche „Gutachten“",
    );
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
