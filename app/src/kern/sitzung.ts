// Terminmodus des Arbeitsfensters: Sitzungsblatt (Anträge, Streitpunkte) und Terminsnotizen (core: aktenverwaltung/sitzung.py).

export type PunktArt = "antrag" | "streitpunkt";
export type Ampel = "rot" | "gelb" | "gruen";
export type TerminNotizArt = "notiz" | "hinweis" | "vergleich" | "zeuge" | "auflage";

export const PUNKT_AMPEL_TEXT: Record<Ampel, string> = { rot: "kritisch", gelb: "offen", gruen: "günstig" };

export const TERMIN_NOTIZ_ARTEN: { art: TerminNotizArt; titel: string }[] = [
  { art: "notiz", titel: "Notiz" },
  { art: "hinweis", titel: "Hinweis des Gerichts" },
  { art: "vergleich", titel: "Vergleichsvorschlag" },
  { art: "zeuge", titel: "Zeugenaussage" },
  { art: "auflage", titel: "Frist / Auflage" },
];

export interface PunktBeleg {
  dokument_id: number;
  abschnitt: number | null;
  rn: number | null;
  bezeichnung: string;
}

export interface SitzungsPunkt {
  id: number;
  akte_id: number;
  art: PunktArt;
  text: string;
  ampel: Ampel | null;
  belege: PunktBeleg[];
  /** "ki": aus einem Vorschlag der Analyse übernommen. */
  herkunft: "eigen" | "ki";
}

export interface TerminNotiz {
  id: number;
  sitzung_id: number;
  /** ISO-Zeitpunkt, zu dem die Notiz gespeichert wurde. */
  zeit: string;
  art: TerminNotizArt;
  art_text: string;
  text: string;
  dokument_id: number | null;
  dokument: string | null;
}

export interface Sitzung {
  id: number;
  akte_id: number;
  kalender_id: number | null;
  titel: string;
  beginn: string;
  ende: string | null;
  uebernommen: { notiz: boolean; zeit: number | null; fristen: number } | null;
  notizen: TerminNotiz[];
}

export interface TerminHeute {
  id: number;
  titel: string;
  datum: string;
  uhrzeit: string | null;
  ort: string | null;
}

export interface FristVorschlag {
  notiz_id: number;
  titel: string;
  /** "datum": festes Datum aus der Notiz; "dauer": Dauer ab dem Termintag über den Fristenrechner. */
  art: "datum" | "dauer";
  anzahl: number | null;
  einheit: string | null;
  /** null, wenn der Beginn an einem späteren Ereignis hängt (``beginn_offen``). */
  bezugstag: string | null;
  datum: string | null;
  verschoben: boolean;
  grund: string | null;
  /** Bei festem Datum: Wochentag oder Feiertag, wenn der Tag kein Werktag ist. */
  kein_werktag: string | null;
  /** „Zustellung des Protokolls“: Beginn steht noch nicht fest, das Datum trägt man ein, sobald es bekannt ist. */
  beginn_offen: string | null;
  quelle: string;
}

export interface SitzungsAbschluss {
  protokoll: string;
  minuten: number;
  fristen: FristVorschlag[];
  taetigkeit: string;
}

/** Uhrzeit „10:34“ aus einem ISO-Zeitpunkt. */
export function uhrzeitVon(iso: string): string {
  return iso.slice(11, 16);
}

/** Laufzeit „0:41:12“ zwischen zwei Zeitpunkten (Millisekunden). */
export function laufzeit(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}:${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
