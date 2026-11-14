import { describe, expect, it } from "vitest";
import { type KiLeistung, leistungsBericht } from "./kern";

const ergebnis: KiLeistung = {
  anbieter: "LM Studio (OpenAI-kompatibel)",
  modell: "google/gemma-4-12b",
  ort: "Lokales Netzwerk",
  dauer: 95,
  messwerte: [{ titel: "Token pro Sekunde", wert: "31", stand: "ok", hinweis: null }],
  fragen: [
    {
      id: "berufung_wochenende",
      bereich: "Fristen",
      frage: "Bis wann läuft die Berufungsfrist?",
      erwartet: "Fristende 14.09.2026",
      antwort: "12.09.2026",
      richtig: false,
      fundstelle: "§ 517 ZPO",
      sekunden: 4.2,
    },
  ],
  bereiche: [{ bereich: "Fristen", richtig: 0, von: 1 }],
  gesamt: { richtig: 0, von: 1, stand: "fehler", meldung: "0 von 1 Prüffragen richtig beantwortet." },
  stand_fundstellen: "13.11.2026",
};

describe("Bericht des KI-Leistungstests", () => {
  it("nennt Modell, Messwerte, Antwort, Erwartung und Fundstelle", () => {
    const text = leistungsBericht(ergebnis, new Date(2026, 10, 13, 15, 0));
    expect(text).toContain("google/gemma-4-12b (LM Studio (OpenAI-kompatibel), Lokales Netzwerk)");
    expect(text).toContain("- [OK] Token pro Sekunde: 31");
    expect(text).toContain("[FALSCH] Fristen: Bis wann läuft die Berufungsfrist?");
    expect(text).toContain("Erwartet: Fristende 14.09.2026");
    expect(text).toContain("Fundstelle: § 517 ZPO");
  });
});
