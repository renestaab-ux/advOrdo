import { describe, expect, it } from "vitest";
import { geaenderteBereiche } from "./aenderungen";

describe("Abgleich zwischen den Fenstern", () => {
  it("meldet nur ändernde Aufrufe", () => {
    expect(geaenderteBereiche("akten.notiz_speichern")).toEqual(["notizen"]);
    expect(geaenderteBereiche("akten.notiz_loeschen")).toEqual(["notizen"]);
    expect(geaenderteBereiche("akten.notizen")).toEqual([]);
    expect(geaenderteBereiche("anmerkungen.anlegen")).toEqual(["anmerkungen"]);
    expect(geaenderteBereiche("anmerkungen.liste")).toEqual([]);
    expect(geaenderteBereiche("anmerkungen.export")).toEqual([]);
    expect(geaenderteBereiche("lesezeichen.anordnen")).toEqual(["lesezeichen"]);
    expect(geaenderteBereiche("lesezeichen.ordner_umbenennen")).toEqual(["lesezeichen"]);
    expect(geaenderteBereiche("lesezeichen.liste")).toEqual([]);
    expect(geaenderteBereiche("lesezeichen.inhalt")).toEqual([]);
    expect(geaenderteBereiche("akten.dokument")).toEqual([]);
    expect(geaenderteBereiche("sitzung.notiz_anlegen")).toEqual(["sitzung"]);
    expect(geaenderteBereiche("sitzung.beenden")).toEqual(["sitzung", "notizen"]);
    expect(geaenderteBereiche("sitzung.punkte")).toEqual([]);
    expect(geaenderteBereiche("sitzung.abschluss")).toEqual([]);
  });
});
