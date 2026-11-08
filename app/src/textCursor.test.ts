import { describe, expect, it } from "vitest";
import { auswahlSchritt } from "./textCursor";

describe("auswahlSchritt", () => {
  it("bewegt ohne Umschalt und erweitert mit Umschalt", () => {
    expect(auswahlSchritt("ArrowRight", false, false)).toEqual({ art: "move", richtung: "forward", einheit: "character" });
    expect(auswahlSchritt("ArrowLeft", true, false)).toEqual({ art: "extend", richtung: "backward", einheit: "character" });
  });
  it("Strg springt wortweise bzw. absatzweise", () => {
    expect(auswahlSchritt("ArrowRight", true, true)?.einheit).toBe("word");
    expect(auswahlSchritt("ArrowDown", false, true)?.einheit).toBe("paragraphboundary");
    expect(auswahlSchritt("ArrowUp", false, false)?.einheit).toBe("line");
  });
  it("Pos1 und Ende gehen an den Zeilen- bzw. Textrand", () => {
    expect(auswahlSchritt("Home", true, false)).toEqual({ art: "extend", richtung: "backward", einheit: "lineboundary" });
    expect(auswahlSchritt("End", false, true)?.einheit).toBe("documentboundary");
  });
  it("andere Tasten bleiben dem Browser", () => {
    expect(auswahlSchritt("PageDown", false, false)).toBeNull();
    expect(auswahlSchritt("a", true, false)).toBeNull();
  });
});
