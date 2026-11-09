import { describe, expect, it } from "vitest";
import { geaenderterBereich } from "./aenderungen";

describe("Abgleich zwischen den Fenstern", () => {
  it("meldet nur ändernde Aufrufe", () => {
    expect(geaenderterBereich("akten.notiz_speichern")).toBe("notizen");
    expect(geaenderterBereich("akten.notiz_loeschen")).toBe("notizen");
    expect(geaenderterBereich("akten.notizen")).toBeNull();
    expect(geaenderterBereich("anmerkungen.anlegen")).toBe("anmerkungen");
    expect(geaenderterBereich("anmerkungen.liste")).toBeNull();
    expect(geaenderterBereich("anmerkungen.export")).toBeNull();
    expect(geaenderterBereich("lesezeichen.anordnen")).toBe("lesezeichen");
    expect(geaenderterBereich("lesezeichen.ordner_umbenennen")).toBe("lesezeichen");
    expect(geaenderterBereich("lesezeichen.liste")).toBeNull();
    expect(geaenderterBereich("lesezeichen.inhalt")).toBeNull();
    expect(geaenderterBereich("akten.dokument")).toBeNull();
  });
});
