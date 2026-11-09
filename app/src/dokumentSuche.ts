import { datumDe, dokumentName, type AktenDokument } from "./kern";

/** Klein, ohne Akzente und Umlautpunkte, ß wie ss: „rucktritt“ findet „Rücktritt“ (wie die Volltextsuche). */
export function vergleichbar(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLocaleLowerCase("de-DE")
    .replace(/ß/g, "ss");
}

type SuchbaresDokument = Pick<AktenDokument, "titel" | "dateiname" | "herkunft" | "art" | "datum" | "tags"> &
  Partial<Pick<AktenDokument, "absender">>;

/** Alles, was die Dokumentliste zu einem Dokument zeigt: Titel, Dateiname, Ordner, Art, Absender, Tags, Datum. */
export function suchText(d: SuchbaresDokument): string {
  const teile = [dokumentName(d), d.dateiname, d.herkunft ?? "", d.art ?? "", ...d.tags.map((t) => t.name)];
  if (d.absender) teile.push(d.absender.wert === "eigene" ? "uns" : d.absender.name);
  if (d.datum) teile.push(d.datum, datumDe(d.datum));
  return vergleichbar(teile.join(" "));
}

/**
 * Ob ein Dokument zur Eingabe im Suchfeld der Dokumentliste passt: jedes Wort muss irgendwo vorkommen, auch als
 * Wortteil („protokoll“ findet „Diagnoseprotokoll“). Sterne sind erlaubt und ändern nichts, Anführungszeichen
 * halten eine Wortfolge zusammen.
 */
export function dokumentPasst(d: SuchbaresDokument, eingabe: string): boolean {
  const woerter = suchWoerter(eingabe);
  if (woerter.length === 0) return true;
  const text = suchText(d);
  return woerter.every((w) => text.includes(w));
}

export function suchWoerter(eingabe: string): string[] {
  const woerter: string[] = [];
  for (const [, phrase, wort] of eingabe.matchAll(/["„“]([^"„“]*)["„“]?|(\S+)/g)) {
    const w = vergleichbar((phrase ?? wort ?? "").replace(/\*/g, " ").replace(/\s+/g, " ").trim());
    if (w) woerter.push(...(phrase != null ? [w] : w.split(" ")));
  }
  return woerter;
}
