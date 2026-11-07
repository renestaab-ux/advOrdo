import type { KostenEingabePosten } from "./schriftstuecke";
import { datumDe } from "./toolbox";

// --------------------------------------------------------------------------- Zeiterfassung

export interface ZeitStufe {
  id: number;
  name: string;
  /** Euro je Stunde, netto, mit Punkt. */
  satz: string;
  reihenfolge: number;
}

export interface ZeitBearbeiter {
  id: number;
  name: string;
  stufe_id: number | null;
  stufe: string;
  satz: string | null;
  person_id: number | null;
  archiviert: boolean;
}

export interface ZeitEinstellungen {
  taktung: number;
  taktungen: number[];
  /** Hinweis auf die Grenzen der Taktung (BGH IX ZR 140/19), ab 15 Minuten. */
  taktung_hinweis: string | null;
  stufen: ZeitStufe[];
  bearbeiter: ZeitBearbeiter[];
  standard_bearbeiter_id: number | null;
  neu?: number;
}

export interface ZeitEintrag {
  id: number;
  akte_id: number;
  bearbeiter_id: number | null;
  bearbeiter: string;
  stufe: string;
  satz: string | null;
  datum: string;
  /** Erfasste Minuten (bei laufendem Timer inklusive der laufenden Zeit). */
  minuten: number;
  /** Nach der Taktung abzurechnende Minuten; 0 bei nicht abrechenbaren Einträgen. */
  getaktet: number;
  betrag: string | null;
  laeuft_seit: string | null;
  taetigkeit: string;
  abrechenbar: boolean;
  kostennote_id: number | null;
  kostennote: string | null;
  angelegt_am: string;
  geaendert_am: string;
  /** Zeitspannen: jeder Timer-Lauf und von–bis von Hand; leer, wenn nur eine Dauer angegeben wurde. */
  abschnitte: { von: string; bis: string; quelle: "timer" | "hand" }[];
  /** Verknüpfte Aktennotiz, z. B. die Telefonnotiz zum Gespräch. */
  notiz_id: number | null;
  notiz: string | null;
}

export interface ZeitLaufend extends ZeitEintrag {
  akte: string;
  aktenzeichen: string | null;
  sekunden: number;
}

/** Inhalt einer Rahmen- oder Einzelvereinbarung. */
export interface VereinbarungDaten {
  taktung: number | null;
  vereinbart_am: string | null;
  mindestverguetung: boolean;
  notiz: string;
}

/**
 * Was für die Akte gilt: Einzelvereinbarung der Akte, sonst Rahmenvereinbarung mit dem (ersten) Mandanten. Die
 * flachen Felder beschreiben die geltende Vereinbarung.
 */
export interface ZeitVereinbarung {
  mandant: { schluessel: string; name: string; person: boolean; akten: number } | null;
  art: "einzel" | "rahmen" | null;
  rahmen: VereinbarungDaten | null;
  einzel: VereinbarungDaten | null;
  vermerkt: boolean;
  /** Wirksame Taktung der Akte. */
  taktung: number;
  /** Taktung aus der Vereinbarung; null: die aus den Einstellungen. */
  taktung_eigen: number | null;
  taktung_allgemein: number;
  vereinbart_am: string | null;
  mindestverguetung: boolean;
  notiz: string;
  /** Kostenschätzung dieser Akte, netto. */
  kostenschaetzung: string | null;
  hinweise: string[];
}

/** Vereinbarungen in den Daten eines Mandanten. */
export interface MandantVereinbarungen {
  mandant: string;
  rahmen: VereinbarungDaten | null;
  einzel: ({ akte_id: number; akte: string; aktenzeichen: string | null } & VereinbarungDaten)[];
  akten: number;
  taktung_allgemein: number;
  taktungen: number[];
}

export interface ZeitListe {
  eintraege: ZeitEintrag[];
  summen: { bearbeiter: string; stufe: string; minuten: number; getaktet: number; betrag: string }[];
  gesamt: {
    minuten: number;
    getaktet: number;
    betrag: string;
    offen: string;
    offen_minuten: number;
    /** Erfasster Betrag in Prozent der Kostenschätzung; null ohne Schätzung. */
    budget_anteil: number | null;
  };
  taktung: number;
  laufend: ZeitLaufend | null;
  vereinbarung: ZeitVereinbarung;
  hinweise: string[];
}

export interface ZeitFuerKostennote {
  posten: Extract<KostenEingabePosten, { typ: "stunden" }>[];
  leistungszeitraum: string;
  taktung: number;
  /** RVG-Mindestvergütung laut Vereinbarung mit dem Mandanten; null: keine Vereinbarung vermerkt. */
  mindestverguetung: boolean | null;
  hinweise: string[];
}

/** 67 → „1:07“ (Stunden:Minuten). */
export function stundenText(minuten: number): string {
  return `${Math.floor(minuten / 60)}:${String(minuten % 60).padStart(2, "0")}`;
}

/** Sekunden als „1:07:05“ für den laufenden Timer. */
export function uhrText(sekunden: number): string {
  const h = Math.floor(sekunden / 3600);
  const m = Math.floor((sekunden % 3600) / 60);
  const s = sekunden % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** Beginn des laufenden Timers („2026-10-29T12:03:00“) als „heute, 12:03 Uhr“ bzw. „28.10.2026, 17:40 Uhr“. */
export function timerSeitText(laeuftSeit: string, heute: string): string {
  const tag = laeuftSeit.slice(0, 10);
  return `${tag === heute ? "heute" : datumDe(tag)}, ${laeuftSeit.slice(11, 16)} Uhr`;
}

/** Meldet anderen Teilen der Oberfläche (Seitenleiste, Reiter „Zeiten“), dass ein Timer gestartet oder angehalten
 *  wurde. */
export const ZEIT_EREIGNIS = "jurabox-zeit";
export function zeitGeaendert(): void {
  window.dispatchEvent(new Event(ZEIT_EREIGNIS));
}
