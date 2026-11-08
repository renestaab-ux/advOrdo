// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { bearbeitungenLeeren, offeneBearbeitungen, useBearbeitung, useUngespeichert } from "./ungespeichert";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function Formular() {
  const b = useBearbeitung("Beteiligter");
  return (
    <form {...b.formular} onSubmit={(e) => e.preventDefault()}>
      <input aria-label="Name" />
      <button type="submit">Speichern</button>
    </form>
  );
}

function Stammdaten({ geaendert }: { geaendert: boolean }) {
  useUngespeichert(geaendert, "Stammdaten der Akte", async () => true);
  return null;
}

function rahmen() {
  const el = document.createElement("div");
  document.body.appendChild(el);
  return { el, root: createRoot(el) };
}

afterEach(() => {
  bearbeitungenLeeren();
  document.body.innerHTML = "";
});

describe("offene Bearbeitungen", () => {
  it("Formular: Eingabe meldet an, Absenden und Schließen melden ab", () => {
    const { el, root } = rahmen();
    act(() => root.render(<Formular />));
    expect(offeneBearbeitungen()).toEqual([]);

    const feld = el.querySelector("input")!;
    act(() => {
      feld.value = "Kanzlei Ahrens";
      feld.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(offeneBearbeitungen().map((b) => b.was)).toEqual(["Beteiligter"]);

    act(() => el.querySelector("form")!.requestSubmit());
    expect(offeneBearbeitungen()).toEqual([]);

    act(() => feld.dispatchEvent(new Event("input", { bubbles: true })));
    expect(offeneBearbeitungen()).toHaveLength(1);
    act(() => root.unmount());
    expect(offeneBearbeitungen()).toEqual([]);
  });

  it("selbst gemeldet, mit Speichern", async () => {
    const { root } = rahmen();
    act(() => root.render(<Stammdaten geaendert={false} />));
    expect(offeneBearbeitungen()).toEqual([]);
    act(() => root.render(<Stammdaten geaendert />));
    const [b] = offeneBearbeitungen();
    expect(b.was).toBe("Stammdaten der Akte");
    expect(await b.speichern!()).toBe(true);
    act(() => root.render(<Stammdaten geaendert={false} />));
    expect(offeneBearbeitungen()).toEqual([]);
    act(() => root.unmount());
  });
});
