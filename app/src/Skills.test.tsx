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
  skills: [
    skill({}),
    skill({
      id: "b",
      name: "Vertragsprüfung",
      herkunft: "Importiert aus paket.zip",
      zeichen: 9000,
      passt: false,
      hinweise: ["Der Skill verweist auf Webseiten oder Online-Recherche."],
      nicht_uebernommen: ["references/checkliste.md"],
    }),
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

describe("Skills", () => {
  it("listet Skills mit Herkunft, Länge und Hinweisen, ohne Barrieren", async () => {
    await zeige(<SkillsEinstellungen />);
    const text = behaelter.textContent ?? "";
    expect(text).toContain("Angelegte Skills (2)");
    expect(text).toContain("Importiert aus paket.zip · 9.000 Zeichen");
    expect(text).toContain("zu lang für das aktive Sprachmodell (höchstens 6.144)");
    expect(text).toContain("Hinweise (2)");
    expect(text).toContain("rund 6.144 Zeichen");
    const ergebnis = await axe.run(behaelter, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
      rules: { "color-contrast": { enabled: false } },
    });
    expect(ergebnis.violations.map((v) => v.id)).toEqual([]);
  });

  it("Auswahl: zu lange Skills sind gesperrt, ein gelöschter Skill fällt auf „keiner“ zurück", async () => {
    const onWert = vi.fn();
    await zeige(<SkillWahl wert="weg" onWert={onWert} />);
    const optionen = [...behaelter.querySelectorAll("option")];
    expect(optionen.map((o) => o.textContent)).toEqual([
      "keiner",
      "Gegnerbrille",
      "Vertragsprüfung (zu lang für das Modell)",
    ]);
    expect(optionen[2].disabled).toBe(true);
    expect(onWert).toHaveBeenCalledWith("");
  });
});
