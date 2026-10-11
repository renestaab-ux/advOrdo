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
