import { describe, expect, it } from "vitest";
import { protokollLesen } from "./terminsprotokoll";

describe("Terminsprotokoll in Notizen", () => {
  it("zerlegt das Protokoll in Einträge mit Art, Text und Bezug", () => {
    const text = [
      "Terminsprotokoll 24.11.2026, 10:32–11:14 Uhr (LG Freiburg, Saal 2.14)",
      "10:34 Vorsitzende führt in den Sach- und Streitstand ein.",
      "10:41 Hinweis des Gerichts: Kammer hält Fristsetzung für entbehrlich. [zu 05_Klageschrift.pdf]",
      "11:09 Frist / Auflage: Schriftsatznachlass drei Wochen.",
      "      zweite Zeile",
    ].join("\n");
    expect(protokollLesen(text)).toEqual({
      kopf: "Terminsprotokoll 24.11.2026, 10:32–11:14 Uhr (LG Freiburg, Saal 2.14)",
      eintraege: [
        { zeit: "10:34", art: null, text: "Vorsitzende führt in den Sach- und Streitstand ein.", bezug: null },
        { zeit: "10:41", art: "Hinweis des Gerichts", text: "Kammer hält Fristsetzung für entbehrlich.", bezug: "05_Klageschrift.pdf" },
        { zeit: "11:09", art: "Frist / Auflage", text: "Schriftsatznachlass drei Wochen.\nzweite Zeile", bezug: null },
      ],
    });
  });

  it("lässt andere Notizen als schlichten Text", () => {
    expect(protokollLesen("Zeuge Hoffmann anrufen.")).toBeNull();
    expect(protokollLesen("10:34 Telefonat mit Mandantin")).toBeNull();
  });
});
