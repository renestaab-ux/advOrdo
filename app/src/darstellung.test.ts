import { describe, expect, it } from "vitest";
import { AKZENTE, BARRIEREFREI_AN, BARRIEREFREI_AUS, VORGABE, darstellungLesen, fensterThema, modusAn, modusSetzen, musterHintergrund } from "./darstellung";

describe("darstellungLesen", () => {
  it("übernimmt gültige Werte", () => {
    expect(darstellungLesen('{"thema":"dunkel","akzent":"bordeaux","schrift":1.25}')).toEqual({
      thema: "dunkel",
      akzent: "bordeaux",
      leiste: "farbig",
      schrift: 1.25,
      barrierefrei: BARRIEREFREI_AUS,
    });
  });

  it("fällt bei Unbekanntem oder kaputtem Eintrag auf die Vorgabe zurück", () => {
    expect(darstellungLesen('{"thema":"lila","akzent":"pink","schrift":3}')).toEqual(VORGABE);
    expect(darstellungLesen("kein json")).toEqual(VORGABE);
    expect(darstellungLesen(null)).toEqual(VORGABE);
  });
});

describe("barrierefreier Modus", () => {
  it("liest einzelne Hilfen und übergeht Unbekanntes", () => {
    const d = darstellungLesen('{"barrierefrei":{"kontrast":true,"fokus":"ja","laut":true}}');
    expect(d.barrierefrei).toEqual({ ...BARRIEREFREI_AUS, kontrast: true });
    expect(modusAn(d.barrierefrei)).toBe(false);
  });

  it("alte Einträge ohne Barrierefreiheit gelten als aus", () => {
    expect(darstellungLesen('{"thema":"hell"}').barrierefrei).toEqual(BARRIEREFREI_AUS);
  });

  it("der Hauptschalter schaltet alle Hilfen ein und vergrößert die Schrift mindestens auf Sehr groß", () => {
    const an = modusSetzen(VORGABE, true);
    expect(an.barrierefrei).toEqual(BARRIEREFREI_AN);
    expect(modusAn(an.barrierefrei)).toBe(true);
    expect(an.schrift).toBe(1.25);
    expect(modusSetzen({ ...VORGABE, schrift: 1.5 }, true).schrift).toBe(1.5);
  });

  it("aus schaltet nur die Hilfen ab und lässt die Schriftgröße stehen", () => {
    const aus = modusSetzen(modusSetzen(VORGABE, true), false);
    expect(aus.barrierefrei).toEqual(BARRIEREFREI_AUS);
    expect(aus.schrift).toBe(1.25);
  });

  it("Extra groß ist eine gültige Schriftgröße", () => {
    expect(darstellungLesen('{"schrift":1.5}').schrift).toBe(1.5);
  });
});

describe("fensterThema", () => {
  it("übersetzt die Wahl für die Titelleiste", () => {
    expect(fensterThema({ ...VORGABE, thema: "hell" })).toBe("light");
    expect(fensterThema({ ...VORGABE, thema: "dunkel" })).toBe("dark");
    expect(fensterThema(VORGABE)).toBeNull();
  });
});

describe("Farbakzente in zwei Nuancen", () => {
  const leuchtdichte = (hex: string) => {
    const k = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * k[0] + 0.7152 * k[1] + 0.0722 * k[2];
  };

  it("weiße Schrift auf der hellen Nuance bleibt gut lesbar (WCAG 4,5 : 1)", () => {
    for (const a of AKZENTE) for (const n of [a.hell, a.dunkel]) expect(1.05 / (leuchtdichte(n.hell) + 0.05), a.id).toBeGreaterThanOrEqual(4.5);
  });

  it("das Muster ist hart in zwei Hälften geteilt", () => {
    expect(musterHintergrund({ dunkel: "#000000", hell: "#336699" })).toBe("linear-gradient(90deg, #000000 50%, #336699 50%)");
  });

  it("bei weißer Leiste steht links weiß bzw. im Dunkelmodus die neutrale Fläche", () => {
    expect(musterHintergrund({ dunkel: "#000000", hell: "#336699" }, "weiss")).toBe("linear-gradient(90deg, #ffffff 50%, #336699 50%)");
    expect(musterHintergrund({ dunkel: "#000000", hell: "#336699" }, "weiss", true)).toBe("linear-gradient(90deg, #242528 50%, #336699 50%)");
  });

  it("liest die Leiste und fällt bei Unbekanntem auf farbig zurück", () => {
    expect(darstellungLesen('{"leiste":"weiss"}').leiste).toBe("weiss");
    expect(darstellungLesen('{"leiste":"gelb"}').leiste).toBe("farbig");
    expect(darstellungLesen('{"akzent":"gruen"}').leiste).toBe("farbig");
  });
});
