/**
 * Arbeitsfenster einer Akte: welche Spalten es zeigt und wie breit sie sind. Reine Logik ohne Oberfläche, damit sie
 * sich ohne Fenster prüfen lässt; die Oberfläche steht in ``Arbeitsfenster.tsx``.
 *
 * Die Anordnung wird je Akte auf diesem Gerät gemerkt (localStorage), ebenso Lage und Größe des Fensters.
 */

export type SpaltenArt =
  | "leer"
  | "dokument"
  | "notizen"
  | "anmerkungen"
  | "normen"
  | "rechtsprechung"
  | "sitzungsblatt"
  | "terminsnotizen";

/** Was eine Spalte zeigt. Bei einem Dokument auch welches und ob als Text oder Original. */
export interface Spalte {
  art: SpaltenArt;
  dokumentId?: number | null;
  modus?: "text" | "original";
  /** Fundstelle, zu der nach dem Öffnen gesprungen wird (Abschnitt im Text oder Seite im Original); wird nicht gemerkt. */
  abschnitt?: number | null;
  seite?: number | null;
  /** Randnummer, zu der gesprungen wird (Springen „Rn. 14“, Beleg im Sitzungsblatt); wird nicht gemerkt. */
  rn?: number | null;
}

export interface Anordnung {
  spalten: Spalte[];
  /** Anteile der Spalten an der Breite (Summe 1); null: alle gleich breit. */
  anteile: number[] | null;
}

export const MIN_SPALTEN = 1;
export const MAX_SPALTEN = 4;
/** Kleinster Anteil einer Spalte, damit keine beim Ziehen verschwindet. */
export const MIN_ANTEIL = 0.12;

export const SPALTEN_ARTEN: { art: SpaltenArt; titel: string }[] = [
  { art: "dokument", titel: "Dokument" },
  { art: "notizen", titel: "Notizen" },
  { art: "anmerkungen", titel: "Anmerkungen und Lesezeichen" },
  { art: "normen", titel: "Normen der Akte" },
  { art: "rechtsprechung", titel: "Rechtsprechung der Akte" },
  { art: "sitzungsblatt", titel: "Sitzungsblatt" },
  { art: "terminsnotizen", titel: "Terminsnotizen" },
];

const ARTEN = new Set<SpaltenArt>(["leer", ...SPALTEN_ARTEN.map((a) => a.art)]);

/** Zwei Spalten: links ein Dokument, rechts die Notizen. */
export function standardAnordnung(): Anordnung {
  return { spalten: [{ art: "dokument", dokumentId: null, modus: "text" }, { art: "notizen" }], anteile: null };
}

/** Prüft eine gespeicherte Anordnung; Unbekanntes oder Kaputtes fällt auf den Standard zurück. */
export function anordnungPruefen(wert: unknown): Anordnung {
  const w = wert as { spalten?: unknown; anteile?: unknown } | null;
  if (!w || typeof w !== "object" || !Array.isArray(w.spalten)) return standardAnordnung();
  const spalten: Spalte[] = w.spalten.slice(0, MAX_SPALTEN).map((s: unknown) => {
    const t = s as Partial<Spalte> | null;
    const art = t && ARTEN.has(t.art as SpaltenArt) ? (t.art as SpaltenArt) : "leer";
    if (art !== "dokument") return { art };
    return {
      art,
      dokumentId: typeof t?.dokumentId === "number" ? t.dokumentId : null,
      modus: t?.modus === "original" ? "original" : "text",
    };
  });
  if (spalten.length < MIN_SPALTEN) return standardAnordnung();
  return { spalten, anteile: anteilePruefen(w.anteile, spalten.length) };
}

function anteilePruefen(wert: unknown, anzahl: number): number[] | null {
  if (!Array.isArray(wert) || wert.length !== anzahl) return null;
  if (!wert.every((a) => typeof a === "number" && Number.isFinite(a) && a >= MIN_ANTEIL / 2)) return null;
  const summe = wert.reduce((s: number, a: number) => s + a, 0);
  return wert.map((a: number) => a / summe);
}

