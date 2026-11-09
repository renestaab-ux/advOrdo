// Zugriff auf den Python-Analysekern. Die Desktop-App leitet jeden Aufruf
// per Tauri-Befehl an den Kernprozess weiter (JSON über stdin/stdout, kein Netzwerkport).
import { invoke } from "@tauri-apps/api/core";
import { aenderungMelden } from "../aenderungen";

export const istDesktop = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export async function kern<T>(methode: string, params: Record<string, unknown> = {}): Promise<T> {
  if (!istDesktop) {
    throw new Error("Der Analysekern ist nur in der Desktop-App verfügbar (npm run tauri dev).");
  }
  const ergebnis = await invoke<T>("kern_aufruf", { methode, params });
  if (methode.startsWith("ki.") || methode === "akten.metadaten_ki") kiPruefen(ergebnis);
  // Andere Fenster (Arbeitsfenster der Akten) laden geänderte Notizen, Anmerkungen und Lesezeichen nach.
  void aenderungMelden(methode);
  return ergebnis;
}

// --- Lange Befehle im Hintergrund ---------------------------------------------------------------
// Importe und Online-Abrufe laufen im Kern in einem eigenen Thread (hintergrund.starten); die Oberfläche fragt
// nach Fortschritt und Ergebnis. So reagiert die App währenddessen, und die Warteanzeige (Hintergrund.tsx) kann
// abbrechen.

export interface HintergrundAuftrag {
  auftrag_id: number;
  aufgabe: string;
  titel: string;
  /** KI-Auftrag (ki.auftrag, abbrechen mit ki.abbrechen) statt Befehl des Kerns (hintergrund.auftrag). */
  ki?: boolean;
  status: "laeuft" | "fertig" | "fehler" | "abgebrochen";
  text: string;
  schritt: number | null;
  von: number | null;
  sekunden: number;
  ergebnis: unknown;
  fehler: string | null;
}

const hintergrundLaufend = new Map<number, HintergrundAuftrag>();
const hintergrundBeobachter = new Set<(liste: HintergrundAuftrag[]) => void>();

// Läuft eine KI-Aufgabe (Analyse, Chat, Vorschläge für Details), zeigt die Warteanzeige sie ebenfalls. Sie startet
// in verschiedenen Bereichen; deshalb schaut jede Antwort eines ki.*-Aufrufs, ob ein Auftrag läuft, und solange
// einer läuft, fragt `kiBeobachten` jede Sekunde mit ki.laufend nach (es läuft höchstens einer zugleich).
let kiLaufend: HintergrundAuftrag | null = null;
let kiSchleife = false;

export function laeuftKi(wert: unknown): boolean {
  const w = wert as { status?: unknown; auftrag_id?: unknown; auftrag?: { status?: unknown } } | null;
  return !!w && typeof w === "object" && ((w.status === "laeuft" && "auftrag_id" in w) || w.auftrag?.status === "laeuft");
}

function kiPruefen(ergebnis: unknown) {
  if (laeuftKi(ergebnis)) void kiBeobachten();
}

/** Fragt, solange ein KI-Auftrag läuft, nach seinem Stand; beim Start der App einmal aufrufen. */
export async function kiBeobachten(): Promise<void> {
  if (kiSchleife || !istDesktop) return;
  kiSchleife = true;
  try {
    for (;;) {
      let a: HintergrundAuftrag | null = null;
      try {
        a = await invoke<HintergrundAuftrag | null>("kern_aufruf", { methode: "ki.laufend", params: {} });
      } catch {
        a = null; // Kern nicht erreichbar: Anzeige ausblenden, der nächste ki.*-Aufruf schaut wieder
      }
      kiLaufend = a && a.status === "laeuft" ? { ...a, ki: true } : null;
      hintergrundMelden();
      if (!kiLaufend) return;
      await new Promise((weiter) => setTimeout(weiter, 1000));
    }
  } finally {
    kiSchleife = false;
  }
}

function hintergrundMelden() {
  const liste = [...(kiLaufend ? [kiLaufend] : []), ...hintergrundLaufend.values()];
  hintergrundBeobachter.forEach((f) => f(liste));
}

function hintergrundSetzen(a: HintergrundAuftrag) {
  if (a.status === "laeuft") hintergrundLaufend.set(a.auftrag_id, a);
  else hintergrundLaufend.delete(a.auftrag_id);
  hintergrundMelden();
}

/** Meldet die laufenden Hintergrundaufträge dieses Fensters; gibt die Abmeldung zurück. */
export function beobachteHintergrund(f: (liste: HintergrundAuftrag[]) => void): () => void {
  hintergrundBeobachter.add(f);
  f([...(kiLaufend ? [kiLaufend] : []), ...hintergrundLaufend.values()]);
  return () => {
    hintergrundBeobachter.delete(f);
  };
}

export async function hintergrundAbbrechen(auftragId: number, ki = false): Promise<void> {
  if (ki) {
    const a = await kern<HintergrundAuftrag>("ki.abbrechen", { auftrag_id: auftragId });
    if (kiLaufend?.auftrag_id === auftragId) kiLaufend = { ...a, ki: true };
    hintergrundMelden();
    return;
  }
  const a = await kern<HintergrundAuftrag>("hintergrund.abbrechen", { auftrag_id: auftragId });
  if (hintergrundLaufend.has(auftragId)) hintergrundSetzen(a);
}

/** Ergebnis eines beendeten Auftrags, sonst ein Fehler mit der Meldung des Kerns bzw. „… abgebrochen.“ */
export function hintergrundErgebnis<T>(a: HintergrundAuftrag): T {
  if (a.status === "fertig") return a.ergebnis as T;
  if (a.status === "abgebrochen") throw new Error(`${a.titel}: abgebrochen.`);
  throw new Error(a.fehler ?? `${a.titel}: fehlgeschlagen.`);
}

/** Abfragepause: anfangs kurz (kleine Importe sind schnell fertig), dann höchstens eine Sekunde. */
export function hintergrundPause(runde: number): number {
  return Math.min(250 * 1.5 ** runde, 1000);
}

/**
 * Wie `kern`, aber für lange Befehle: startet sie im Hintergrund des Kerns und wartet auf das Ergebnis,
 * ohne andere Aufrufe aufzuhalten. Abbrechen über die Warteanzeige führt zu einem Fehler „… abgebrochen.“
 */
export async function kernImHintergrund<T>(methode: string, params: Record<string, unknown> = {}): Promise<T> {
  let a = await kern<HintergrundAuftrag>("hintergrund.starten", { methode, params });
  hintergrundSetzen(a);
  try {
    for (let runde = 0; a.status === "laeuft"; runde++) {
      await new Promise((weiter) => setTimeout(weiter, hintergrundPause(runde)));
      a = await kern<HintergrundAuftrag>("hintergrund.auftrag", { auftrag_id: a.auftrag_id });
      hintergrundSetzen(a);
    }
  } finally {
    if (hintergrundLaufend.delete(a.auftrag_id)) hintergrundMelden();
  }
  return hintergrundErgebnis<T>(a);
}
