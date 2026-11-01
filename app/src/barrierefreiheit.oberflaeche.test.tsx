// @vitest-environment jsdom
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import axe from "axe-core";
import App from "./App";

/**
 * Automatische Prüfung auf Barrieren (axe-core, Regeln nach WCAG 2.1 A/AA) in der Vorschau ohne Kern:
 * jeder Bereich der Leiste und jeder Reiter der Einstellungen, einmal normal und einmal im barrierefreien Modus.
 * Farbkontraste kann jsdom nicht berechnen; die stehen fest in styles.css.
 */
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let wurzel: Root;
let behaelter: HTMLDivElement;

beforeAll(async () => {
  // jsdom kann nicht zeichnen; axe kommt ohne aus.
  HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement["getContext"];
  window.matchMedia ??= ((q: string) =>
    ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }) as unknown as MediaQueryList);
  behaelter = document.createElement("div");
  document.body.appendChild(behaelter);
  wurzel = createRoot(behaelter);
  await act(async () => wurzel.render(<App />));
});

afterAll(() => {
  act(() => wurzel.unmount());
});

async function pruefe(): Promise<string[]> {
  const ergebnis = await axe.run(behaelter, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
    rules: { "color-contrast": { enabled: false } },
  });
  return ergebnis.violations.map(
    (v) => `${v.id}: ${v.help}\n  ${v.nodes.map((n) => n.html.slice(0, 140)).join("\n  ")}`,
  );
}

async function klicke(el: Element) {
  await act(async () => {
    (el as HTMLElement).click();
  });
}

function knopf(text: string, wo: ParentNode = document): HTMLElement {
  const k = Array.from(wo.querySelectorAll("button")).find((b) => b.textContent?.trim() === text);
  if (!k) throw new Error(`Knopf „${text}“ fehlt`);
  return k;
}

describe("Barrierefreiheit der Oberfläche", () => {
  it("jeder Bereich der Leiste ist ohne Befund", async () => {
    const nav = document.querySelector("nav.navigation")!;
    const befunde: string[] = [];
    const bereiche = Array.from(nav.querySelectorAll("button.nav-eintrag[aria-keyshortcuts]"));
    expect(bereiche.length).toBe(8);
    for (const k of bereiche) {
      await klicke(k);
      for (const b of await pruefe()) befunde.push(`[${k.textContent}] ${b}`);
    }
    expect(befunde).toEqual([]);
  });

  it("jeder Reiter der Einstellungen ist ohne Befund, auch im barrierefreien Modus", async () => {
    await klicke(knopf("Einstellungen", document.querySelector("nav.navigation")!));
    const befunde: string[] = [];
    const schalter = Array.from(document.querySelectorAll<HTMLInputElement>("label input")).find((i) =>
      i.parentElement?.textContent?.includes("Barrierefreier Modus"),
    );
    expect(schalter).toBeDefined();
    await klicke(schalter!);
    expect(document.documentElement.dataset.kontrast).toBe("an");
    const reiter = Array.from(document.querySelectorAll(".inhalt [role='tablist'] [role='tab']")).map(
      (b) => b.textContent?.trim() ?? "",
    );
    expect(reiter.length).toBeGreaterThan(3);
    for (const name of reiter) {
      await klicke(knopf(name, document.querySelector(".inhalt")!));
      expect(document.querySelector("[role='tab'][aria-selected='true']")?.textContent?.trim()).toBe(name);
      for (const b of await pruefe()) befunde.push(`[Einstellungen → ${name}] ${b}`);
    }
    expect(befunde).toEqual([]);
  });

  it("die Rechner der Toolbox sind ohne Befund", async () => {
    await klicke(knopf("Start", document.querySelector("nav.navigation")!));
    const kachel = Array.from(document.querySelectorAll(".inhalt button")).find((b) => b.textContent?.includes("Toolbox"));
    expect(kachel).toBeDefined();
    await klicke(kachel!);
    const werkzeuge = Array.from(document.querySelectorAll(".toolbox-reiter button")).map((b) => b.textContent?.trim() ?? "");
    expect(werkzeuge.length).toBeGreaterThan(1);
    const befunde: string[] = [];
    for (const name of werkzeuge) {
      await klicke(knopf(name, document.querySelector(".toolbox-reiter")!));
      for (const b of await pruefe()) befunde.push(`[Toolbox → ${name}] ${b}`);
    }
    expect(befunde).toEqual([]);
  });

  it("„Zum Inhalt springen“ steht vor der Leiste und führt zum Hauptbereich", () => {
    const erster = behaelter.querySelector("a, button");
    expect(erster?.textContent).toBe("Zum Inhalt springen");
    expect(document.getElementById("inhalt")?.tagName).toBe("MAIN");
  });
});