/** Anordnung zum Speichern: ohne Sprungziele, die nur für den Augenblick gelten. */
export function zumSpeichern(a: Anordnung): Anordnung {
  return {
    spalten: a.spalten.map((s) => (s.art === "dokument" ? { art: s.art, dokumentId: s.dokumentId ?? null, modus: s.modus ?? "text" } : { art: s.art })),
    anteile: a.anteile,
  };
}

/** Anzahl der Spalten ändern: neue Spalten kommen leer dazu, überzählige fallen rechts weg. */
export function spaltenZahl(a: Anordnung, anzahl: number): Anordnung {
  const n = Math.min(MAX_SPALTEN, Math.max(MIN_SPALTEN, Math.round(anzahl)));
  if (n === a.spalten.length) return a;
  const spalten = a.spalten.slice(0, n);
  while (spalten.length < n) spalten.push({ art: "leer" });
  return { spalten, anteile: null };
}

/** Eine Spalte schließen; die letzte bleibt immer stehen. */
export function spalteEntfernen(a: Anordnung, index: number): Anordnung {
  if (a.spalten.length <= MIN_SPALTEN || index < 0 || index >= a.spalten.length) return a;
  return { spalten: a.spalten.filter((_, i) => i !== index), anteile: null };
}

export function spalteSetzen(a: Anordnung, index: number, spalte: Spalte): Anordnung {
  return { ...a, spalten: a.spalten.map((s, i) => (i === index ? spalte : s)) };
}

/** Anteile, auch wenn keine gespeichert sind (dann gleich). */
export function anteileVon(a: Anordnung): number[] {
  return a.anteile ?? a.spalten.map(() => 1 / a.spalten.length);
}

/**
 * Trennlinie ``index`` (zwischen Spalte ``index`` und ``index + 1``) um ``delta`` (Anteil der Gesamtbreite)
 * verschieben. Nur die beiden Nachbarn ändern sich; keine wird schmaler als ``MIN_ANTEIL``.
 */
export function trennerVerschieben(a: Anordnung, index: number, delta: number): Anordnung {
  const anteile = [...anteileVon(a)];
  if (index < 0 || index >= anteile.length - 1) return a;
  const paar = anteile[index] + anteile[index + 1];
  const links = Math.min(Math.max(anteile[index] + delta, MIN_ANTEIL), paar - MIN_ANTEIL);
  anteile[index] = links;
  anteile[index + 1] = paar - links;
  return { ...a, anteile };
}

/**
 * Wohin ein Dokument aus Spalte ``von`` geöffnet wird (Fundstelle aus Normen, Rechtsprechung oder Anmerkungen):
 * in die nächste andere Spalte, die schon ein Dokument zeigt; sonst in eine leere; sonst kommt eine Spalte dazu,
 * solange Platz ist; sonst in die rechte Nachbarspalte (bei der letzten: die linke). Die Liste, aus der geöffnet
 * wird, bleibt damit stehen. Eine Dokument-Spalte öffnet in sich selbst.
 */
export function zielSpalte(a: Anordnung, von: number): { anordnung: Anordnung; index: number } {
  const n = a.spalten.length;
  if (a.spalten[von]?.art === "dokument") return { anordnung: a, index: von };
  const nachAbstand = [...Array(n).keys()].filter((i) => i !== von).sort((x, y) => Math.abs(x - von) - Math.abs(y - von) || x - y);
  const dok = nachAbstand.find((i) => a.spalten[i].art === "dokument");
  if (dok != null) return { anordnung: a, index: dok };
  const leer = nachAbstand.find((i) => a.spalten[i].art === "leer");
  if (leer != null) return { anordnung: a, index: leer };
  if (n < MAX_SPALTEN) {
    const spalten = [...a.spalten];
    spalten.splice(von + 1, 0, { art: "leer" });
    return { anordnung: { spalten, anteile: null }, index: von + 1 };
  }
  return { anordnung: a, index: von < n - 1 ? von + 1 : von - 1 };
}

