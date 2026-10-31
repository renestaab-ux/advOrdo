import { describe, expect, it } from "vitest";
import { type HintergrundAuftrag, hintergrundErgebnis, hintergrundPause, laeuftKi } from "./kern";

const auftrag = (teil: Partial<HintergrundAuftrag>): HintergrundAuftrag => ({
  auftrag_id: 1,
  aufgabe: "gesetze.importieren",
  titel: "Gesetze laden",
  status: "fertig",
  text: "Fertig",
  schritt: null,
  von: null,
  sekunden: 3,
  ergebnis: null,
  fehler: null,
  ...teil,
});

describe("Hintergrundaufträge", () => {
  it("liefert das Ergebnis eines fertigen Auftrags", () => {
    expect(hintergrundErgebnis<number[]>(auftrag({ ergebnis: [1, 2] }))).toEqual([1, 2]);
  });

  it("meldet Abbruch und Fehler als Fehler", () => {
    expect(() => hintergrundErgebnis(auftrag({ status: "abgebrochen" }))).toThrow("Gesetze laden: abgebrochen.");
    expect(() => hintergrundErgebnis(auftrag({ status: "fehler", fehler: "offline" }))).toThrow("offline");
    expect(() => hintergrundErgebnis(auftrag({ status: "fehler" }))).toThrow("Gesetze laden: fehlgeschlagen.");
  });

  it("fragt anfangs schnell, dann höchstens jede Sekunde nach", () => {
    expect(hintergrundPause(0)).toBe(250);
    expect(hintergrundPause(1)).toBe(375);
    expect(hintergrundPause(10)).toBe(1000);
  });

  it("erkennt einen laufenden KI-Auftrag in der Antwort eines ki.*-Aufrufs", () => {
    expect(laeuftKi(auftrag({ status: "laeuft" }))).toBe(true);
    expect(laeuftKi({ status: "laeuft", auftrag: auftrag({ status: "laeuft" }) })).toBe(true);
    expect(laeuftKi(auftrag({ status: "fertig" }))).toBe(false);
    expect(laeuftKi({ status: "aus" })).toBe(false);
    expect(laeuftKi(null)).toBe(false);
    expect(laeuftKi([1, 2])).toBe(false);
  });
});
