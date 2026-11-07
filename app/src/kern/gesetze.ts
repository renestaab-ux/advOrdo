export interface Fassung {
  id: number;
  quelle: string;
  abgerufen_am: string;
  builddate: string | null;
  stand: string[];
  sha256: string;
  hinweis: string;
}

export interface GesetzEintrag {
  abk: string;
  langtitel: string | null;
  fassung_id: number;
  abgerufen_am: string;
  builddate: string | null;
  stand: string[];
  fassungen: number;
  normen: number;
}

export interface Voreinstellung {
  abk: string;
  kuerzel: string;
  titel: string;
  gruppe: string;
  pakete: string[];
  quelle?: "bayern";
}

export interface GesetzesPaket {
  id: string;
  titel: string;
  beschreibung: string;
  teil_von?: string;
  /** Schalter gesetzt */
  aktiv: boolean;
  /** an und, falls Teil eines anderen Pakets, dieses auch an */
  wirksam: boolean;
  gesetze: number;
}

/** Gesetze eines Pakets, nach Gruppen in der Reihenfolge der Liste. */
export function paketGruppen(gesetze: Voreinstellung[], paket: string): [string, Voreinstellung[]][] {
  const gruppen = new Map<string, Voreinstellung[]>();
  for (const g of gesetze) {
    if (!g.pakete.includes(paket)) continue;
    gruppen.set(g.gruppe, [...(gruppen.get(g.gruppe) ?? []), g]);
  }
  return [...gruppen];
}

export interface ImportErgebnis {
  abk: string;
  neu: boolean;
  normen?: number | null;
  hinweis?: string;
  fehler?: string;
}

export interface Treffer {
  id: number;
  abk: string;
  bezeichnung: string;
  titel: string | null;
  weggefallen: number;
  ausschnitt: string;
}

export interface Satz {
  nr: number;
  text: string;
  nummern: [string, string][];
}

export interface Norm {
  gesetz: string;
  langtitel: string | null;
  bezeichnung: string;
  titel: string | null;
  gliederung: string[];
  weggefallen: boolean;
  absaetze: { nr: string | null; text: string; saetze: Satz[] }[];
  fassung: Fassung;
}

export interface Beleg {
  zitat: string;
  status: "belegt" | "nicht_gefunden" | "unbekanntes_gesetz";
  wortlaut: string | null;
  hinweis: string | null;
  norm?: string;
  titel?: string | null;
  fassung: Fassung | null;
}

/** Erkennt, ob eine Eingabe ein Normzitat ist ("§ 280 Abs. 1 BGB") statt eines Suchbegriffs. */
export function istZitat(eingabe: string): boolean {
  return /^\s*(§§?|Art\.|Artikel)\s*\d+[a-z]?\b.*\s(?:[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]*[A-ZÄÖÜ]|Rom[ -]?I{1,2}(?:[ -]?VO)?)\s*$/.test(eingabe);
}

/** Datumsstempel der Quelle ("20260901120000") lesbar machen. */
export function formatiereBuilddate(b: string | null): string {
  if (!b || b.length < 8) return "unbekannt";
  return `${b.slice(6, 8)}.${b.slice(4, 6)}.${b.slice(0, 4)}`;
}
