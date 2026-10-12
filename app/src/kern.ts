// Zugriff auf den Python-Analysekern. Die Desktop-App leitet jeden Aufruf
// per Tauri-Befehl an den Kernprozess weiter (JSON über stdin/stdout, kein Netzwerkport).
import { invoke } from "@tauri-apps/api/core";

export const istDesktop = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export async function kern<T>(methode: string, params: Record<string, unknown> = {}): Promise<T> {
  if (!istDesktop) {
    throw new Error("Der Analysekern ist nur in der Desktop-App verfügbar (npm run tauri dev).");
  }
  return invoke<T>("kern_aufruf", { methode, params });
}

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
  return /^\s*(§§?|Art\.|Artikel)\s*\d+[a-z]?\b.*\s[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]*[A-ZÄÖÜ]\s*$/.test(eingabe);
}

/** Datumsstempel der Quelle ("20260901120000") lesbar machen. */
export function formatiereBuilddate(b: string | null): string {
  if (!b || b.length < 8) return "unbekannt";
  return `${b.slice(6, 8)}.${b.slice(4, 6)}.${b.slice(0, 4)}`;
}

// --- Akten ---------------------------------------------------------------------------------------

export type ZitatStatus = Beleg["status"];

export interface Akte {
  id: number;
  name: string;
  angelegt_am: string;
  dokumente: number;
}

export interface AktenDokument {
  id: number;
  akte_id: number;
  dateiname: string;
  format: "pdf" | "docx" | "txt" | "md";
  sha256: string;
  seiten: number | null;
  lesart: "textebene" | "ocr" | "gemischt" | "datei" | "leer";
  ocr_konfidenz: number | null;
  hinweise: string[];
  importiert_am: string;
  randnummern: number;
  zitate: Partial<Record<ZitatStatus, number>>;
  /** Unterordner beim Ordner-Import, z. B. "Kläger/Anlagen". */
  herkunft: string | null;
  tags: Tag[];
}

export interface Tag {
  name: string;
  /** "ordner": aus dem Ordnernamen übernommen, "manuell": von Hand gesetzt. */
  quelle: "ordner" | "manuell";
}

export interface OrdnerFunde {
  ordner: string;
  name: string;
  dateien: { pfad: string; relativ: string; herkunft: string }[];
  unterordner: { herkunft: string; dateien: number; tags: string[] }[];
  uebersprungen: string[];
}

export interface Loeschergebnis {
  name?: string;
  dateiname?: string;
  hinweis: string | null;
}

export interface NormZitat {
  start: number;
  ende: number;
  treffer_start: number;
  treffer_ende: number;
  seite: number | null;
  zitat: string;
  gesetz: string;
  status: ZitatStatus;
  fassung_id: number | null;
  norm: string | null;
  titel: string | null;
  hinweis: string | null;
}

export interface Abschnitt {
  nr: number;
  seite: number | null;
  seite_bis: number | null;
  rn: number | null;
  art: "absatz" | "tabelle" | "fussnote";
  text: string;
  zitate: NormZitat[];
}

export interface DokumentInhalt {
  dokument: AktenDokument;
  abschnitte: Abschnitt[];
}

export interface Fundstelle {
  dokument_id: number;
  dateiname: string;
  abschnitt: number;
  seite: number | null;
  rn: number | null;
}

export interface NormEintrag {
  zitat: string;
  gesetz: string;
  status: ZitatStatus;
  fassung_id: number | null;
  norm: string | null;
  titel: string | null;
  hinweis: string | null;
  fundstellen: Fundstelle[];
}

export interface AktenImport {
  dateiname: string;
  dokument_id: number;
  neu: boolean;
  lesart?: AktenDokument["lesart"];
  zitate?: Partial<Record<ZitatStatus, number>>;
  hinweise?: string[];
}

export interface OcrStatus {
  verfuegbar: boolean;
  programm?: string;
  version?: string;
  hinweis?: string;
}

export const STATUS_TEXT: Record<ZitatStatus, string> = {
  belegt: "belegt",
  nicht_gefunden: "existiert nicht",
  unbekanntes_gesetz: "nicht in Wissensbasis",
};

