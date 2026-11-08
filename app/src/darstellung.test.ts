import { describe, expect, it } from "vitest";
import { BARRIEREFREI_AN, BARRIEREFREI_AUS, VORGABE, darstellungLesen, fensterThema, modusAn, modusSetzen } from "./darstellung";

describe("darstellungLesen", () => {
  it("übernimmt gültige Werte", () => {
    expect(darstellungLesen('{"thema":"dunkel","akzent":"bordeaux","schrift":1.25}')).toEqual({
      thema: "dunkel",
      akzent: "bordeaux",
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
