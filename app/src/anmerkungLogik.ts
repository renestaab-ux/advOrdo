/**
 * Markierungen und Kommentare an Dokumenten: Typen und reine Hilfsfunktionen (ohne DOM, getestet in
 * anmerkungLogik.test.ts). Die Oberfläche steht in Anmerkungen.tsx.
 *
 * Lage einer Markierung: Zeichenpositionen im Text des Dokuments, dessen Abschnitte mit je einem Zeilenumbruch
 * verbunden sind (wie im Kern, juracore/dokumente/anmerkungen.py).
 */

export type AnmerkFarbe = "gelb" | "gruen" | "blau" | "rot";
export type AnmerkStil = "flaeche" | "unterstrichen" | "durchgestrichen";

export const FARBEN: AnmerkFarbe[] = ["gelb", "gruen", "blau", "rot"];
export const FARB_NAME: Record<AnmerkFarbe, string> = { gelb: "Gelb", gruen: "Grün", blau: "Blau", rot: "Rot" };
export const STILE: { stil: AnmerkStil; name: string }[] = [
  { stil: "flaeche", name: "Farbig hinterlegen" },
  { stil: "unterstrichen", name: "Unterstreichen" },
  { stil: "durchgestrichen", name: "Durchstreichen" },
];

export type Bedeutungen = Record<AnmerkFarbe, string>;
export const BEDEUTUNG_VORGABE: Bedeutungen = { gelb: "Wichtig", gruen: "Erledigt", blau: "Beweis", rot: "Streitig" };

export interface Anmerkung {
  id: number;
  dokument_id: number;
  /** Heute nur "markierung"; später kommen Lesezeichen und Freihand hinzu. */
  art: string;
  farbe: AnmerkFarbe;
  stil: AnmerkStil;
  start: number | null;
  ende: number | null;
  zitat: string | null;
  seite: number | null;
  abschnitt: number | null;
  rn: number | null;
  /** Markdown; null = ohne Kommentar. */
  kommentar: string | null;
  /** "nicht_gefunden": Der Wortlaut steht nach einer Änderung des Texts nicht mehr im Dokument. */
  status: "gefunden" | "nicht_gefunden";
  angelegt_am: string;
  geaendert_am: string;
  dokument?: string;
  dateiname?: string;
  akte_id?: number;
  akte?: string;
}

/** Anmerkung im Original-PDF: dazu die Rechtecke auf der Seite (Anteile von Breite und Höhe). */
export interface AnmerkungAufSeite extends Anmerkung {
  rechtecke: { x: number; y: number; b: number; h: number }[];
}

/** Beginn jedes Abschnitts im Text des Dokuments. */
export function abschnittBeginne(abschnitte: { text: string }[]): number[] {
  const beginne: number[] = [];
  let pos = 0;
  for (const a of abschnitte) {
    beginne.push(pos);
    pos += a.text.length + 1;
  }
  return beginne;
}

export interface Stueck {
  /** Lage im Abschnitt. */
  von: number;
  bis: number;
  /** Markierungen, die das Stück abdecken, die zuletzt angelegte zuletzt. */
  anmerkungen: Anmerkung[];
  /** Das Stück ist das Ende dieser Markierungen (dort steht die Sprechblase des Kommentars). */
  endeVon: Anmerkung[];
}

/**
 * Zerlegt den Bereich ``von``–``bis`` eines Abschnitts (der bei ``beginn`` im Dokument anfängt) an den Grenzen der
 * Markierungen. Stücke ohne Markierung sind dabei, damit der ganze Bereich abgedeckt ist.
 */
export function stuecke(von: number, bis: number, beginn: number, anmerkungen: Anmerkung[]): Stueck[] {
  const relevant = anmerkungen.filter(
    (a) => a.status === "gefunden" && a.start != null && a.ende != null && a.start - beginn < bis && a.ende - beginn > von,
  );
  if (relevant.length === 0) return [{ von, bis, anmerkungen: [], endeVon: [] }];
  const grenzen = new Set([von, bis]);
  for (const a of relevant) {
    grenzen.add(Math.min(Math.max(a.start! - beginn, von), bis));
    grenzen.add(Math.min(Math.max(a.ende! - beginn, von), bis));
  }
  const punkte = [...grenzen].sort((x, y) => x - y);
  const ergebnis: Stueck[] = [];
  for (let i = 0; i + 1 < punkte.length; i++) {
    const [s, e] = [punkte[i], punkte[i + 1]];
    if (e <= s) continue;
    const decken = relevant
      .filter((a) => a.start! - beginn < e && a.ende! - beginn > s)
      .sort((x, y) => x.id - y.id);
    ergebnis.push({ von: s, bis: e, anmerkungen: decken, endeVon: decken.filter((a) => a.ende! - beginn === e) });
  }
  return ergebnis;
}

