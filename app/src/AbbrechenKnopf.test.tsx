// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { AbbrechenKnopf } from "./AbbrechenKnopf";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let wurzel: Root | null = null;
let feld: HTMLDivElement | null = null;

function zeige(element: React.ReactElement) {
  feld = document.createElement("div");
  document.body.append(feld);
  wurzel = createRoot(feld);
  act(() => wurzel!.render(element));
  return feld.querySelector("button")!;
}

afterEach(() => {
  act(() => wurzel?.unmount());
  feld?.remove();
});

describe("AbbrechenKnopf", () => {
  it("zeigt sofort nach dem Klick „Bricht ab …“ und sperrt sich", async () => {
    const onAbbrechen = vi.fn(async () => {});
    const knopf = zeige(<AbbrechenKnopf auftrag={{ auftrag_id: 3 }} onAbbrechen={onAbbrechen} />);
    expect(knopf.textContent).toBe("Abbrechen");
    await act(async () => knopf.click());
    expect(onAbbrechen).toHaveBeenCalledTimes(1);
    expect(knopf.textContent).toBe("Bricht ab …");
    expect(knopf.disabled).toBe(true);
  });

  it("folgt dem Stand des Kerns", () => {
    const knopf = zeige(<AbbrechenKnopf auftrag={{ auftrag_id: 3, abbruch: true }} onAbbrechen={() => {}} />);
    expect(knopf.textContent).toBe("Bricht ab …");
  });

  it("gibt den Knopf wieder frei, wenn das Abbrechen scheitert", async () => {
    const knopf = zeige(<AbbrechenKnopf auftrag={{ auftrag_id: 3 }} onAbbrechen={() => Promise.reject(new Error("weg"))} />);
    await act(async () => knopf.click());
    expect(knopf.textContent).toBe("Abbrechen");
  });
});
