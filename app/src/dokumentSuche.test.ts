import { describe, expect, it } from "vitest";
import { dokumentPasst, suchWoerter, vergleichbar } from "./dokumentSuche";

const dok = {
  titel: "Gutachten Diagnoseprotokoll Pumpe",
  dateiname: "anlage_k3.pdf",
  herkunft: "Kläger/Anlagen",
  art: "Gutachten",
  datum: "2026-03-14",
  tags: [{ name: "Kläger", quelle: "ordner" as const }],
  absender: { wert: 3 as const, name: "Sachverständiger Weiß", rolle_text: "Sachverständiger" },
};

describe("Suchfeld der Dokumentliste", () => {
  it("findet Wortteile ohne Rücksicht auf Groß- und Kleinschreibung und Umlaute", () => {
    expect(dokumentPasst(dok, "protokoll")).toBe(true);
    expect(dokumentPasst(dok, "*PROTOKOLL*")).toBe(true);
    expect(dokumentPasst(dok, "klager anlagen")).toBe(true);
    expect(dokumentPasst(dok, "weiss")).toBe(true);
  });

  it("verlangt alle Wörter und sucht auch in Dateiname, Art, Absender und Datum", () => {
    expect(dokumentPasst(dok, "anlage_k3")).toBe(true);
    expect(dokumentPasst(dok, "14.03.2026")).toBe(true);
    expect(dokumentPasst(dok, "2026-03")).toBe(true);
    expect(dokumentPasst(dok, "Gutachten Beklagter")).toBe(false);
    expect(dokumentPasst(dok, "   ")).toBe(true);
  });

  it("hält eine Wortfolge in Anführungszeichen zusammen", () => {
    expect(suchWoerter('„Diagnoseprotokoll Pumpe“ k3')).toEqual(["diagnoseprotokoll pumpe", "k3"]);
    expect(dokumentPasst(dok, '"Pumpe Diagnoseprotokoll"')).toBe(false);
    expect(vergleichbar("Rücktritt")).toBe("rucktritt");
  });

  it("findet eigene Schreiben über „uns“", () => {
    expect(dokumentPasst({ ...dok, absender: { wert: "eigene", name: "Kanzlei", rolle_text: "" } }, "uns")).toBe(true);
  });
});

describe("Vorschlag Wortteilsuche in der Volltextsuche", () => {
  it("schlägt *wort* nur für einfache Wörter ohne Platzhalter vor", async () => {
    const { wortteilVorschlag } = await import("./kern");
    expect(wortteilVorschlag("Protokoll")).toBe("*Protokoll*");
    expect(wortteilVorschlag("Protokoll Pumpe")).toBe("*Protokoll* *Pumpe*");
    expect(wortteilVorschlag("*protokoll*")).toBeNull();
    expect(wortteilVorschlag('"bis zum"')).toBeNull();
    expect(wortteilVorschlag("§ 437")).toBeNull();
    expect(wortteilVorschlag("ab")).toBeNull();
  });
});