/** CSS-Klassen eines markierten Stücks: Farbe der zuletzt angelegten Fläche, dazu Unter- und Durchstreichungen. */
export function stueckKlassen(anmerkungen: Anmerkung[]): string {
  const klassen = ["anm"];
  const flaeche = [...anmerkungen].reverse().find((a) => a.stil === "flaeche");
  if (flaeche) klassen.push(`anm-${flaeche.farbe}`);
  const unter = [...anmerkungen].reverse().find((a) => a.stil === "unterstrichen");
  if (unter) klassen.push("anm-unter", `anm-linie-${unter.farbe}`);
  const durch = [...anmerkungen].reverse().find((a) => a.stil === "durchgestrichen");
  if (durch) klassen.push("anm-durch", `anm-linie-${durch.farbe}`);
  return klassen.join(" ");
}

export interface AnmerkFilter {
  /** Leer = alle Farben. */
  farben: AnmerkFarbe[];
  nurKommentar: boolean;
  suche: string;
}

export const KEIN_ANMERK_FILTER: AnmerkFilter = { farben: [], nurKommentar: false, suche: "" };

/** Für die Suche vergleichbar: klein, ohne Akzente und Umlautpunkte („rucktritt“ findet „Rücktritt“). */
export function vergleichbar(text: string): string {
  return text.normalize("NFKD").replace(/\p{M}/gu, "").toLocaleLowerCase("de");
}

export function filtereAnmerkungen(liste: Anmerkung[], f: AnmerkFilter, bedeutungen: Bedeutungen): Anmerkung[] {
  const woerter = vergleichbar(f.suche).replace(/["*]/g, " ").split(/\s+/).filter(Boolean);
  return liste.filter((a) => {
    if (f.farben.length > 0 && !f.farben.includes(a.farbe)) return false;
    if (f.nurKommentar && !a.kommentar) return false;
    if (woerter.length === 0) return true;
    const heu = vergleichbar([a.zitat ?? "", a.kommentar ?? "", bedeutungen[a.farbe] ?? "", a.dokument ?? ""].join(" "));
    return woerter.every((w) => heu.includes(w));
  });
}

/** Ort einer Anmerkung für die Liste, z. B. „S. 3“, „Rn. 12“ oder „nicht mehr gefunden“. */
export function anmerkungOrt(a: Pick<Anmerkung, "seite" | "rn" | "abschnitt" | "status">): string {
  if (a.status === "nicht_gefunden") return "Stelle nicht mehr gefunden";
  const teile: string[] = [];
  if (a.seite != null) teile.push(`S. ${a.seite}`);
  if (a.rn != null) teile.push(`Rn. ${a.rn}`);
  if (teile.length === 0 && a.abschnitt != null) teile.push(`Abschn. ${a.abschnitt}`);
  return teile.join(", ");
}

// --- Markdown für Kommentare -----------------------------------------------------------------------------------------

export interface Inline {
  text: string;
  fett?: boolean;
  kursiv?: boolean;
  code?: boolean;
}

export type Block =
  | { art: "absatz"; zeilen: Inline[][] }
  | { art: "liste"; geordnet: boolean; punkte: Inline[][] }
  | { art: "code"; text: string };

/** Zerlegt eine Zeile in Text, **fett**, *kursiv* (auch _kursiv_) und `Code`. HTML wird nie ausgewertet. */
export function inline(zeile: string): Inline[] {
  const teile: Inline[] = [];
  const muster = /`([^`]+)`|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*\s][^*]*)\*|(?<![\p{L}\d])_([^_\s][^_]*)_(?![\p{L}\d])/gu;
  let pos = 0;
  for (const m of zeile.matchAll(muster)) {
    if (m.index! > pos) teile.push({ text: zeile.slice(pos, m.index) });
    if (m[1] != null) teile.push({ text: m[1], code: true });
    else if (m[2] != null || m[3] != null) teile.push(...inline(m[2] ?? m[3]).map((t) => ({ ...t, fett: true })));
    else teile.push(...inline(m[4] ?? m[5]).map((t) => ({ ...t, kursiv: true })));
    pos = m.index! + m[0].length;
  }
  if (pos < zeile.length) teile.push({ text: zeile.slice(pos) });
  return teile;
}

/** Einfaches Markdown: Absätze, Listen (-, *, 1.), Code-Blöcke (```), dazu fett, kursiv und Code im Text. */
export function markdownBloecke(text: string): Block[] {
  const bloecke: Block[] = [];
  const zeilen = text.replace(/\r\n?/g, "\n").split("\n");
  for (let i = 0; i < zeilen.length; i++) {
    const zeile = zeilen[i];
    if (/^\s*```/.test(zeile)) {
      const inhalt: string[] = [];
      for (i++; i < zeilen.length && !/^\s*```/.test(zeilen[i]); i++) inhalt.push(zeilen[i]);
      bloecke.push({ art: "code", text: inhalt.join("\n") });
      continue;
    }
    const punkt = zeile.match(/^\s*(?:([-*•])|(\d+)[.)])\s+(.*)$/);
    const letzter = bloecke[bloecke.length - 1];
    if (punkt) {
      const geordnet = punkt[2] != null;
      if (letzter?.art === "liste" && letzter.geordnet === geordnet) letzter.punkte.push(inline(punkt[3]));
      else bloecke.push({ art: "liste", geordnet, punkte: [inline(punkt[3])] });
      continue;
    }
    if (!zeile.trim()) {
      bloecke.push({ art: "absatz", zeilen: [] });
      continue;
    }
    if (letzter?.art === "absatz" && letzter.zeilen.length > 0) letzter.zeilen.push(inline(zeile));
    else bloecke.push({ art: "absatz", zeilen: [inline(zeile)] });
  }
  return bloecke.filter((b) => b.art !== "absatz" || b.zeilen.length > 0);
}

