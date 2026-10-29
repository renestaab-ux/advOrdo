import { describe, expect, it } from "vitest";
import { KalenderEintrag } from "./kern";
import { FILTER_START, blaettern, kalenderwoche, posten, wochenbeginn, zeitraumTitel, zeitraumVon } from "./kalender";

const basis: KalenderEintrag = {
  id: 1,
  akte_id: 3,
  verfahren_id: null,
  art: "frist",
  art_text: "Frist",
  titel: "Klageerwiderung",
  datum: "2026-11-26",
  uhrzeit: null,
  bis_uhrzeit: null,
  ort: null,
  vorfrist: "2026-11-19",
  vorfrist2: "2026-11-24",
  vorfrist_erreicht: null,
  berechnung: null,
  dokument_id: null,
  dokument: null,
  fundstelle: null,
  notiz: null,
  erledigt_am: null,
  erledigt_vermerk: null,
  zustand: null,
  verlauf: [],
  verlegt_von: null,
  verlegt_von_termin: null,
  verlegt_auf: null,
  abgeschlossen: false,
  in_tagen: 10,
  lage: "offen",
  gericht: "Landgericht Freiburg",
};

describe("Kalender-Zeiträume", () => {
  it("rechnet Monat, Woche und Liste", () => {
    expect(wochenbeginn("2026-11-01")).toBe("2026-10-26");
    expect(zeitraumVon("monat", "2026-11-15")).toEqual({ von: "2026-10-26", bis: "2026-12-06" });
    expect(zeitraumVon("woche", "2026-11-05")).toEqual({ von: "2026-11-02", bis: "2026-11-08" });
    expect(zeitraumVon("liste", "2026-11-05")).toEqual({ von: "2026-11-05", bis: "2026-12-02" });
    expect(blaettern("monat", "2026-12-31", 1)).toBe("2027-01-01");
    expect(blaettern("woche", "2026-11-05", -1)).toBe("2026-10-29");
    expect(kalenderwoche("2026-11-02")).toBe(45);
    expect(kalenderwoche("2027-01-01")).toBe(53);
    expect(zeitraumTitel("woche", "2026-11-05")).toBe("KW 45: 02.11.–08.11.2026");
  });
});

describe("Kalender-Posten", () => {
  it("zeigt Vorfristen als eigene Tage und filtert", () => {
    const termin = { ...basis, id: 2, art: "termin" as const, titel: "Haupttermin", datum: "2026-11-20", uhrzeit: "10:00", vorfrist: null, vorfrist2: null, gericht: null };
    const alle = posten([basis, termin], FILTER_START, "2026-11-16", "2026-11-29");
    expect(alle.map((p) => [p.tag, p.typ, p.nr ?? null])).toEqual([
      ["2026-11-19", "vorfrist", 1],
      ["2026-11-20", "termin", null],
      ["2026-11-24", "vorfrist", 2],
      ["2026-11-26", "frist", null],
    ]);
    expect(posten([basis, termin], { ...FILTER_START, arten: ["termin"] }, "2026-11-16", "2026-11-29")).toHaveLength(1);
    expect(posten([basis, termin], { ...FILTER_START, gericht: "Landgericht Freiburg" }, "2026-11-16", "2026-11-29")).toHaveLength(3);
    // Erledigte Fristen zeigen keine Vorfristen mehr.
    const erledigt = { ...basis, abgeschlossen: true, erledigt_am: "2026-11-18", zustand: "erledigt" as const, lage: "erledigt" as const };
    expect(posten([erledigt], FILTER_START, "2026-11-16", "2026-11-29").map((p) => p.typ)).toEqual(["frist"]);
    expect(posten([erledigt], { ...FILTER_START, zustand: "offen" }, "2026-11-16", "2026-11-29")).toEqual([]);
  });
});
