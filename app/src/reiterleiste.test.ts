import { describe, expect, it } from "vitest";
import { menueZiel, reiterAufteilen } from "./reiterleiste";

describe("reiterAufteilen", () => {
  const b = [100, 100, 100, 100, 100];

  it("zeigt alle Reiter, wenn sie in die Zeile passen", () => {
    expect(reiterAufteilen(b, 500, 80, 0)).toEqual({ sichtbar: [0, 1, 2, 3, 4], mehr: [] });
  });

  it("legt die hinteren Reiter in das Menü „Mehr“", () => {
    // 380 Platz − 80 für „Mehr“ = 300: drei Reiter passen.
    expect(reiterAufteilen(b, 380, 80, 0)).toEqual({ sichtbar: [0, 1, 2], mehr: [3, 4] });
  });

  it("hält den gewählten Reiter sichtbar, auch wenn er hinten liegt", () => {
    expect(reiterAufteilen(b, 380, 80, 4)).toEqual({ sichtbar: [0, 1, 4], mehr: [2, 3] });
  });

  it("ohne gewählten Reiter der Leiste (Stammdaten) bleibt die Reihenfolge", () => {
    expect(reiterAufteilen(b, 380, 80, -1)).toEqual({ sichtbar: [0, 1, 2], mehr: [3, 4] });
  });

  it("lässt bei sehr schmaler Zeile wenigstens einen Reiter stehen", () => {
    expect(reiterAufteilen(b, 50, 80, -1).sichtbar).toEqual([0]);
    expect(reiterAufteilen(b, 50, 80, 3).sichtbar).toEqual([3]);
  });
});

describe("menueZiel", () => {
  it("läuft mit den Pfeiltasten herum und kennt Pos1/Ende", () => {
    expect(menueZiel("ArrowDown", 2, 3)).toBe(0);
    expect(menueZiel("ArrowUp", 0, 3)).toBe(2);
    expect(menueZiel("Home", 2, 3)).toBe(0);
    expect(menueZiel("End", 0, 3)).toBe(2);
    expect(menueZiel("a", 0, 3)).toBeNull();
  });
});
