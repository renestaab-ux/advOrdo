import { describe, expect, it } from "vitest";
import { startGerichtsbarkeit, vorbelegungAus, ZUSTAENDIGKEIT_HINWEIS } from "./gerichtssuche";

describe("Zuständigkeitssuche", () => {
  it("wählt im Mahnverfahren das Mahngericht, wenn es eingeschaltet ist", () => {
    expect(startGerichtsbarkeit(["zivil", "mahn"], "mahnverfahren")).toBe("mahn");
    expect(startGerichtsbarkeit(["zivil", "arbeit"], "mahnverfahren")).toBe("zivil");
    expect(startGerichtsbarkeit(["arbeit", "sozial"], "klage")).toBe("arbeit");
    expect(startGerichtsbarkeit([], "klage")).toBeNull();
  });

  it("belegt Sozialgericht und Mahngericht mit der eigenen Seite vor", () => {
    expect(vorbelegungAus("sozial")).toBe("mandant");
    expect(vorbelegungAus("mahn")).toBe("mandant");
    expect(vorbelegungAus("zivil")).toBe("gegner");
    expect(vorbelegungAus("verwaltung")).toBe("gegner");
  });

  it("nennt für jede Gerichtsbarkeit eine Norm", () => {
    for (const t of Object.values(ZUSTAENDIGKEIT_HINWEIS)) expect(t).toMatch(/§/);
  });
});
