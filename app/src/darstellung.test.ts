import { describe, expect, it } from "vitest";
import { VORGABE, darstellungLesen } from "./darstellung";

describe("darstellungLesen", () => {
  it("übernimmt gültige Werte", () => {
    expect(darstellungLesen('{"thema":"dunkel","akzent":"bordeaux","schrift":1.25}')).toEqual({
      thema: "dunkel",
      akzent: "bordeaux",
      schrift: 1.25,
    });
  });

  it("fällt bei Unbekanntem oder kaputtem Eintrag auf die Vorgabe zurück", () => {
    expect(darstellungLesen('{"thema":"lila","akzent":"pink","schrift":3}')).toEqual(VORGABE);
    expect(darstellungLesen("kein json")).toEqual(VORGABE);
    expect(darstellungLesen(null)).toEqual(VORGABE);
  });
});
