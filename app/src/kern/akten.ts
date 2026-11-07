import type { Fundstelle } from "./dokumente";
import type { Beleg } from "./gesetze";

// --- Akten ---------------------------------------------------------------------------------------

export type ZitatStatus = Beleg["status"];

export interface Akte {
  id: number;
  name: string;
  angelegt_am: string;
  dokumente: number;
  aktenzeichen: string | null;
  status: string;
  gegenstand: string | null;
  /** Gegenstandswert mit Punkt, z. B. "14555.40". */
  gegenstandswert: string | null;
  mandanten: string[];
  gegner: string[];
  gerichte: { name: string; aktenzeichen: string }[];
  sachgebiet: string | null;
  eigene_rolle: string | null;
  sachbearbeiter_id: number | null;
  sachbearbeiter: string | null;
  geaendert_am: string | null;
  /** Wann die Akte zuletzt geöffnet wurde; für „Zuletzt geöffnet“. */
  geoeffnet_am: string | null;
  /** Aktuelles Verfahren, z. B. "Klageverfahren, 1. Instanz · Landgericht Freiburg, 2 O 233/26". */
  verfahren?: string | null;
  /** Früheste offene Frist, Termin oder Wiedervorlage. */
  naechste?: Pick<KalenderEintrag, "id" | "art" | "art_text" | "titel" | "datum" | "uhrzeit" | "in_tagen" | "lage"> | null;
}

// --- Stufe 2: Verfahren, Fristen und Termine, Notizen, Akte aus Dokument --------------------------------

// Wie im Kern (verfahren.INSTANZ_VORGABE): Vorgabe der Instanz je Verfahrensart, frei änderbar.
export const INSTANZ_VORGABE: Record<string, string> = {
  klage: "1. Instanz",
  eilverfahren: "1. Instanz",
  beweisverfahren: "1. Instanz",
  berufung: "2. Instanz",
  revision: "3. Instanz",
};

export interface Verfahren {
  id: number;
  akte_id: number;
  art: string;
  art_text: string;
  instanz: string | null;
  gericht: string | null;
  spruchkoerper: string | null;
  aktenzeichen: string | null;
  status: string;
  beginn: string | null;
  ende: string | null;
  notiz: string | null;
  bezeichnung: string;
  aktuell: boolean;
}

export interface FristBerechnung {
  bezugstag: string;
  anzahl: number;
  einheit: "tage" | "wochen" | "monate" | "jahre";
  beginn: string;
  land: string;
  ende: string;
  wochentag: string;
  verschoben: boolean;
  grund: string;
  grundlagen: string[];
  hinweise: string[];
}

export type KalenderArt = "frist" | "termin" | "wiedervorlage";
export type KalenderLage =
  | "erledigt"
  | "stattgefunden"
  | "aufgehoben"
  | "verlegt"
  | "abgelaufen"
  | "heute"
  | "vorfrist"
  | "bald"
  | "offen";

/** Abschluss eines Termins; „geplant“ setzt ihn zurück. */
export type TerminZustand = "geplant" | "aufgehoben" | "verlegt";

/** Ein Schritt im Verlauf einer Frist bzw. Wiedervorlage (Verlängerung, Verkürzung, Verschiebung). */
export interface KalenderVerlauf {
  am: string;
  was: "verlängert" | "verkürzt" | "verschoben";
  alt: string;
  neu: string;
  alt_vorfristen: string[];
  alt_berechnung: FristBerechnung | null;
  vermerk: string | null;
  dokument_id: number | null;
  fundstelle: (Fundstelle & { text?: string }) | null;
}

