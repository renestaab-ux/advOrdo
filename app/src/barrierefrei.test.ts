import { describe, expect, it } from "vitest";
import { bereichAusTaste, naechsterImKreis, trennerSchritt } from "./barrierefrei";

const taste = (code: string, mehr: Partial<{ altKey: boolean; ctrlKey: boolean; metaKey: boolean; shiftKey: boolean }> = {}) => ({
  altKey: true,
  ctrlKey: false,
  metaKey: false,
  shiftKey: false,
  code,
  ...mehr,
});

describe("bereichAusTaste", () => {
  it("Alt + Ziffer wählt den Bereich, auch über den Ziffernblock", () => {
    expect(bereichAusTaste(taste("Digit1"), 8)).toBe(0);
    expect(bereichAusTaste(taste("Numpad8"), 8)).toBe(7);
  });

  it("übergeht andere Kombinationen und Ziffern ohne Bereich", () => {
    expect(bereichAusTaste(taste("Digit9"), 8)).toBeNull();
    expect(bereichAusTaste(taste("Digit0"), 8)).toBeNull();
    expect(bereichAusTaste(taste("Digit1", { altKey: false }), 8)).toBeNull();
    expect(bereichAusTaste(taste("Digit1", { ctrlKey: true }), 8)).toBeNull(); // AltGr unter Windows
    expect(bereichAusTaste(taste("Digit1", { shiftKey: true }), 8)).toBeNull();
    expect(bereichAusTaste(taste("KeyA"), 8)).toBeNull();
  });
});

describe("naechsterImKreis", () => {
  it("springt am Ende zum Anfang und umgekehrt", () => {
    expect(naechsterImKreis(2, 3, false)).toBe(0);
    expect(naechsterImKreis(0, 3, true)).toBe(2);
  });

  it("lässt den üblichen Schritt in der Mitte zu", () => {
    expect(naechsterImKreis(1, 3, false)).toBeNull();
    expect(naechsterImKreis(1, 3, true)).toBeNull();
  });

  it("holt den Fokus von außen herein", () => {
    expect(naechsterImKreis(-1, 3, false)).toBe(0);
    expect(naechsterImKreis(-1, 3, true)).toBe(2);
    expect(naechsterImKreis(-1, 0, false)).toBeNull();
  });
});

describe("trennerSchritt", () => {
  it("Pfeiltasten ändern die Breite in Grenzen, Pos1 setzt zurück", () => {
    expect(trennerSchritt("ArrowLeft", false, 360, 260, 900, 360)).toBe(380);
    expect(trennerSchritt("ArrowRight", true, 360, 260, 900, 360)).toBe(280);
    expect(trennerSchritt("ArrowRight", true, 300, 260, 900, 360)).toBe(260);
    expect(trennerSchritt("ArrowLeft", true, 880, 260, 900, 360)).toBe(900);
    expect(trennerSchritt("Home", false, 700, 260, 900, 360)).toBe(360);
    expect(trennerSchritt("Enter", false, 700, 260, 900, 360)).toBeNull();
  });
});
