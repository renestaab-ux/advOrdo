import { KalenderEintrag } from "./kern";

/** Was im Kalender als eigener Posten erscheint; Vorfristen stehen an ihrem eigenen Tag. */
export type PostenTyp = "frist" | "vorfrist" | "termin" | "wiedervorlage";
export const POSTEN_TEXT: Record<PostenTyp, string> = {
  frist: "Frist",
  vorfrist: "Vorfrist",
  termin: "Termin",
  wiedervorlage: "Wiedervorlage",
};

export interface KalenderPosten {
  schluessel: string;
  tag: string;
  typ: PostenTyp;
  /** Bei Vorfristen: erste oder zweite. */
  nr?: 1 | 2;
  eintrag: KalenderEintrag;
}

export type Ansicht = "monat" | "woche" | "liste";

export interface KalenderFilter {
  arten: PostenTyp[];
  zustand: "offen" | "alle" | "abgeschlossen";
  akteId: number | null;
  gericht: string;
  nurAbgelaufen: boolean;
}

export const FILTER_START: KalenderFilter = {
  arten: ["frist", "vorfrist", "termin", "wiedervorlage"],
  zustand: "alle",
  akteId: null,
  gericht: "",
  nurAbgelaufen: false,
};

/** JJJJ-MM-TT eines lokalen Datums. */
export function isoTag(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function ausIso(iso: string): Date {
  const [j, m, t] = iso.split("-").map(Number);
  return new Date(j, m - 1, t);
}

export function plusTage(iso: string, tage: number): string {
  const d = ausIso(iso);
  d.setDate(d.getDate() + tage);
  return isoTag(d);
}

/** Montag der Woche, in der der Tag liegt. */
export function wochenbeginn(iso: string): string {
  const d = ausIso(iso);
  return plusTage(iso, -((d.getDay() + 6) % 7));
}

/** Sichtbarer Zeitraum einer Ansicht um den Bezugstag: Monat als 6 volle Wochen, Woche Mo–So, Liste 4 Wochen. */
export function zeitraumVon(ansicht: Ansicht, bezug: string): { von: string; bis: string } {
  if (ansicht === "monat") {
    const von = wochenbeginn(`${bezug.slice(0, 7)}-01`);
    return { von, bis: plusTage(von, 41) };
  }
  if (ansicht === "woche") {
    const von = wochenbeginn(bezug);
    return { von, bis: plusTage(von, 6) };
  }
  return { von: bezug, bis: plusTage(bezug, 27) };
}

/** Bezugstag eine Seite weiter (+1) oder zurück (-1). */
export function blaettern(ansicht: Ansicht, bezug: string, richtung: 1 | -1): string {
  if (ansicht === "monat") {
    const d = ausIso(`${bezug.slice(0, 7)}-01`);
    d.setMonth(d.getMonth() + richtung);
    return isoTag(d);
  }
  return plusTage(bezug, richtung * (ansicht === "woche" ? 7 : 28));
}

/** Überschrift des Zeitraums: „November 2026“, „KW 45: 02.11.–08.11.2026“ oder „02.11.–29.11.2026“. */
export function zeitraumTitel(ansicht: Ansicht, bezug: string): string {
  const kurz = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}.`;
  if (ansicht === "monat") return ausIso(bezug).toLocaleDateString("de-DE", { month: "long", year: "numeric" });
  const { von, bis } = zeitraumVon(ansicht, bezug);
  const spanne = `${kurz(von)}–${kurz(bis)}${bis.slice(0, 4)}`;
  return ansicht === "woche" ? `KW ${kalenderwoche(von)}: ${spanne}` : spanne;
}

/** Kalenderwoche nach ISO 8601. */
export function kalenderwoche(iso: string): number {
  const d = ausIso(iso);
  const donnerstag = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 3 - ((d.getDay() + 6) % 7));
  const erster = new Date(donnerstag.getFullYear(), 0, 4);
  return 1 + Math.round(((donnerstag.getTime() - erster.getTime()) / 86400000 - 3 + ((erster.getDay() + 6) % 7)) / 7);
}

/**
 * Posten im Zeitraum nach Filter: jede Frist an ihrem Ende, dazu ihre Vorfristen an deren Tagen (nur solange die
 * Frist offen ist), Termine und Wiedervorlagen an ihrem Tag. Sortiert nach Tag und Uhrzeit.
 */
export function posten(eintraege: KalenderEintrag[], filter: KalenderFilter, von: string, bis: string): KalenderPosten[] {
  const liste: KalenderPosten[] = [];
  const drin = (tag: string) => tag >= von && tag <= bis;
  for (const e of eintraege) {
    if (filter.akteId != null && e.akte_id !== filter.akteId) continue;
    if (filter.gericht && (e.gericht ?? "") !== filter.gericht) continue;
    if (filter.zustand === "offen" && e.abgeschlossen) continue;
    if (filter.zustand === "abgeschlossen" && !e.abgeschlossen) continue;
    if (filter.nurAbgelaufen && e.lage !== "abgelaufen") continue;
    if (filter.arten.includes(e.art) && drin(e.datum)) {
      liste.push({ schluessel: `${e.id}`, tag: e.datum, typ: e.art, eintrag: e });
    }
    if (e.art === "frist" && !e.abgeschlossen && !filter.nurAbgelaufen && filter.arten.includes("vorfrist")) {
      ([e.vorfrist, e.vorfrist2] as (string | null)[]).forEach((v, i) => {
        if (v && drin(v)) liste.push({ schluessel: `${e.id}-v${i + 1}`, tag: v, typ: "vorfrist", nr: (i + 1) as 1 | 2, eintrag: e });
      });
    }
  }
  return liste.sort(
    (a, b) =>
      a.tag.localeCompare(b.tag) ||
      (a.eintrag.uhrzeit ?? "").localeCompare(b.eintrag.uhrzeit ?? "") ||
      a.eintrag.id - b.eintrag.id,
  );
}

/** Farbklasse eines Postens: Fristen nach Lage, Vorfrist gelb, Termin, Wiedervorlage; Abgeschlossenes blass. */
export function postenKlasse(p: KalenderPosten): string {
  const e = p.eintrag;
  if (p.typ === "vorfrist") return "kal-posten vorfrist";
  if (e.abgeschlossen) return `kal-posten ${p.typ} abgeschlossen ${e.lage}`;
  return `kal-posten ${p.typ} ${e.lage}`;
}