/**
 * Anordnung für den Gerichtstermin: Sitzungsblatt, ein Dokument (das erste aus der bisherigen Anordnung, sonst zur
 * Auswahl) und die Terminsnotizen. Die bisherige Anordnung wird gemerkt und nach dem Termin wiederhergestellt.
 */
export function terminAnordnung(alt: Anordnung): Anordnung {
  const dok = alt.spalten.find((s) => s.art === "dokument");
  return {
    spalten: [
      { art: "sitzungsblatt" },
      { art: "dokument", dokumentId: dok?.dokumentId ?? null, modus: dok?.modus ?? "text" },
      { art: "terminsnotizen" },
    ],
    anteile: [0.3, 0.4, 0.3],
  };
}

const VOR_TERMIN = (akteId: number) => `arbeitsfenster.vor-termin.${akteId}`;

/** Anordnung vor dem Termin merken (nur, wenn nicht schon eine gemerkt ist: ein zweiter Start überschreibt sie nicht). */
export function vorTerminMerken(akteId: number, a: Anordnung) {
  if (lesen(VOR_TERMIN(akteId)) == null) schreiben(VOR_TERMIN(akteId), zumSpeichern(a));
}

/** Anordnung von vor dem Termin zurückholen (und vergessen); ohne gemerkte: die Standardanordnung. */
export function vorTerminHolen(akteId: number): Anordnung {
  const w = lesen(VOR_TERMIN(akteId));
  try {
    localStorage.removeItem(VOR_TERMIN(akteId));
  } catch {
    // Ohne Speicher gibt es auch nichts zu vergessen.
  }
  return w == null ? standardAnordnung() : anordnungPruefen(w);
}

// --------------------------------------------------------------------------- Springen (Strg+K)

/** Ziel eines Sprungs: ein Dokument, wahlweise an einer Randnummer oder einem Abschnitt. */
export interface SprungZiel {
  titel: string;
  hinweis: string;
  dokumentId: number;
  abschnitt?: number;
  rn?: number;
}

interface SprungDokument {
  id: number;
  name: string;
  tags: string[];
}

interface SprungNorm {
  zitat: string;
  fundstellen: { dokument_id: number; dateiname: string; abschnitt: number; seite: number | null; rn: number | null }[];
}

/** Für den Vergleich: klein, ohne Leerzeichen und Punkte („Anlage K 2“ → „anlagek2“, „§ 477“ → „§477“). */
function knapp(t: string): string {
  return t.toLowerCase().replace(/[\s.]+/g, "");
}

/** Kurzbezeichnung einer Anlage aus einem Tag („Anlage K 2“ → „K 2“, „B1“ → „B 1“), sonst null. */
export function anlageAusTag(tag: string): string | null {
  const m = /^(?:anlagen?\s*)?([A-Za-zÄÖÜäöü]{1,3})\s*(\d{1,3}[a-z]?)$/i.exec(tag.trim());
  if (!m || (!/^anlage/i.test(tag.trim()) && m[1].length > 2)) return null;
  return `${m[1].toUpperCase()} ${m[2]}`;
}

/**
 * Treffer für die Eingabe im Springen-Feld:
 * - „K 2“, „B1“, „Anlage K 3“: Dokumente mit diesem Anlagen-Tag (aus „Tag hinzufügen“ bzw. dem Ordnernamen),
 * - „Rn. 14“ oder „Rn 14“: diese Randnummer in den Dokumenten, die gerade in einer Spalte offen sind,
 * - „§ 477“, „Art. 6“: Fundstellen dieses Normzitats in der Akte,
 * - sonst: Dokumente, deren Name oder Tag den Text enthält.
 */
