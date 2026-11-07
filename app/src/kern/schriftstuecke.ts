import type { Beteiligung } from "./akten";

// --------------------------------------------------------------------------- Schriftstücke

/** Eine Vorlage für Schriftstücke: mitgeliefert („grund:brief“) oder eigene Word-Datei („eigen:Datei.docx“). */
export interface SchriftVorlage {
  id: string;
  titel: string;
  art: "brief" | "schriftsatz" | "vereinbarung" | "eigen";
  beschreibung?: string;
  datei?: string;
  /** Platzhalter in der Vorlage, in der Schreibweise des Katalogs. */
  platzhalter: string[];
  /** Platzhalter, die JuraBox nicht kennt (Tippfehler); sie bleiben im Schriftstück stehen. */
  unbekannt: string[];
  fehler?: string;
}

export interface SchriftVorlagen {
  grund: SchriftVorlage[];
  eigene: SchriftVorlage[];
  ordner: string;
  logo_hinweis: string | null;
}

export interface PlatzhalterEintrag {
  platzhalter: string;
  gruppe: string;
  bedeutung: string;
  wo: string;
}

export interface SchriftVorschau {
  zeilen: { platzhalter: string; wert: string | null; bekannt: boolean; wo: string }[];
  hinweise: string[];
}

export interface SchriftErgebnis {
  dateiname: string;
  leer: string[];
  unbekannt: string[];
  hinweise: string[];
  pfad?: string;
  dokument_id?: number;
  neu?: boolean;
}

/** Schriftsatz an das Gericht, Brief an den Gegnervertreter, sonst an den Gegner (wie im Kern). */
export function empfaengerVorschlag(beteiligte: Beteiligung[], art: SchriftVorlage["art"]): number | null {
  const reihenfolge =
    art === "schriftsatz" ? ["gericht"] : art === "vereinbarung" ? ["mandant"] : ["bevollmaechtigter_gegner", "gegner", "mandant"];
  for (const rolle of reihenfolge) {
    const b = beteiligte.find((x) => x.rolle === rolle);
    if (b) return b.id;
  }
  return beteiligte[0]?.id ?? null;
}

/** Ein Eintrag im Protokoll der Online-Anfragen (Einstellungen → Diagnose). */
export interface NetzEintrag {
  zeit: string;
  ziel: string;
  ort: "internet" | "geraet" | "netzwerk";
  zweck: string;
  methode: string;
  adresse: string;
  gesendet: string;
  status: number | null;
  fehler: string | null;
  dauer_ms: number;
}

export interface NetzProtokoll {
  eintraege: NetzEintrag[];
  gesamt: number;
  seit: string | null;
  hoechstens: number;
  tage: number;
}

export interface NetzEinstellungen {
  tage: number;
  hoechstens: number;
  tage_wahl: number[];
  hoechstens_wahl: number[];
  vorgabe: { tage: number; hoechstens: number };
}

/** „90 Tage“, „1 Jahr“, „2 Jahre“ für die Aufbewahrung des Protokolls. */
export function netzFrist(tage: number): string {
  if (tage % 365 === 0) return tage === 365 ? "1 Jahr" : `${tage / 365} Jahre`;
  return `${tage} Tage`;
}

export const NETZ_ORTE: Record<NetzEintrag["ort"], string> = {
  internet: "Internet",
  geraet: "Eigener Rechner",
  netzwerk: "Lokales Netzwerk",
};

/** Ergebnis einer Anfrage für Menschen: „HTTP 200“, „Fehler: …“; 2xx/3xx gelten als erfolgreich. */
export function netzErgebnis(e: NetzEintrag): { text: string; ok: boolean } {
  if (e.fehler) return { text: `Fehler: ${e.fehler}`, ok: false };
  if (e.status == null) return { text: "–", ok: false };
  return { text: `HTTP ${e.status}`, ok: e.status < 400 };
}

/** „28.10.2026, 14:03:12“ aus der ISO-Zeit des Kerns. */
export function netzZeit(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const z = (n: number) => String(n).padStart(2, "0");
  return `${z(d.getDate())}.${z(d.getMonth() + 1)}.${d.getFullYear()}, ${z(d.getHours())}:${z(d.getMinutes())}:${z(d.getSeconds())}`;
}