export interface KalenderEintrag {
  id: number;
  akte_id: number;
  verfahren_id: number | null;
  art: KalenderArt;
  art_text: string;
  titel: string;
  datum: string;
  uhrzeit: string | null;
  /** Ende eines Termins, optional. */
  bis_uhrzeit: string | null;
  ort: string | null;
  /** Erste (frühere) und zweite Vorfrist einer Frist. */
  vorfrist: string | null;
  vorfrist2: string | null;
  vorfrist_erreicht: 1 | 2 | null;
  berechnung: FristBerechnung | null;
  dokument_id: number | null;
  dokument: string | null;
  fundstelle: Fundstelle | null;
  notiz: string | null;
  /** Abgeschlossen am (erledigt, aufgehoben oder verlegt), mit Vermerk. */
  erledigt_am: string | null;
  erledigt_vermerk: string | null;
  zustand: "erledigt" | "stattgefunden" | "aufgehoben" | "verlegt" | null;
  verlauf: KalenderVerlauf[];
  verlegt_von: number | null;
  verlegt_von_termin: { id: number; datum: string; uhrzeit: string | null } | null;
  verlegt_auf: { id: number; datum: string; uhrzeit: string | null } | null;
  /** Erledigt, aufgehoben, verlegt oder ein Termin, dessen Tag vorbei ist. */
  abgeschlossen: boolean;
  in_tagen: number;
  lage: KalenderLage;
  /** Nur in „Nächste Fristen“ und im Kalender über alle Akten. */
  akte?: string;
  aktenzeichen?: string | null;
  /** Nur im Kalender: Status der Akte und Gericht des Verfahrens. */
  akte_status?: string;
  gericht?: string | null;
  gericht_aktenzeichen?: string | null;
}

/**
 * Vorschlag aus einem Dokument; "zustand" schlägt vor, einen eingetragenen Termin aufzuheben oder (mit ``neu``) zu
 * verlegen.
 */
export interface KalenderVorschlag {
  art: KalenderArt | "zustand";
  zustand?: "aufgehoben" | "verlegt";
  neu?: { titel: string; datum: string; uhrzeit: string; ort: string; fundstelle: Fundstelle & { text: string } };
  titel: string;
  datum: string | null;
  uhrzeit?: string;
  ort?: string;
  vorfrist?: string;
  berechnung?: FristBerechnung;
  dauer?: { anzahl: number; einheit: FristBerechnung["einheit"]; bezug: string };
  hinweis?: string;
  eintrag_id?: number;
  vermerk?: string;
  fundstelle: Fundstelle & { text: string };
  bezug_fundstelle?: Fundstelle & { text: string };
  dokument_id: number;
  dateiname: string;
}

export interface Notiz {
  id: number;
  akte_id: number;
  dokument_id: number | null;
  dokument: string | null;
  text: string;
  angeheftet: boolean;
  angelegt_am: string;
  geaendert_am: string;
  /** Zeiteintrag, zu dem die Notiz gehört („2026-10-29 · Bearbeiter“), sonst null. */
  zeiteintrag: string | null;
}

export interface RubrumFeld {
  wert: string;
  fundstelle: Fundstelle;
  /** Beim Mahnbescheid steht statt des Streitwerts die Hauptforderung. */
  art?: string;
}

export interface RubrumPartei {
  index: number;
  art: "person" | "organisation";
  name: string;
  daten: Record<string, string>;
  vertreter: { funktion: string; name: string; daten: Record<string, string> }[];
  hinweise: string[];
  seite: "aktiv" | "passiv";
  rolle: string;
  zusatz: string;
  fundstelle: Fundstelle;
  treffer: { id: number; name: string; stufe: "gleich" | "aehnlich" }[];
  eigene_organisation_id: number | null;
  /** Nur bei „Verfahren aus Dokument“: Rolle, in der die Partei schon in der Akte steht. */
  in_akte?: RubrumInAkte | null;
  bevollmaechtigte: {
    name: string;
    daten: Record<string, string>;
    zeichen: string;
    treffer: { id: number; name: string; stufe: "gleich" | "aehnlich" }[];
    eigene: boolean;
    in_akte?: RubrumInAkte | null;
  } | null;
}

export interface RubrumInAkte {
  rolle: string;
  rolle_text: string;
  name: string;
}

export interface RubrumVorschau {
  dateiname: string;
  lesart: string;
  dokumentart: RubrumFeld | null;
  gericht: (RubrumFeld & { name: string; spruchkoerper: string; anschrift?: { strasse: string; plz: string; ort: string } }) | null;
  aktenzeichen: RubrumFeld | null;
  zeichen_absender: RubrumFeld | null;
  gegenstand: RubrumFeld | null;
  streitwert: RubrumFeld | null;
  parteien: RubrumPartei[];
  verfahren_art: string;
  kurzbezeichnung: string;
  eigene_seite: { wert: "aktiv" | "passiv"; grund: string } | null;
  aktenzeichen_vorschlag: string;
  hinweise: string[];
  abschnitte: Record<string, string>;
  /** Nur bei „Verfahren aus Dokument“: gleiches gerichtliches Aktenzeichen schon in der Akte. */
  verfahren_vorhanden?: { id: number; bezeichnung: string } | null;
  /** Nur bei „Verfahren aus Dokument“: laufende Verfahren der Akte, die sich dabei abschließen lassen. */
  laufende_verfahren?: { id: number; bezeichnung: string; art: string }[];
}