export function springTreffer(
  eingabe: string,
  dokumente: SprungDokument[],
  normen: SprungNorm[],
  offen: number[],
  max = 12,
): SprungZiel[] {
  const e = eingabe.trim();
  if (!e) return [];
  const name = (id: number) => dokumente.find((d) => d.id === id)?.name ?? `Dokument ${id}`;

  const rn = /^rn\.?\s*(\d{1,4})$/i.exec(e);
  if (rn) {
    const n = Number(rn[1]);
    return [...new Set(offen)].map((id) => ({ titel: `Rn. ${n}`, hinweis: name(id), dokumentId: id, rn: n }));
  }

  if (/^(§§?|art\.?)\s*\d/i.test(e)) {
    const k = knapp(e);
    const aus: SprungZiel[] = [];
    for (const n of normen) {
      if (!knapp(n.zitat).startsWith(k)) continue;
      for (const f of n.fundstellen) {
        const ort = f.rn != null ? `Rn. ${f.rn}` : f.seite != null ? `S. ${f.seite}` : `Abschnitt ${f.abschnitt}`;
        aus.push({ titel: n.zitat, hinweis: `${f.dateiname}, ${ort}`, dokumentId: f.dokument_id, abschnitt: f.abschnitt });
      }
    }
    return aus.slice(0, max);
  }

  const anlage = anlageAusTag(e);
  if (anlage) {
    const treffer = dokumente.filter((d) => d.tags.some((t) => anlageAusTag(t) === anlage));
    if (treffer.length) return treffer.slice(0, max).map((d) => ({ titel: `Anlage ${anlage}`, hinweis: d.name, dokumentId: d.id }));
  }

  const k = knapp(e);
  return dokumente
    .filter((d) => knapp(d.name).includes(k) || d.tags.some((t) => knapp(t).includes(k)))
    .slice(0, max)
    .map((d) => {
      const tag = d.tags.map(anlageAusTag).find((a) => a != null);
      return { titel: d.name, hinweis: tag ? `Anlage ${tag}` : "Dokument", dokumentId: d.id };
    });
}

/** Lage und Größe des Fensters in Bildschirmpunkten (physisch), wie Tauri sie meldet. */
export interface FensterLage {
  x: number;
  y: number;
  breite: number;
  hoehe: number;
}

export function lagePruefen(wert: unknown): FensterLage | null {
  const w = wert as Partial<FensterLage> | null;
  if (!w || typeof w !== "object") return null;
  const zahlen = [w.x, w.y, w.breite, w.hoehe];
  if (!zahlen.every((z) => typeof z === "number" && Number.isFinite(z))) return null;
  if (w.breite! < 200 || w.hoehe! < 150) return null;
  return { x: Math.round(w.x!), y: Math.round(w.y!), breite: Math.round(w.breite!), hoehe: Math.round(w.hoehe!) };
}

const ANORDNUNG = (akteId: number) => `arbeitsfenster.anordnung.${akteId}`;
const LAGE = (akteId: number) => `arbeitsfenster.lage.${akteId}`;

function lesen(schluessel: string): unknown {
  try {
    const t = localStorage.getItem(schluessel);
    return t ? JSON.parse(t) : null;
  } catch {
    return null;
  }
}

function schreiben(schluessel: string, wert: unknown) {
  try {
    localStorage.setItem(schluessel, JSON.stringify(wert));
  } catch {
    // Ohne Speicher gilt die Anordnung nur, solange das Fenster offen ist.
  }
}

export function gemerkteAnordnung(akteId: number): Anordnung {
  const w = lesen(ANORDNUNG(akteId));
  return w == null ? standardAnordnung() : anordnungPruefen(w);
}

export function anordnungMerken(akteId: number, a: Anordnung) {
  schreiben(ANORDNUNG(akteId), zumSpeichern(a));
}

export function gemerkteLage(akteId: number): FensterLage | null {
  return lagePruefen(lesen(LAGE(akteId)));
}

export function lageMerken(akteId: number, lage: FensterLage) {
  if (lagePruefen(lage)) schreiben(LAGE(akteId), lage);
}

/** Bezeichnung des Fensters für Tauri: eines je Akte. Muss zu ``capabilities/arbeitsfenster.json`` passen. */
export function fensterName(akteId: number): string {
  return `akte-${akteId}`;
}
