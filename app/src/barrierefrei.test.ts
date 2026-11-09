// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { ansagen, bereichAusTaste, naechsterImKreis, reiterZiel, trennerSchritt } from "./barrierefrei";

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

describe("reiterZiel", () => {
  it("geht waagerecht mit links/rechts weiter und läuft am Ende herum", () => {
    expect(reiterZiel("ArrowRight", 0, 3, false)).toBe(1);
    expect(reiterZiel("ArrowRight", 2, 3, false)).toBe(0);
    expect(reiterZiel("ArrowLeft", 0, 3, false)).toBe(2);
    expect(reiterZiel("ArrowDown", 0, 3, false)).toBeNull();
  });
  it("nimmt bei senkrechter Leiste hoch/runter, Pos1 und Ende immer", () => {
    expect(reiterZiel("ArrowDown", 1, 3, true)).toBe(2);
    expect(reiterZiel("ArrowUp", 1, 3, true)).toBe(0);
    expect(reiterZiel("ArrowRight", 1, 3, true)).toBeNull();
    expect(reiterZiel("Home", 2, 3, true)).toBe(0);
    expect(reiterZiel("End", 0, 3, false)).toBe(2);
  });
});

describe("ansagen", () => {
  it("setzt den Text verzögert in den Statusbereich, auch zweimal denselben", () => {
    vi.useFakeTimers();
    document.body.innerHTML = '<div id="ansage" role="status"></div>';
    const el = document.getElementById("ansage")!;
    ansagen("Brief.docx liegt jetzt unter Dokumente.");
    expect(el.textContent).toBe("");
    vi.advanceTimersByTime(200);
    expect(el.textContent).toBe("Brief.docx liegt jetzt unter Dokumente.");
    ansagen("Brief.docx liegt jetzt unter Dokumente.");
    expect(el.textContent).toBe("");
    vi.advanceTimersByTime(200);
    expect(el.textContent).toBe("Brief.docx liegt jetzt unter Dokumente.");
    vi.useRealTimers();
  });
});

describe("useFokusAuf", () => {
  it("setzt den Fokus auf die Meldung, sobald es ein Ergebnis gibt", async () => {
    const { act, createElement } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const { useFokusAuf } = await import("./barrierefrei");
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    function Meldung({ ergebnis }: { ergebnis: string | null }) {
      const ref = useFokusAuf<HTMLDivElement>(ergebnis);
      return ergebnis ? createElement("div", { ref, tabIndex: -1, id: "m" }, ergebnis) : null;
    }
    document.body.innerHTML = "<div id='w'></div>";
    const root = createRoot(document.getElementById("w")!);
    act(() => root.render(createElement(Meldung, { ergebnis: null })));
    act(() => root.render(createElement(Meldung, { ergebnis: "Gespeichert unter C:\\Briefe\\Brief.docx." })));
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    expect(document.activeElement?.id).toBe("m");
    act(() => root.unmount());
  });
});
