// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import axe from "axe-core";
import type { SkillQuelle, SkillQuellenPaket } from "./kern";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Frei erfundene Quelle.
const quelle: SkillQuelle = {
  id: "q1",
  adresse: "https://github.com/muster/sammlung",
  besitzer: "muster",
  repo: "sammlung",
  zweig: "main",
  pfad: "",
  titel: "muster/sammlung",
  beschreibung: "Skills zum Testen",
  art: "marktplatz",
  geladen_am: "2026-11-14T19:00:00+00:00",
  hinweis: null,
  pakete: [{ pfad: "mietrecht-pruefer", name: "mietrecht-pruefer", beschreibung: "Wohnraummiete", anzahl: null }],
};
let quellen: SkillQuelle[] = [];
const paket: SkillQuellenPaket = {
  quelle_id: "q1",
  pfad: "mietrecht-pruefer",
  name: "mietrecht-pruefer",
  skills: [
    { pfad: "mietrecht-pruefer/skills/betriebskosten/SKILL.md", name: "betriebskosten", importiert: false },
    { pfad: "mietrecht-pruefer/skills/kuendigung/SKILL.md", name: "kuendigung", importiert: true },
  ],
};
const aufrufe: { methode: string; params: Record<string, unknown> }[] = [];

vi.mock("./kern", async (original) => {
  const echt = await original<typeof import("./kern")>();
  const antwort = async (methode: string, params: Record<string, unknown> = {}) => {
    aufrufe.push({ methode, params });
    if (methode === "skills.quellen") return { quellen };
    if (methode === "skills.quelle_anbinden") {
      quellen = [quelle];
      return quelle;
    }
    if (methode === "skills.quelle_paket") return paket;
    if (methode === "skills.quelle_importieren")
      return { uebernommen: [{ name: "betriebskosten", ordner: "Mietrecht Prüfer" }], aktualisiert: [], uebersprungen: [] };
    throw new Error(`unerwartet: ${methode}`);
  };
  return { ...echt, istDesktop: true, kern: vi.fn(antwort), kernImHintergrund: vi.fn(antwort) };
});

const { default: SkillQuellen } = await import("./SkillQuellen");

let wurzel: Root;
let behaelter: HTMLDivElement;

beforeEach(() => {
  aufrufe.length = 0;
  quellen = [];
  behaelter = document.createElement("div");
  document.body.appendChild(behaelter);
  wurzel = createRoot(behaelter);
});

afterEach(() => {
  act(() => wurzel.unmount());
  behaelter.remove();
});

async function warte() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}

async function klicke(el: Element | null | undefined) {
  await act(async () => {
    (el as HTMLElement).click();
  });
  await warte();
}

const knopf = (text: string) => [...behaelter.querySelectorAll("button")].find((b) => b.textContent === text);

describe("Skill-Quellen", () => {
  it("bindet eine Quelle an, öffnet ein Paket und importiert markierte Skills", async () => {
    const onImportiert = vi.fn();
    await act(async () => wurzel.render(<SkillQuellen onImportiert={onImportiert} />));
    await warte();
    expect(behaelter.textContent).toContain("Noch keine Quelle angebunden.");

    const feld = behaelter.querySelector<HTMLInputElement>(".skill-quelle-neu input")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(feld, "muster/sammlung");
      feld.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      behaelter.querySelector("form")!.requestSubmit();
    });
    await warte();
    expect(aufrufe.find((a) => a.methode === "skills.quelle_anbinden")?.params).toEqual({ adresse: "muster/sammlung" });
    expect(behaelter.textContent).toContain("Quelle „muster/sammlung“ angebunden: 1 Paket.");

    await klicke(knopf("Skills anzeigen"));
    expect(behaelter.textContent).toContain("kuendigung · schon übernommen");
    expect((knopf("Markierte importieren") as HTMLButtonElement).disabled).toBe(true);
    const ergebnis = await axe.run(behaelter, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
      rules: { "color-contrast": { enabled: false } },
    });
    expect(ergebnis.violations.map((v) => v.id)).toEqual([]);

    await klicke(behaelter.querySelector(".skill-quellen-skills input"));
    await klicke(knopf("1 Skill importieren"));
    expect(aufrufe.find((a) => a.methode === "skills.quelle_importieren")?.params).toEqual({
      quelle_id: "q1",
      pfade: ["mietrecht-pruefer/skills/betriebskosten/SKILL.md"],
    });
    expect(onImportiert).toHaveBeenCalled();
    expect(behaelter.textContent).toContain("1 Skill übernommen in den Ordner „Mietrecht Prüfer“.");
  });
});
