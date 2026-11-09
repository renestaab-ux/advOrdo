import { describe, expect, it } from "vitest";
import { spracheErkennen, sprachenImDokument } from "./sprache";

// Erfundene Beispielsätze.
const DE =
  "Die Klägerin hat die Leistung vollständig erbracht. Der Beklagte ist mit der Zahlung in Verzug, da er auf die " +
  "Rechnung vom 1. September nicht reagiert hat und auch nach der Mahnung keine Zahlung geleistet wurde.";
const EN =
  "The Seller shall deliver the goods to the Buyer within thirty days. Any claim arising from this agreement is " +
  "governed by the laws of Germany, and the parties have agreed that the courts of Munich are competent.";
const FR =
  "Le vendeur est tenu de livrer les marchandises dans un délai de trente jours. Les parties ont convenu que le " +
  "tribunal de Paris est compétent pour tout litige qui pourrait naître de ce contrat.";
const PT =
  "O vendedor deve entregar as mercadorias no prazo de trinta dias. As partes acordaram que o foro da comarca de " +
  "São Paulo é competente para qualquer litígio decorrente deste contrato e que não há outra cláusula.";

describe("Sprache erkennen", () => {
  it("erkennt Deutsch, Englisch, Französisch und Portugiesisch", () => {
    expect(spracheErkennen(DE)).toBe("de");
    expect(spracheErkennen(EN)).toBe("en");
    expect(spracheErkennen(FR)).toBe("fr");
    expect(spracheErkennen(PT)).toBe("pt");
  });

  it("lässt kurze Texte, Aktenzeichen und Namen offen", () => {
    expect(spracheErkennen("Anlage K 3")).toBeNull();
    expect(spracheErkennen("BGH, Urteil vom 21.10.2014 – XI ZR 210/13")).toBeNull();
    expect(spracheErkennen("Dr. Clara Linden Rechtsanwältin Kanzlei Linden & Partner Musterstraße 1 79000 Teststadt")).toBeNull();
  });

  it("zeichnet im deutschen Schriftsatz nur den englischen Absatz aus", () => {
    const r = sprachenImDokument([DE, EN, DE, "Anlage K 3"]);
    expect(r.dokument).toBe("de");
    expect(r.absaetze).toEqual([undefined, "en", undefined, undefined]);
  });

  it("englischer Vertrag: Dokument englisch, deutscher Vermerk abweichend", () => {
    const r = sprachenImDokument([EN, EN, DE]);
    expect(r.dokument).toBe("en");
    expect(r.absaetze).toEqual([undefined, undefined, "de"]);
  });
});