/** Fundstelle im Dokument lesbar: "S. 2–3, Rn. 5" oder "Abschn. 12" (laufender Absatz), wenn weder Seite noch Randnummer bekannt sind. */
export function fundstelle(a: { seite: number | null; seite_bis?: number | null; rn: number | null; nr?: number; abschnitt?: number }): string {
  const teile: string[] = [];
  if (a.seite != null) teile.push(a.seite_bis ? `S. ${a.seite}–${a.seite_bis}` : `S. ${a.seite}`);
  if (a.rn != null) teile.push(`Rn. ${a.rn}`);
  if (teile.length === 0) teile.push(`Abschn. ${a.nr ?? a.abschnitt ?? "?"}`);
  return teile.join(", ");
}

/** Woher der Text stammt, für die Dokumentliste. */
export function lesartText(d: Pick<AktenDokument, "lesart" | "ocr_konfidenz" | "format">): string {
  switch (d.lesart) {
    case "textebene":
      return "PDF mit Text";
    case "ocr":
    case "gemischt": {
      const k = d.ocr_konfidenz != null ? `, Erkennung ${Math.round(d.ocr_konfidenz)} %` : "";
      return `${d.lesart === "ocr" ? "Scan" : "PDF teils Scan"} (Texterkennung${k})`;
    }
    case "datei":
      return d.format === "docx" ? "Word" : d.format === "md" ? "Markdown" : "Text";
    default:
      return "kein Text";
  }
}

export type Segment = { text: string; zitat?: NormZitat };

/** Zerlegt einen Abschnitt in Text und Normzitate, damit Zitate anklickbar dargestellt werden können. */
export function segmente(text: string, zitate: NormZitat[]): Segment[] {
  const ergebnis: Segment[] = [];
  let pos = 0;
  for (const z of [...zitate].sort((a, b) => a.start - b.start)) {
    if (z.start < pos || z.ende > text.length) continue; // überlappend oder außerhalb: als Text lassen
    if (z.start > pos) ergebnis.push({ text: text.slice(pos, z.start) });
    ergebnis.push({ text: text.slice(z.start, z.ende), zitat: z });
    pos = z.ende;
  }
  if (pos < text.length) ergebnis.push({ text: text.slice(pos) });
  return ergebnis;
}

/** Tags aus einer Eingabe wie "Kläger, Anlage K 1": getrennt an Komma oder Semikolon, ohne Dubletten. */
export function tagsAusText(text: string): string[] {
  const gesehen = new Map<string, string>();
  for (const teil of text.split(/[,;]/)) {
    const tag = teil.replace(/\s+/g, " ").trim();
    if (tag && !gesehen.has(tag.toLocaleLowerCase("de"))) gesehen.set(tag.toLocaleLowerCase("de"), tag);
  }
  return [...gesehen.values()];
}

/** Alle Tags einer Akte mit der Zahl der Dokumente, die sie tragen; Beteiligte zuerst. */
export function tagUebersicht(dokumente: Pick<AktenDokument, "tags">[]): { name: string; anzahl: number }[] {
  const zaehlung = new Map<string, number>();
  for (const d of dokumente) for (const t of d.tags) zaehlung.set(t.name, (zaehlung.get(t.name) ?? 0) + 1);
  return sortiereTags([...zaehlung.entries()].map(([name, anzahl]) => ({ name, anzahl })));
}

/** Beteiligte in ihrer üblichen Reihenfolge zuerst, danach alle übrigen Tags alphabetisch. */
export function sortiereTags<T extends { name: string }>(tags: T[]): T[] {
  const rang = (name: string) => {
    const i = BETEILIGTE.indexOf(name);
    return i < 0 ? BETEILIGTE.length : i;
  };
  return [...tags].sort((a, b) => rang(a.name) - rang(b.name) || a.name.localeCompare(b.name, "de"));
}

/** Die üblichen Beteiligten, als schnelle Auswahl beim Bearbeiten und für die Reihenfolge. */
export const BETEILIGTE = ["Kläger", "Beklagter", "Gericht", "Streitverkündeter", "Sachverständiger"];
