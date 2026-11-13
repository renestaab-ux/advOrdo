// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import axe from "axe-core";
import type { Skill, SkillListe } from "./kern";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function skill(teil: Partial<Skill>): Skill {
  return {
    id: "a",
    name: "Gegnerbrille",
    beschreibung: "Liest aus Sicht der Gegenseite",
    text: "Lies alles aus Sicht der Gegenseite.",
    herkunft: "Eigener Skill",
    ordner: "",
    angelegt_am: "2026-11-13T12:00:00+00:00",
    geaendert_am: "2026-11-13T12:00:00+00:00",
    nicht_uebernommen: [],
    zeichen: 36,
    hinweise: [],
    hoechstens: 6144,
    passt: true,
    ...teil,
  };
}

const liste: SkillListe = {
  kontext: 8192,
  // Reihenfolge wie vom Kern: nach Ordner, ohne Ordner zuletzt.
  skills: [
    skill({
      id: "b",
      name: "Vertragsprüfung",
      herkunft: "Importiert aus paket.zip",
      ordner: "BGB AT Prüfer",
      zeichen: 9000,
      passt: false,
      hinweise: ["Der Skill verweist auf Webseiten oder Online-Recherche."],
      nicht_uebernommen: ["references/checkliste.md"],
    }),
    skill({}),
  ],
};

const aufrufe: { methode: string; params: Record<string, unknown> }[] = [];

vi.mock("./kern", async (original) => ({
  ...(await original<typeof import("./kern")>()),
  istDesktop: true,
  kern: vi.fn(async (methode: string, params: Record<string, unknown> = {}) => {
    aufrufe.push({ methode, params });
    if (methode === "skills.liste") return liste;
    throw new Error(`unerwartet: ${methode}`);
  }),
}));

const { default: SkillsEinstellungen, SkillWahl } = await import("./Skills");

let wurzel: Root;
let behaelter: HTMLDivElement;

beforeEach(() => {
  aufrufe.length = 0;
  behaelter = document.createElement("div");
  document.body.appendChild(behaelter);
  wurzel = createRoot(behaelter);
});

afterEach(() => {
  act(() => wurzel.unmount());
  behaelter.remove();
});

async function zeige(el: React.ReactElement) {
  await act(async () => wurzel.render(el));
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}

async function klicke(el: Element | null) {
  await act(async () => {
    (el as HTMLElement).click();
  });
}

async function tippe(el: HTMLInputElement, text: string) {
  await act(async () => {
    const setze = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setze.call(el, text);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function barrierefrei() {
  const ergebnis = await axe.run(behaelter, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    rules: { "color-contrast": { enabled: false } },
  });
  return ergebnis.violations.map((v) => v.id);
}

describe("Skills", () => {
  it("listet Skills nach Ordnern mit Herkunft, Länge und Hinweisen, ohne Barrieren", async () => {
    await zeige(<SkillsEinstellungen />);
    const text = behaelter.textContent ?? "";
    expect(text).toContain("Angelegte Skills (2)");
    expect([...behaelter.querySelectorAll(".skill-ordner > summary")].map((x) => x.textContent)).toEqual([
      "BGB AT Prüfer (1)",
      "Ohne Ordner (1)",
    ]);
    expect(text).toContain("Importiert aus paket.zip · 9.000 Zeichen");
    expect(text).toContain("zu lang für das aktive Sprachmodell (höchstens 6.144)");
    expect(text).toContain("Hinweise (2)");
    expect(text).toContain("rund 6.144 Zeichen");
    expect(await barrierefrei()).toEqual([]);

    await tippe(behaelter.querySelector<HTMLInputElement>(".skill-suche")!, "vertrag");
    expect([...behaelter.querySelectorAll(".skill-ordner > summary")].map((x) => x.textContent)).toEqual([
      "BGB AT Prüfer (1 von 1)",
    ]);
  });

  it("Auswahl mit Suche, Ordnern und „Alle“; Gelöschtes fällt heraus", async () => {
    const onWert = vi.fn();
    await zeige(<SkillWahl wert={["weg", "a"]} onWert={onWert} />);
    expect(onWert).toHaveBeenCalledWith(["a"]);

    await zeige(<SkillWahl wert={["a"]} onWert={onWert} />);
    const knopf = behaelter.querySelector("button")!;
    expect(knopf.textContent).toBe("Skills: Gegnerbrille ▾");
    await klicke(knopf);
    expect(knopf.getAttribute("aria-expanded")).toBe("true");
    expect(await barrierefrei()).toEqual([]);

    // Ordner sind eingeklappt; die Suche zeigt die passenden Skills.
    expect(behaelter.querySelectorAll(".skill-gruppe li")).toHaveLength(0);
    await tippe(behaelter.querySelector<HTMLInputElement>("input[type=search]")!, "gegner");
    const treffer = [...behaelter.querySelectorAll(".skill-gruppe li")];
    expect(treffer.map((x) => x.textContent)).toEqual([" Gegnerbrille"]);
    expect(treffer[0].querySelector<HTMLInputElement>("input")!.checked).toBe(true);

    await tippe(behaelter.querySelector<HTMLInputElement>("input[type=search]")!, "");
    const ordner = [...behaelter.querySelectorAll(".skill-gruppe-kopf input")][0];
    await klicke(ordner);
    expect(onWert).toHaveBeenLastCalledWith(["a", "ordner:BGB AT Prüfer"]);
    await klicke(behaelter.querySelector(".skill-alle input"));
    expect(onWert).toHaveBeenLastCalledWith(["alle"]);
  });
});