// --- Kostennote (Schriftstücke, Stufe 2) ---------------------------------------------------------------------

export interface KostenGebuehr {
  nr: string;
  text: string;
  satz: string;
  angelegenheit: string;
  erhoehbar: boolean;
  rahmen: [string, string] | null;
}

export interface KostennoteKatalog {
  gebuehren: KostenGebuehr[];
  auslagen: { nr: string; text: string }[];
  angelegenheiten: Record<string, string>;
  anrechnung_auf: string[];
  fassungen: Record<string, string>;
  arten: Record<string, string>;
}

/** Ein Posten der Eingabe: Wertgebühr, Auslage oder Zeitaufwand (§ 3a RVG, später aus der Zeiterfassung). */
export type KostenEingabePosten =
  | { typ: "gebuehr"; nr: string; satz: string; wert?: string }
  | { typ: "auslage"; nr: string; text: string; betrag: string; ust: boolean }
  | { typ: "stunden"; text: string; stunden: string; stundensatz: string; minuten?: number; quelle?: number[] };

export interface KostennoteEingabe {
  art: "rechnung" | "vorschuss";
  nummer: string;
  datum: string;
  auftrag: string;
  gegenstandswert: string;
  auftraggeber: number;
  leistungszeitraum: string;
  empfaenger_id: number | null;
  posten: KostenEingabePosten[];
  anrechnung: { satz: string; wert?: string; nummer?: string } | null;
  pauschale: boolean;
  umsatzsteuer: number;
  abzuege: { text?: string; nummer?: string; betrag: string }[];
  zahlungsziel: number;
  /** Zeithonorar, mindestens aber die gesetzlichen Gebühren (die Gebührenposten dienen dann dem Vergleich). */
  mindestverguetung?: boolean;
}

export interface KostennoteZeile {
  art: "gebuehr" | "anrechnung" | "pauschale" | "auslage" | "stunden";
  nr: string;
  text: string;
  wert: string | null;
  satz: string | null;
  betrag: string;
}

export interface KostennoteErgebnis {
  art: "rechnung" | "vorschuss";
  fassung: string;
  fassung_titel: string;
  grundlage: string;
  abschnitte: { titel: string; zeilen: KostennoteZeile[] }[];
  /** RVG-Mindestvergütung: beide Beträge netto und welcher berechnet ist. */
  /** RVG-Mindestvergütung; ``faktor``: Zeithonorar über dem Fünffachen der gesetzlichen Vergütung. */
  vergleich: { zeithonorar: string; gesetzlich: string; gewaehlt: "zeithonorar" | "gesetzlich"; faktor?: string } | null;
  steuerfrei: KostennoteZeile[];
  netto: string;
  umsatzsteuer_satz: string;
  umsatzsteuer: string;
  brutto: string;
  abzuege: { text: string; nummer: string; betrag: string; ust: string }[];
  zahlbetrag: string;
  hinweise: string[];
}

export interface KostennoteEintrag {
  id: number;
  nummer: string;
  art: "rechnung" | "vorschuss";
  art_text: string;
  datum: string;
  brutto: string;
  zahlbetrag: string;
  dokument_id: number | null;
  storniert: boolean;
  storniert_am: string | null;
}

export interface KostennoteVorschlag {
  nummer: string;
  muster: string;
  datum: string;
  auftrag: string;
  gegenstandswert: string;
  empfaenger_id: number | null;
  offene_vorschuesse: { nummer: string; datum: string; betrag: string }[];
  geschaeftsgebuehr: { nummer: string; satz: string; wert: string } | null;
  kostennoten: KostennoteEintrag[];
  hinweise: string[];
}

export interface KostennoteErzeugt {
  dateiname: string;
  ergebnis: KostennoteErgebnis;
  leer: string[];
  hinweise: string[];
  pfad?: string;
  dokument_id?: number;
  kostennoten?: KostennoteEintrag[];
  /** Wie viele Zeiteinträge diese Kostennote als abgerechnet gekennzeichnet hat. */
  zeiten_abgerechnet?: number;
}