/** "2026-09-29" → "Di, 29.09.2026". */
export function datumLang(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [j, m, t] = iso.slice(0, 10).split("-").map(Number);
  const d = new Date(j, m - 1, t);
  if (Number.isNaN(d.getTime())) return iso;
  const tag = d.toLocaleDateString("de-DE", { weekday: "short" }).replace(".", "");
  return `${tag}, ${String(t).padStart(2, "0")}.${String(m).padStart(2, "0")}.${j}`;
}

/** Wie weit ein Eintrag entfernt ist: "heute", "morgen", "in 4 Tagen", "seit 2 Tagen abgelaufen". */
export function abstandText(
  e: Pick<KalenderEintrag, "in_tagen" | "art" | "erledigt_am"> & { zustand?: KalenderEintrag["zustand"] },
): string {
  if (e.erledigt_am) return e.zustand ?? "erledigt";
  const n = e.in_tagen;
  if (n === 0) return "heute";
  if (n === 1) return "morgen";
  if (n > 1) return `in ${n} Tagen`;
  if (e.art === "termin") return "stattgefunden";
  return n === -1 ? "seit gestern abgelaufen" : `seit ${-n} Tagen abgelaufen`;
}

/** Eine Erinnerung des Systems an eine Frist, einen Termin oder eine Wiedervorlage. */
export interface Erinnerung {
  /** Eintrag, Stufe und Datum: ändert sich das Datum, wird erneut erinnert. */
  schluessel: string;
  akte_id: number;
  titel: string;
  text: string;
}

/**
 * Welche Erinnerungen jetzt fällig und noch nicht gezeigt sind. Fristen: bei erreichter Vorfrist, am Vortag, am
 * Tag des Ablaufs und einmal, wenn sie abgelaufen sind. Termine: am Vortag und am Tag. Wiedervorlagen: am Tag
 * (auch nachträglich).
 */
export function faelligeErinnerungen(eintraege: KalenderEintrag[], gezeigt: ReadonlySet<string>): Erinnerung[] {
  const ergebnis: Erinnerung[] = [];
  for (const e of eintraege) {
    if (e.erledigt_am) continue;
    const n = e.in_tagen;
    let stufe: string | null = null;
    let titel = "";
    if (e.art === "frist") {
      if (n < 0) [stufe, titel] = ["abgelaufen", `Frist abgelaufen: ${e.titel}`];
      else if (n === 0) [stufe, titel] = ["heute", `Frist läuft heute ab: ${e.titel}`];
      else if (n === 1) [stufe, titel] = ["morgen", `Frist läuft morgen ab: ${e.titel}`];
      else if (e.lage === "vorfrist")
        [stufe, titel] = [
          e.vorfrist_erreicht === 2 ? "vorfrist2" : "vorfrist",
          `${e.vorfrist_erreicht === 2 ? "Zweite Vorfrist" : "Vorfrist"} erreicht: ${e.titel}`,
        ];
    } else if (e.art === "termin") {
      const zeit = e.uhrzeit ? `, ${e.uhrzeit} Uhr` : "";
      if (n === 0) [stufe, titel] = ["heute", `Termin heute${zeit}: ${e.titel}`];
      else if (n === 1) [stufe, titel] = ["morgen", `Termin morgen${zeit}: ${e.titel}`];
    } else if (n <= 0) {
      [stufe, titel] = ["faellig", `Wiedervorlage: ${e.titel}`];
    }
    if (!stufe) continue;
    const schluessel = `${e.id}:${stufe}:${e.datum}`;
    if (gezeigt.has(schluessel)) continue;
    const akte = [e.aktenzeichen, e.akte].filter(Boolean).join(" ");
    ergebnis.push({
      schluessel,
      akte_id: e.akte_id,
      titel,
      text: [akte, `${e.art_text} ${datumLang(e.datum)}`, e.art === "termin" ? e.ort : null].filter(Boolean).join(" · "),
    });
  }
  return ergebnis;
}

