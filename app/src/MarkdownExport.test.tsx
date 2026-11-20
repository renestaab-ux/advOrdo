// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const aufrufe: { methode: string; params: unknown }[] = [];
const speichernDialog = vi.fn();

vi.mock("./kern", async (original) => ({
  ...(await original<typeof import("./kern")>()),
  kern: vi.fn(async (methode: string, params: unknown) => {
    aufrufe.push({ methode, params });
    if (methode === "markdown.name") return { name: "BGB_Buergerliches-Gesetzbuch_Stand-2026-10-09.md", warnung: null };
    return { pfad: "/tmp/BGB.md", warnung: "Laut Standangabe ist dies eine außer Kraft getretene Fassung." };
  }),
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ save: (o: unknown) => speichernDialog(o) }));

const { default: MarkdownKnopf } = await import("./MarkdownExport");

describe("MarkdownKnopf", () => {
  let wurzel: Root;
  let ort: HTMLDivElement;
  beforeEach(() => {
    aufrufe.length = 0;
    speichernDialog.mockReset();
    ort = document.createElement("div");
    document.body.appendChild(ort);
    wurzel = createRoot(ort);
  });
  afterEach(() => {
    act(() => wurzel.unmount());
    ort.remove();
  });

  it("schlägt den Dateinamen vor, speichert und zeigt die Warnung", async () => {
    speichernDialog.mockResolvedValue("/tmp/BGB.md");
    await act(async () => wurzel.render(<MarkdownKnopf quelle={{ gesetz: "BGB", fassung_id: 3 }} was="BGB" />));
    await act(async () => ort.querySelector("button")!.click());
    expect(speichernDialog.mock.calls[0][0]).toMatchObject({ defaultPath: "BGB_Buergerliches-Gesetzbuch_Stand-2026-10-09.md" });
    expect(aufrufe).toEqual([
      { methode: "markdown.name", params: { gesetz: "BGB", fassung_id: 3 } },
      { methode: "markdown.speichern", params: { gesetz: "BGB", fassung_id: 3, pfad: "/tmp/BGB.md" } },
    ]);
    expect(ort.querySelector('[role="status"]')!.textContent).toContain("Gespeichert unter /tmp/BGB.md. Achtung:");
  });

  it("schreibt nichts, wenn der Dialog abgebrochen wird", async () => {
    speichernDialog.mockResolvedValue(null);
    await act(async () => wurzel.render(<MarkdownKnopf quelle={{ dokument_id: 7 }} was="Dokument" />));
    await act(async () => ort.querySelector("button")!.click());
    expect(aufrufe.map((a) => a.methode)).toEqual(["markdown.name"]);
    expect(ort.querySelector('[role="status"]')).toBeNull();
  });
});
