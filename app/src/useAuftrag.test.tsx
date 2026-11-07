// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { KiAuftrag } from "./kern";

const stand = (status: KiAuftrag["status"]): KiAuftrag => ({
  auftrag_id: 7, aufgabe: "chat", status, text: "", schritt: null, von: null, sekunden: 1, ergebnis: null, fehler: null,
});
const antworten: KiAuftrag[] = [];
vi.mock("./kern", () => ({ kern: vi.fn(async () => antworten.shift() ?? stand("fertig")) }));
const { kern } = await import("./kern");
const { useAuftrag } = await import("./useAuftrag");

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function Probe({ id, gesehen }: { id: number | null; gesehen: string[] }) {
  useAuftrag(id, (a) => void gesehen.push(a.status), (e) => void gesehen.push(`fehler ${e}`));
  return null;
}

afterEach(() => vi.useRealTimers());

describe("useAuftrag", () => {
  it("fragt im Takt nach und hört nach dem Wechsel auf null auf", async () => {
    vi.useFakeTimers();
    antworten.push(stand("laeuft"), stand("fertig"));
    const gesehen: string[] = [];
    const wurzel = createRoot(document.createElement("div"));
    await act(async () => wurzel.render(<Probe id={7} gesehen={gesehen} />));
    await act(async () => void (await vi.advanceTimersByTimeAsync(2000)));
    expect(gesehen).toEqual(["laeuft", "fertig"]);
    expect(kern).toHaveBeenCalledWith("ki.auftrag", { auftrag_id: 7 });
    await act(async () => wurzel.render(<Probe id={null} gesehen={gesehen} />));
    await act(async () => void (await vi.advanceTimersByTimeAsync(3000)));
    expect(gesehen).toHaveLength(2);
    act(() => wurzel.unmount());
  });
});
