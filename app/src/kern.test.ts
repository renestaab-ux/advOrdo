import { describe, expect, it } from "vitest";
import { formatiereBuilddate, istZitat } from "./kern";

describe("istZitat", () => {
  it("erkennt Normzitate", () => {
    expect(istZitat("§ 280 Abs. 1 S. 2 BGB")).toBe(true);
    expect(istZitat("§ 253 ZPO")).toBe(true);
    expect(istZitat("Art. 3 GG")).toBe(true);
  });
  it("behandelt Suchbegriffe nicht als Zitat", () => {
    expect(istZitat("Verjährung")).toBe(false);
    expect(istZitat("§ 280")).toBe(false);
  });
});

describe("formatiereBuilddate", () => {
  it("formatiert den Quellstempel", () => {
    expect(formatiereBuilddate("20260901120000")).toBe("01.09.2026");
    expect(formatiereBuilddate(null)).toBe("unbekannt");
  });
});