/** Das Land für die Feiertage (§ 193 BGB) wie im Fristenrechner der Toolbox. */
export function fristenLand(): string {
  try {
    return localStorage.getItem("toolbox.land") ?? "BY";
  } catch {
    return "BY";
  }
}

/** Anzeige einer Akte in Auswahllisten: „12/26 · Brückner ./. Autohaus“; ohne Aktenzeichen nur der Name. */
export function akteTitel(a: Pick<Akte, "name" | "aktenzeichen">): string {
  return a.aktenzeichen ? `${a.aktenzeichen} · ${a.name}` : a.name;
}

function einfach(text: string): string {
  return text.toLocaleLowerCase("de").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

/**
 * Ob eine Akte zu einer Sucheingabe passt: jedes Wort muss in Aktenzeichen, Kurzbezeichnung, Parteien, Gegenstand,
 * Gericht oder gerichtlichem Aktenzeichen vorkommen. Groß- und Kleinschreibung und Akzente spielen keine Rolle.
 */
export function aktePasst(
  a: Pick<Akte, "aktenzeichen" | "name" | "gegenstand" | "mandanten" | "gegner" | "gerichte">,
  suche: string,
): boolean {
  const begriffe = einfach(suche).split(/\s+/).filter(Boolean);
  if (begriffe.length === 0) return true;
  const text = einfach(
    [a.aktenzeichen, a.name, a.gegenstand, ...a.mandanten, ...a.gegner, ...a.gerichte.flatMap((g) => [g.name, g.aktenzeichen])]
      .filter(Boolean)
      .join(" "),
  );
  return begriffe.every((b) => text.includes(b));
}

/**
 * Ob ein Eintrag einer Auswahlliste zur Eingabe passt: jedes Wort muss im Eintrag vorkommen, egal wo. „münchen“ findet so
 * „Rechtsanwaltskammer für den Oberlandesgerichtsbezirk München“. Umlaute dürfen auch umschrieben sein („muenchen“).
 */
export function optionPasst(option: string, suche: string): boolean {
  const umschreiben = (t: string) =>
    t.toLocaleLowerCase("de").replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss");
  const begriffe = umschreiben(suche).split(/\s+/).filter(Boolean);
  const text = umschreiben(option);
  return begriffe.every((b) => text.includes(b));
}

/** Die zuletzt geöffneten Akten, neueste zuerst; Akten, die noch nie geöffnet wurden, fehlen. */
export function zuletztGeoeffnet(akten: Akte[], anzahl: number): Akte[] {
  return akten
    .filter((a) => a.geoeffnet_am)
    .sort((a, b) => (b.geoeffnet_am ?? "").localeCompare(a.geoeffnet_am ?? ""))
    .slice(0, anzahl);
}

/** Zuletzt bearbeitet als „heute“, „gestern“ oder Datum. */
export function bearbeitetText(iso: string | null | undefined, jetzt = new Date()): string {
  if (!iso) return "–";
  const tag = iso.slice(0, 10);
  // Der Kern speichert Ortszeit ohne Zone; daher mit dem örtlichen Datum vergleichen.
  const tagVon = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const heute = tagVon(jetzt);
  const gestern = tagVon(new Date(jetzt.getFullYear(), jetzt.getMonth(), jetzt.getDate() - 1));
  if (tag === heute) return "heute";
  if (tag === gestern) return "gestern";
  const [j, m, t] = tag.split("-");
  return j === heute.slice(0, 4) ? `${t}.${m}.` : `${t}.${m}.${j}`;
}

/** Eine Person oder Organisation aus dem Beteiligtenverzeichnis. */
export interface Beteiligter {
  id: number;
  art: "person" | "organisation";
  name: string;
  daten: Record<string, string | string[]>;
  geaendert_am: string;
  stufe?: "gleich" | "aehnlich";
  /** Nur in der Liste: als wer der Eintrag vorkommt, z. B. "Mandant", "Gegner · 2 Akten", "Geschäftsführerin von …". */
  /** Bei Funktionen (Geschäftsführer …) die Seite der vertretenen Organisation, wenn sie eindeutig ist. */
  rollen?: { text: string; gruppe: "eigene" | "gegen" | "gericht" | "neutral" | "funktion"; seite?: "eigene" | "gegen" | null }[];
  /** Nur in der Liste: an wie vielen Akten beteiligt. */
  akten_anzahl?: number;
  beziehungen?: { von: number; zu: number; art: string; anderer: number; name: string; funktion?: string; text: string }[];
  akten?: { akte_id: number; rolle: string; akte: string; aktenzeichen: string | null }[];
}

/** Ein Beteiligter in einer Akte, mit Rolle und Seite. */
export interface Beteiligung {
  id: number;
  rolle: string;
  rolle_text: string;
  seite: "eigene" | "gegen" | "neutral";
  /** Gruppe in der Liste: wie die Seite, nur steht das Gericht für sich. */
  gruppe: "eigene" | "gegen" | "gericht" | "neutral";
  name: string;
  quelle: "verzeichnis" | "eigene_organisation" | "eigene_person";
  beteiligter_id: number | null;
  art: "person" | "organisation" | null;
  aktenzeichen: string;
}

export interface KollisionsTreffer {
  ampel: "rot" | "gelb";
  stufe: string;
  text: string;
  dort: { akte_id: number | null; aktenzeichen: string | null; akte: string; umgebung: string; andere_umgebung: boolean };
}

export interface Kollisionspruefung {
  id: number;
  zeitpunkt: string;
  ampel: "gruen" | "gelb" | "rot";
  treffer: KollisionsTreffer[];
  umgebungen: string[];
  entscheidung: string | null;
  entscheidung_text: string | null;
  begruendung: string | null;
  entschieden_am: string | null;
}

export interface AkteStammdaten {
  id: number;
  name: string;
  aktenzeichen: string | null;
  gegenstand: string | null;
  sachgebiet: string | null;
  eigene_rolle: string | null;
  status: string;
  sachbearbeiter_id: number | null;
  mandat_seit: string | null;
  gegenstandswert: string | null;
  notiz: string | null;
  dokumente: number;
  beteiligte: Beteiligung[];
  kollision: Kollisionspruefung | null;
}

export interface AktenOptionen {
  rollen: Record<string, { seite: "eigene" | "gegen" | "neutral"; text: string }>;
  seiten: Record<string, string>;
  gruppen: Record<string, string>;
  status: Record<string, string>;
  eigene_rollen: string[];
  sachgebiete: string[];
  kategorien: string[];
  beziehungen: Record<string, string>;
  funktionen: string[];
  entscheidungen: Record<string, string>;
  verfahren_arten: Record<string, string>;
  instanzen: string[];
  kalender_arten: Record<KalenderArt, string>;
  form: string | null;
  sachbearbeiter: { id: number; name: string }[];
  konzerngesellschaften: { id: number; name: string }[];
  anwaelte: { id: number; name: string; kanzlei: string }[];
}

/** Möglicher Konflikt eines Suchtreffers, bevor er eingetragen ist; je Beteiligten-ID. */
export type KollisionVorab = Record<string, { ampel: "rot" | "gelb"; texte: string[] }>;

/** Gegenstandswert aus dem Kern ("250000.00") in deutscher Schreibweise ("250.000,00"); Freitext bleibt. */
export function betragAnzeige(wert: string | null | undefined): string {
  if (!wert) return "";
  if (!/^\d+(\.\d{1,2})?$/.test(wert)) return wert;
  return Number(wert).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Eingabe wie "250.000" oder "18450,5 €" in die Anzeige "250.000,00"; was kein Betrag ist, bleibt stehen. */
export function betragNormalisieren(text: string): string {
  let z = text.replace(/[\s€']|EUR/gi, "");
  if (!z) return "";
  if (z.includes(",")) z = z.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(\.\d{3})+$/.test(z)) z = z.replace(/\./g, "");
  return /^\d+(\.\d+)?$/.test(z) ? betragAnzeige(Number(z).toFixed(2)) : text;
}

export interface AktenEinstellungen {
  aktenzeichen_zusatz: string;
  naechste_nummer: Record<string, number>;
  kollision_ausgenommen: string[];
}

export const AMPEL_TEXT: Record<string, string> = {
  gruen: "Keine Treffer",
  gelb: "Ähnliche Namen oder verbundene Beteiligte",
  rot: "Partei steht anderswo auf der Gegenseite",
};