/** Kommentar ohne Markdown-Zeichen, z. B. für Vorschau und Tooltip. */
export function kommentarText(text: string, laenge = 160): string {
  const rein = markdownBloecke(text)
    .map((b) =>
      b.art === "code" ? b.text : (b.art === "liste" ? b.punkte : b.zeilen).map((z) => z.map((t) => t.text).join("")).join(" "),
    )
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
  return rein.length > laenge ? `${rein.slice(0, laenge - 1)}…` : rein;
}

/**
 * Setzt Markdown um die Auswahl eines Eingabefelds (Fett, Kursiv, Code) oder vor die gewählten Zeilen (Liste).
 * Ergebnis: neuer Text und neue Auswahl.
 */
export function formatiere(
  text: string,
  von: number,
  bis: number,
  art: "fett" | "kursiv" | "code" | "liste" | "codeblock",
): { text: string; von: number; bis: number } {
  if (art === "liste") {
    const anfang = text.lastIndexOf("\n", von - 1) + 1;
    const ausgewaehlt = text.slice(anfang, bis);
    const neu = ausgewaehlt
      .split("\n")
      .map((z) => (/^\s*[-*•]\s/.test(z) ? z : `- ${z}`))
      .join("\n");
    return { text: text.slice(0, anfang) + neu + text.slice(bis), von: anfang, bis: anfang + neu.length };
  }
  if (art === "codeblock") {
    const vor = von > 0 && text[von - 1] !== "\n" ? "\n" : "";
    const neu = `${vor}\`\`\`\n${text.slice(von, bis)}\n\`\`\`\n`;
    return { text: text.slice(0, von) + neu + text.slice(bis), von: von + vor.length + 4, bis: von + vor.length + 4 + (bis - von) };
  }
  const zeichen = art === "fett" ? "**" : art === "kursiv" ? "*" : "`";
  const neu = zeichen + text.slice(von, bis) + zeichen;
  return { text: text.slice(0, von) + neu + text.slice(bis), von: von + zeichen.length, bis: bis + zeichen.length };
}
