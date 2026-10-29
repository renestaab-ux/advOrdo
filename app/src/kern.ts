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
  return /^\s*(§§?|Art\.|Artikel)\s*\d+[a-z]?\b.*\s(?:[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]*[A-ZÄÖÜ]|Rom[ -]?I{1,2}(?:[ -]?VO)?)\s*$/.test(eingabe);
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
  aktenzeichen: string | null;
  status: string;
  gegenstand: string | null;
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

/** Fundstelle in einem Dokument: Abschnitt, Seite und der Satz, aus dem ein Vorschlag stammt. */
export interface Fundstelle {
  abschnitt: number;
  seite: number | null;
  text?: string;
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
export type KalenderLage = "erledigt" | "abgelaufen" | "heute" | "vorfrist" | "bald" | "offen";

export interface KalenderEintrag {
  id: number;
  akte_id: number;
  verfahren_id: number | null;
  art: KalenderArt;
  art_text: string;
  titel: string;
  datum: string;
  uhrzeit: string | null;
  ort: string | null;
  vorfrist: string | null;
  berechnung: FristBerechnung | null;
  dokument_id: number | null;
  dokument: string | null;
  fundstelle: Fundstelle | null;
  notiz: string | null;
  erledigt_am: string | null;
  erledigt_vermerk: string | null;
  in_tagen: number;
  lage: KalenderLage;
  /** Nur in „Nächste Fristen“ über alle Akten. */
  akte?: string;
  aktenzeichen?: string | null;
}

/** Vorschlag aus einem Dokument; "erledigen" schlägt vor, einen eingetragenen Termin als aufgehoben abzuhaken. */
export interface KalenderVorschlag {
  art: KalenderArt | "erledigen";
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
export function abstandText(e: Pick<KalenderEintrag, "in_tagen" | "art" | "erledigt_am">): string {
  if (e.erledigt_am) return "erledigt";
  const n = e.in_tagen;
  if (n === 0) return "heute";
  if (n === 1) return "morgen";
  if (n > 1) return `in ${n} Tagen`;
  const wort = e.art === "termin" ? "vorbei" : "abgelaufen";
  return n === -1 ? `seit gestern ${wort}` : `seit ${-n} Tagen ${wort}`;
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
      else if (e.lage === "vorfrist") [stufe, titel] = ["vorfrist", `Vorfrist erreicht: ${e.titel}`];
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
  /** Datum des Dokuments als JJJJ-MM-TT; null, wenn keins zu ermitteln war. */
  datum: string | null;
  /** dokument: Datumszeile im Text, word: letztes Speichern laut Word, datei: Änderungsdatum der Datei. */
  datum_quelle: DatumQuelle | null;
  /** Fundstelle der Datumszeile. */
  datum_abschnitt: number | null;
  datum_seite: number | null;
  datum_text: string | null;
  /** Letztes Speichern als ISO-Zeitpunkt (Word-Eigenschaften oder Dateidatum beim Einlesen). */
  gespeichert_am: string | null;
  gespeichert_quelle: "word" | "datei" | null;
  /** Aktuelle Fassung: 1 ist die eingelesene Datei, jede übernommene Bearbeitung zählt hoch. */
  fassung: { nr: number; erstellt_am: string; quelle: "import" | "bearbeitet" };
  /** Ob es eine Arbeitskopie zum Bearbeiten in einem externen Programm gibt. */
  arbeitskopie: boolean;
  /** Titel von Hand (Ansicht „Details“); null = es gilt der Dateiname. */
  titel: string | null;
  /** Art des Dokuments: Schreiben, Schriftsatz, Verfügung, Urteil … (Ansicht „Details“). */
  art: string | null;
  /** Wer das Dokument erstellt hat (Ansicht „Details“); fehlt bei älteren Abrufen. */
  absender?: MetaAbsender | null;
}

/** Anzeigename eines Dokuments: der Titel, sonst der Dateiname. */
export function dokumentName(d: Pick<AktenDokument, "titel" | "dateiname">): string {
  return d.titel?.trim() || d.dateiname;
}

/** Fundstelle eines Vorschlags in der Ansicht „Details“. */
export interface MetaFundstelle {
  abschnitt: number;
  seite: number | null;
  text: string | null;
}

/** Aus dem Text erkannter Wert; eingetragen wird er erst nach Bestätigung. */
export interface MetaVorschlag {
  wert: string;
  grund: string;
  fundstelle: MetaFundstelle | null;
}

/**
 * Absender eines Dokuments: "eigene" (wir selbst), die Nummer einer Beteiligung der Akte oder "frei:<Name>" für
 * jemanden außerhalb der Akte (z. B. das Mahngericht).
 */
export interface MetaAbsender {
  wert: "eigene" | number | `frei:${string}`;
  name: string;
  rolle_text: string;
}

export interface MetaAbsenderVorschlag extends MetaAbsender {
  grund: string;
  fundstelle: MetaFundstelle | null;
}

export interface MetaBeteiligterVorschlag {
  beteiligung_id: number;
  name: string;
  rolle_text: string;
  grund: string;
  fundstelle: MetaFundstelle | null;
}

export type MetaVerlaufEintrag =
  | { art: "fassung"; zeitpunkt: string; nr: number; dateiname: string; quelle: "import" | "bearbeitet" }
  | { art: "aenderung"; zeitpunkt: string; id: number; feld: string; feld_text: string; alt: string | null; neu: string | null };

/** Metadaten eines Dokuments (Kern: akten.metadaten). */
export interface DokumentMetadaten {
  dokument_id: number;
  dateiname: string;
  titel: string;
  art: string;
  /** Auswahlliste für die Art; eigene Angaben sind ebenfalls möglich. */
  arten: string[];
  absender: MetaAbsender | null;
  datum: {
    wert: string | null;
    quelle: DatumQuelle | null;
    seite: number | null;
    abschnitt: number | null;
    text: string | null;
    /** Nur bei einem Datum von Hand: das erkannte Datum. */
    erkannt: { datum: string | null; quelle: DatumQuelle } | null;
  };
  schlagworte: Tag[];
  beteiligte: Beteiligung[];
  akte_beteiligte: Beteiligung[];
  vorschlaege: {
    titel: MetaVorschlag[];
    art: MetaVorschlag | null;
    absender: MetaAbsenderVorschlag | null;
    datum: MetaVorschlag | null;
    schlagworte: MetaVorschlag[];
    beteiligte: MetaBeteiligterVorschlag[];
  };
  benennung: MetaBenennung;
  verlauf: MetaVerlaufEintrag[];
}

/**
 * Bausteine für den Titel nach dem Schema „Wer schreibt was an wen“. Schlüssel: Beteiligungs-ID als Text, "eigene",
 * "gericht_an" (Gericht in der Anschrift, nicht in der Akte) oder "gericht_kopf" (Gericht im Kopf des Dokuments).
 */
export interface MetaBenennung {
  kurznamen: Record<string, string>;
  /** Im Kopf des Dokuments genannt, in der Reihenfolge des Auftretens. */
  empfaenger: string[];
  vertragsparteien: string[];
  was: { schreiben: string | null; schriftsatz: string | null; vertrag: string | null };
}

/** Vorschläge des Sprachmodells (Kern: akten.metadaten_ki); jede Angabe ist mit einem Zitat im Dokument belegt. */
export interface MetaKiErgebnis {
  art: MetaVorschlag | null;
  /** wert null: nicht in der Akte; dann zählt nur der Name (schluessel) für den Titel. */
  absender: MetaAbsenderVorschlag | null;
  benennung: {
    kurznamen: Record<string, string>;
    empfaenger: string[];
    vertragsparteien: string[];
    was: Partial<MetaBenennung["was"]>;
  };
  /** Angaben, deren Zitat im Dokument nicht steht und die deshalb verworfen wurden. */
  verworfen: number;
  modell: string;
  gespeichert?: boolean;
}

export type MetaKiStand =
  | { status: "aus"; abgeschaltet?: boolean }
  | { status: "belegt"; aufgabe?: string | null }
  | { status: "extern" }
  | { status: "laeuft"; auftrag: KiAuftrag }
  | { status: "fertig"; ergebnis: MetaKiErgebnis }
  | { status: "fehler"; fehler: string };

/** Benennung der Texterkennung, ergänzt um das, was die KI belegt erkannt hat (die KI geht vor). */
export function mitKi(b: MetaBenennung, ki: MetaKiErgebnis | null | undefined): MetaBenennung {
  if (!ki) return b;
  const k = ki.benennung;
  return {
    kurznamen: { ...b.kurznamen, ...k.kurznamen },
    empfaenger: k.empfaenger.length ? [...k.empfaenger, ...b.empfaenger.filter((e) => !k.empfaenger.includes(e))] : b.empfaenger,
    vertragsparteien: k.vertragsparteien.length >= 2 ? k.vertragsparteien : b.vertragsparteien,
    was: { ...b.was, ...k.was },
  };
}

export const FREI = "frei:";

const GERICHT_KURZ: [string, string][] = [
  ["Bundesgerichtshof", "BGH"],
  ["Oberlandesgericht", "OLG"],
  ["Landesarbeitsgericht", "LAG"],
  ["Landessozialgericht", "LSG"],
  ["Oberverwaltungsgericht", "OVG"],
  ["Verwaltungsgerichtshof", "VGH"],
  ["Bundesarbeitsgericht", "BAG"],
  ["Landgericht", "LG"],
  ["Amtsgericht", "AG"],
  ["Arbeitsgericht", "ArbG"],
  ["Sozialgericht", "SG"],
  ["Verwaltungsgericht", "VG"],
  ["Finanzgericht", "FG"],
];

/** „Amtsgericht Stuttgart“ → „AG Stuttgart“ (wie im Kern); andere Namen bleiben, wie sie sind. */
export function gerichtKurz(name: string): string {
  const n = name.trim().replace(/\s+/g, " ");
  const treffer = GERICHT_KURZ.find(([lang]) => n.startsWith(lang));
  return treffer ? treffer[1] + n.slice(treffer[0].length) : n;
}

/** Arten, bei denen das Gericht „schreibt“: der Titel ist nur „LG Freiburg Urteil“. */
const GERICHTSARTEN = ["urteil", "beschluss", "verfügung", "ladung", "protokoll", "mahnbescheid", "vollstreckungsbescheid"];

/**
 * Titel nach dem Schema „Wer schreibt was an wen“ aus Art und Absender (wie gerade eingegeben):
 * Schreiben „RA Müller Zahlungsaufforderung an Schneider“, Schriftsatz „RA Müller Klageschrift gegen Schneider“,
 * Urteil/Beschluss „LG Freiburg Urteil“, Vertrag „Kaufvertrag zwischen Müller und Schneider“.
 * Fehlende Teile fallen weg; null, wenn nichts Brauchbares bleibt.
 */
export function titelNachSchema(
  b: MetaBenennung,
  art: string,
  absender: string,
  akteBeteiligte: Beteiligung[],
): string | null {
  const kurz = (schluessel: string | undefined) =>
    !schluessel ? "" : (b.kurznamen[schluessel] ?? (schluessel.startsWith(FREI) ? gerichtKurz(schluessel.slice(FREI.length)) : ""));
  const ersteMit = (rolle: string) => akteBeteiligte.find((x) => x.rolle === rolle);
  const art_ = art.trim();
  const klein = art_.toLocaleLowerCase("de");
  const satz = (...teile: string[]) => teile.filter((t) => t.trim()).join(" ") || null;

  if (klein.includes("vertrag") || klein.includes("vereinbarung")) {
    const ausgeschlossen = new Set(akteBeteiligte.filter((x) => x.rolle === "gericht").map((x) => String(x.id)));
    let parteien = b.vertragsparteien.filter((s) => s !== "eigene" && !ausgeschlossen.has(s));
    if (parteien.length < 2)
      parteien = [ersteMit("mandant"), ersteMit("gegner")].filter((x) => x).map((x) => String(x!.id));
    const namen = parteien.slice(0, 2).map(kurz).filter((n) => n);
    const was = b.was.vertrag ?? art_;
    if (namen.length === 2) return `${was} zwischen ${namen[0]} und ${namen[1]}`;
    return namen.length === 1 ? `${was} mit ${namen[0]}` : null;
  }

  const wer = kurz(absender);
  // Ohne Absender: das im Kopf erkannte Gericht, auch wenn es nicht zur Akte gehört (Mahngericht).
  if (GERICHTSARTEN.includes(klein)) {
    const gericht = wer || kurz("gericht_kopf");
    return gericht ? satz(gericht, art_) : null;
  }

  if (klein === "schriftsatz") {
    const seite =
      absender === "eigene" ? "eigene" : akteBeteiligte.find((x) => String(x.id) === absender)?.seite;
    const gegen =
      seite === "eigene"
        ? (ersteMit("gegner") ?? akteBeteiligte.find((x) => x.seite === "gegen"))
        : seite === "gegen"
          ? ersteMit("mandant")
          : undefined;
    const g = gegen ? kurz(String(gegen.id)) : "";
    // Ein Gericht außerhalb der Akte (z. B. das Mahngericht) wird als Empfänger genannt.
    const an = kurz(b.empfaenger.find((e) => e === "gericht_an" || (e.startsWith(FREI) && /gericht/i.test(e))));
    return wer || g ? satz(wer, b.was.schriftsatz ?? "Schriftsatz", g ? `gegen ${g}` : "", an ? `an ${an}` : "") : null;
  }

  // Schreiben, E-Mail und alles Übrige. Ohne bekannten Absender steht vorn meist der Briefkopf: dann den zweiten.
  const kandidaten = b.empfaenger.filter((s) => s !== absender);
  const an = kurz(absender ? kandidaten[0] : kandidaten[1]);
  return wer || an ? satz(wer, b.was.schreiben ?? (art_ || "Schreiben"), an ? `an ${an}` : "") : null;
}

/** Eine Fassung eines Dokuments; die Dateien aller Fassungen bleiben unverändert abgelegt. */
export interface DokumentFassung {
  nr: number;
  dateiname: string;
  groesse: number;
  erstellt_am: string;
  quelle: "import" | "bearbeitet";
  aktuell: boolean;
}

/** Arbeitskopie eines Dokuments; „geaendert“ heißt: im externen Programm gespeichert, noch nicht übernommen. */
export interface Arbeitskopie {
  dokument_id: number;
  dateiname: string;
  pfad: string;
  basis_nr: number;
  angelegt_am: string;
  geaendert_am: string | null;
  status: "unveraendert" | "geaendert" | "gesperrt" | "fehlt";
}

export type ProgrammArt = "pdf" | "text";

/** Externes Programm je Art; leeres ``programm`` heißt Standardprogramm des Systems. */
export interface ProgrammEinstellung {
  titel: string;
  programm: string;
  parameter: string;
}

export function programmArt(format: AktenDokument["format"]): ProgrammArt {
  return format === "pdf" ? "pdf" : "text";
}

/** Kurzer Name eines Programms aus seinem Pfad, z. B. „soffice“ oder „LibreOffice“. */
export function programmName(pfad: string): string {
  const name = pfad.replace(/[\\/]+$/, "").split(/[\\/]/).pop() ?? "";
  return name.replace(/\.(exe|app|cmd|bat)$/i, "") || "Standardprogramm";
}

/** Geänderte Arbeitskopien, nach denen noch gefragt werden soll; „später“ gilt bis zur nächsten Änderung. */
export function offeneUebernahmen(kopien: Arbeitskopie[], spaeter: ReadonlySet<string>): Arbeitskopie[] {
  return kopien.filter((k) => k.status === "geaendert" && !spaeter.has(kopieSchluessel(k)));
}

export function kopieSchluessel(k: Arbeitskopie): string {
  return `${k.dokument_id}|${k.geaendert_am ?? ""}`;
}

export type DatumQuelle = "dokument" | "word" | "datei" | "manuell" | "unbekannt";

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

/** Eine Seite des Original-PDFs, vom Kern als PNG gerendert. */
export interface Seitenbild {
  seite: number;
  seiten: number;
  breite: number;
  hoehe: number;
  bild: string;
  /** Fundstellen gesuchter Begriffe als Anteile der Seitengröße (0 bis 1). */
  markierungen: { x: number; y: number; b: number; h: number }[];
}

/** Eine Fundstelle der Volltextsuche: eine Seite, bei Dokumenten ohne Seiten ein Abschnitt. */
export interface SuchFundstelle {
  seite: number | null;
  abschnitt: number;
  rn: number | null;
  treffer: number;
  rang: number;
  begriffe: string[];
  ausschnitt: { vor: string; treffer: string; nach: string };
}

export interface SuchDokument {
  id: number;
  dateiname: string;
  format: AktenDokument["format"];
  seiten: number | null;
  akte_id: number;
  akte: string;
  treffer: number;
  rang: number;
  fundstellen: SuchFundstelle[];
}

export interface SuchErgebnis {
  dokumente: SuchDokument[];
  seiten: number;
  treffer: number;
  dauer_ms: number;
  gekuerzt: boolean;
}

/** Teilt Text in Stücke und markiert darin die gesuchten Begriffe (ohne Rücksicht auf Groß- und Kleinschreibung). */
export function markiereBegriffe(text: string, begriffe: string[]): { text: string; treffer: boolean }[] {
  const muster = [...new Set(begriffe.filter((b) => b.trim()))]
    .sort((a, b) => b.length - a.length)
    .map((b) => b.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (muster.length === 0) return [{ text, treffer: false }];
  // split mit Klammergruppe liefert abwechselnd Text und Treffer.
  return text
    .split(new RegExp(`(${muster.join("|")})`, "giu"))
    .map((s, i) => ({ text: s, treffer: i % 2 === 1 }))
    .filter((s) => s.text !== "");
}

/** Breite in Pixeln, in der der Kern Seiten rendert: auf 200 gerundet, damit gleiche Fenstergrößen gleiche Bilder liefern. */
export function renderBreite(anzeigeBreite: number, pixelVerhaeltnis: number): number {
  return Math.min(2400, Math.max(400, Math.ceil((anzeigeBreite * pixelVerhaeltnis) / 200) * 200));
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

export type UrteilStatus = "abweichend" | "nicht_gefunden" | "kein_verzeichnis" | "belegt" | "ausserhalb" | "nicht_pruefbar";

export const URTEIL_STATUS_TEXT: Record<UrteilStatus, string> = {
  abweichend: "Angaben weichen ab",
  nicht_gefunden: "nicht auffindbar",
  kein_verzeichnis: "noch nicht geprüft",
  belegt: "belegt",
  ausserhalb: "nicht im Verzeichnis",
  nicht_pruefbar: "nicht prüfbar",
};

/** Eine in der Akte zitierte Entscheidung mit Prüfergebnis gegen das Verzeichnis der Bundesgerichte. */
export interface UrteilEintrag {
  zitat: string;
  gericht: string;
  aktenzeichen: string | null;
  datum: string | null;
  status: UrteilStatus;
  hinweis: string | null;
  entscheidung: {
    gericht: string;
    spruchkoerper: string | null;
    datum: string | null;
    aktenzeichen: string;
    link: string | null;
    /** Quelle, die das Zitat belegt hat; fehlt bei rechtsprechung-im-internet.de. */
    quelle?: OnlineQuelle;
  } | null;
  fundstellen: (Fundstelle & { rn_zitiert: number | null; rn_vorhanden: boolean | null })[];
  /** Volltext, der zur Akte vorliegt (selbst ergänzt oder geladen). */
  urteil: UrteilInfo | null;
  /** Höchste Randnummer im Volltext, wenn einer vorliegt. */
  rn_hoechste: number | null;
  /** Online-Quelle, bei der das noch nicht belegte Zitat geprüft werden kann. */
  online_offen: OnlineQuelle | null;
  /** Grund, warum das Zitat nicht online geprüft wird (vermutlich das eigene Verfahren). */
  online_gesperrt?: string | null;
}

export type OnlineQuelle = "bayern" | "neuris";

export const ONLINE_QUELLE: Record<OnlineQuelle, string> = {
  bayern: "gesetze-bayern.de",
  neuris: "NeuRIS (Testphase)",
};

/** Herkunftshinweis der Quellen, aus denen Volltexte geladen werden. */
export const QUELLEN_HINWEIS: Partial<Record<UrteilQuelle, string>> = {
  rii: "Quelle: Rechtsprechung im Internet (BMJ/BfJ). Anonymisierte Fassung, kein amtlicher Text.",
  bayern:
    "Quelle: Bürgerservice BAYERN.RECHT (gesetze-bayern.de). Redaktionell bearbeitete, anonymisierte Fassung, kein amtlicher Text; redaktionelle Leitsätze urheberrechtlich geschützt.",
  neuris: "Quelle: Rechtsinformationsportal des Bundes, Testphase – ohne Gewähr. Kein amtlicher Text.",
};

export type UrteilQuelle = "manuell" | "rii" | OnlineQuelle;

/** Welche Online-Quellen genutzt werden; gesetze-bayern.de ist immer an. */
export interface RechtsprechungQuellen {
  neuris: boolean;
}

/** Eine Entscheidung im Volltext zur Akte, z. B. ein PDF-Ausdruck aus juris. */
export interface UrteilInfo {
  id: number;
  /** null: steht ohne Akte in der Sammlung (Bereich „Rechtsprechung“). */
  akte_id: number | null;
  zitat: string | null;
  gericht: string;
  aktenzeichen: string | null;
  datum: string | null;
  quelle: UrteilQuelle;
  herkunft: string | null;
  dateiname: string;
  format: string;
  /** Prüfsumme der Datei; dieselbe Entscheidung in mehreren Akten hat dieselbe. */
  sha256: string;
  lesart: string;
  hinzugefuegt_am: string;
  hinweise: string[];
  doknr: string | null;
  kopf: { spruchkoerper: string | null; doktyp: string | null; normen: string | null; vorinstanz: string[]; titel: string | null } | null;
}

export interface UrteilVolltext extends UrteilInfo {
  abschnitte: { nr: number; seite: number | null; rn: number | null; text: string; teil: string | null }[];
}

/** Überschriften der Teile eines Volltexts von rechtsprechung-im-internet.de. */
export const URTEIL_TEILE: Record<string, string> = {
  leitsatz: "Leitsatz",
  sonstosatz: "Orientierungssatz",
  tenor: "Tenor",
  tatbestand: "Tatbestand",
  entscheidungsgruende: "Entscheidungsgründe",
  gruende: "Gründe",
  abwmeinung: "Abweichende Meinung",
  sonstlt: "Sonstiger Langtext",
};

/** Hinweis zur zitierten Randnummer: vorhanden, fehlt im Volltext oder nicht prüfbar. */
export function rnHinweis(f: { rn_zitiert: number | null; rn_vorhanden: boolean | null }, hoechste: number | null): string | null {
  if (f.rn_zitiert == null || f.rn_vorhanden == null) return null;
  if (f.rn_vorhanden) return `Rn. ${f.rn_zitiert} zitiert`;
  return hoechste != null && f.rn_zitiert > hoechste
    ? `Rn. ${f.rn_zitiert} zitiert, die Entscheidung hat nur Rn. 1–${hoechste}`
    : `Rn. ${f.rn_zitiert} zitiert, im Volltext nicht gefunden`;
}

/** Übliche Quellen für selbst ergänzte Entscheidungen (Vorschläge, frei änderbar). */
export const URTEIL_QUELLEN = ["juris", "beck-online", "openJur", "Gericht (Ausfertigung)", "Anlage der Gegenseite"];

/** "beck-online, Urteil.pdf" bzw. nur der Dateiname. */
export function urteilHerkunft(u: Pick<UrteilInfo, "herkunft" | "dateiname">): string {
  return u.herkunft ? `${u.herkunft}, ${u.dateiname}` : u.dateiname;
}

/** Eine Entscheidung der Sammlung, einmal je Datei, mit den Akten, denen sie zugeordnet ist. */
export interface SammlungEintrag extends UrteilInfo {
  akten: { akte_id: number; name: string; urteil_id: number; zitat: string | null }[];
  zugeordnet: boolean;
}

/** Treffer der Volltextsuche in den gespeicherten Entscheidungen, beste zuerst. */
export interface SammlungSuche {
  urteile: {
    sha256: string;
    fundstellen: { nr: number; rn: number | null; ausschnitt: { vor: string; treffer: string; nach: string } }[];
  }[];
  treffer: number;
}

/** Quellen der Online-Recherche im Bereich „Rechtsprechung“. */
export type RechercheQuelle = "rii" | "bayern" | "neuris";

/** Ein Treffer der Online-Recherche; ``urteil_id`` ist gesetzt, wenn die Entscheidung schon gespeichert ist. */
export interface RechercheTreffer {
  quelle: RechercheQuelle;
  doknr: string;
  gericht: string;
  spruchkoerper: string | null;
  datum: string | null;
  aktenzeichen: string;
  doktyp: string | null;
  titel: string | null;
  normen?: string | null;
  ausschnitt: string | null;
  link: string | null;
  urteil_id: number | null;
}

export interface RechercheErgebnis {
  quelle: RechercheQuelle;
  /** „verzeichnis“: im geladenen Verzeichnis gesucht, ohne Netz; „online“: bei der Quelle selbst. */
  ort: "verzeichnis" | "online";
  treffer: RechercheTreffer[];
  gesamt: number;
  weitere: boolean;
}

/** Felder der Suchmasken; leere Felder werden nicht gesendet. */
export interface RechercheFelder {
  gericht: string;
  gerichtsbarkeit: string;
  aktenzeichen: string;
  volltext: string;
  norm: string;
  von: string;
  bis: string;
}

export const RECHERCHE_QUELLE_NAME: Record<RechercheQuelle, string> = {
  rii: "rechtsprechung-im-internet.de",
  bayern: "Gerichtsentscheidungen Bayern",
  neuris: "NeuRIS (Testphase)",
};

export const RECHERCHE_GERICHTE = ["BVerfG", "BGH", "BVerwG", "BFH", "BAG", "BSG", "BPatG"];

export const BAYERN_GERICHTSBARKEITEN = [
  "Verfassungsgerichtsbarkeit",
  "Ordentliche Gerichtsbarkeit",
  "Verwaltungsgerichtsbarkeit",
  "Finanzgerichtsbarkeit",
  "Arbeitsgerichtsbarkeit",
  "Sozialgerichtsbarkeit",
  "Dienstgericht",
  "Sonstige Gerichte",
];

/** Geht die Suche bei rechtsprechung-im-internet.de an die Seite (Volltext, Norm, ECLI) oder ins Verzeichnis? */
export function riiOnline(f: Pick<RechercheFelder, "volltext" | "norm" | "aktenzeichen">): boolean {
  return !!(f.volltext.trim() || f.norm.trim() || f.aktenzeichen.trim().toUpperCase().startsWith("ECLI"));
}

/** Nur die Felder, die die Maske der Quelle hat und die ausgefüllt sind. */
export function rechercheFelder(quelle: RechercheQuelle, f: RechercheFelder): Partial<RechercheFelder> {
  const je: Record<RechercheQuelle, (keyof RechercheFelder)[]> = {
    rii: ["gericht", "aktenzeichen", "volltext", "norm", "von", "bis"],
    bayern: ["gerichtsbarkeit", "aktenzeichen", "volltext", "von", "bis"],
    neuris: ["gericht", "aktenzeichen", "volltext", "von", "bis"],
  };
  return Object.fromEntries(je[quelle].filter((k) => f[k].trim()).map((k) => [k, f[k].trim()]));
}

/** Titelzeile eines Treffers wie bei gespeicherten Entscheidungen. */
export function trefferTitel(t: RechercheTreffer): string {
  return urteilTitel({
    gericht: t.gericht,
    datum: t.datum,
    aktenzeichen: t.aktenzeichen,
    kopf: { spruchkoerper: t.spruchkoerper, doktyp: t.doktyp, normen: t.normen ?? null, vorinstanz: [], titel: t.titel },
  });
}

/** Ein aus dem Dokument erkannter Wert mit seiner Fundstelle. */
export interface Erkannt {
  wert: string;
  fundstelle: { abschnitt: number; seite: number | null; text: string };
}

/** Vorschlag für eine eigene Datei: Kopfdaten aus dem Text, jeweils mit Fundstelle oder null. */
export interface KopfVorschlag {
  dateiname: string;
  lesart: string;
  hinweise: string[];
  gericht: Erkannt | null;
  aktenzeichen: Erkannt | null;
  datum: Erkannt | null;
  art: Erkannt | null;
  herkunft: Erkannt | null;
}

/** Fundstelle eines erkannten Werts: „S. 1: „Aktenzeichen: 28 U 12/21““. */
export function erkanntText(e: Erkannt): string {
  const ort = e.fundstelle.seite != null ? `S. ${e.fundstelle.seite}` : `Abs. ${e.fundstelle.abschnitt}`;
  return `${ort}: „${e.fundstelle.text}“`;
}

/** Arten von Entscheidungen (Vorschläge, frei änderbar). */
export const URTEIL_ARTEN = ["Urteil", "Beschluss", "Versäumnisurteil", "Teilurteil", "Hinweisbeschluss", "Gerichtsbescheid"];

/** Anzeigename der Quelle einer gespeicherten Entscheidung. */
export const URTEIL_QUELLE_NAME: Record<UrteilQuelle, string> = {
  rii: "rechtsprechung-im-internet.de",
  bayern: "gesetze-bayern.de",
  neuris: "NeuRIS (Testphase)",
  manuell: "Eigene Datei",
};

/** Kopfzeile einer Entscheidung: „BGH 8. Zivilsenat, Urteil vom 12.10.2016 – VIII ZR 103/15“. */
export function urteilTitel(u: Pick<UrteilInfo, "gericht" | "datum" | "aktenzeichen" | "kopf">): string {
  const gericht = [u.gericht, u.kopf?.spruchkoerper].filter(Boolean).join(" ");
  const datum = u.datum ? `, ${u.kopf?.doktyp ?? "Entscheidung"} vom ${u.datum.split("-").reverse().join(".")}` : "";
  return `${gericht}${datum}${u.aktenzeichen ? ` – ${u.aktenzeichen}` : ""}`;
}

/** Filter der Sammlung: Zuordnung, Quelle und freier Text über Gericht, Aktenzeichen, Titel und Akten. */
export function sammlungPasst(
  e: SammlungEintrag,
  f: { zuordnung: "alle" | "zugeordnet" | "frei"; quelle: UrteilQuelle | "alle"; text: string },
): boolean {
  if (f.zuordnung === "zugeordnet" && !e.zugeordnet) return false;
  if (f.zuordnung === "frei" && e.zugeordnet) return false;
  if (f.quelle !== "alle" && e.quelle !== f.quelle) return false;
  const woerter = f.text.toLocaleLowerCase("de-DE").split(/\s+/).filter(Boolean);
  if (!woerter.length) return true;
  const heuhaufen = [urteilTitel(e), e.kopf?.titel, e.kopf?.normen, e.herkunft, e.dateiname, ...e.akten.map((a) => a.name)]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase("de-DE");
  return woerter.every((w) => heuhaufen.includes(w));
}

/** Selbst ergänzte bzw. geladene Entscheidungen über alle Akten, je Quelle. */
export interface EigeneUrteile {
  gesamt: number;
  quellen: { quelle: UrteilQuelle; herkunft: string | null; anzahl: number }[];
}

export interface RechtsprechungStand {
  id: number;
  abgerufen_am: string;
  eintraege: number;
  gerichte: Record<string, { anzahl: number; von: string | null; bis: string | null }>;
  neu?: boolean;
}

export interface GerichtsverzeichnisStand {
  sha256: string;
  quelle: string;
  version: string | null;
  abgerufen_am: string;
  eintraege: number;
  arten: Record<string, number>;
  neu?: boolean;
}

/** „BGH ab 2010, BVerfG ab 1998 …“ aus dem Stand des Verzeichnisses. */
export function rechtsprechungUmfang(stand: Pick<RechtsprechungStand, "gerichte">): string {
  return Object.entries(stand.gerichte)
    .sort(([, a], [, b]) => b.anzahl - a.anzahl)
    .map(([g, z]) => (z.von ? `${g} ab ${z.von.slice(0, 4)}` : g))
    .join(", ");
}

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

// --- Abgleich ------------------------------------------------------------------------------------

export type AbgleichStatus = "abweichend" | "uebereinstimmend" | "einzeln";
export type Einordnung = "im_dokument" | "innerhalb_partei" | "zwischen_parteien" | "partei_unbekannt";

export interface AbgleichFundstelle {
  dokument_id: number;
  dateiname: string;
  abschnitt: number;
  seite: number | null;
  rn: number | null;
  /** Beteiligten-Tags des Dokuments, z. B. ["Kläger"]. */
  parteien: string[];
  /** Der Satz um den Wert, zum Hervorheben getrennt. */
  ausschnitt: { davor: string; wert: string; danach: string };
}

export interface AbgleichWert {
  wert: string;
  art: "datum" | "monat" | "betrag" | "km" | "code";
  anzeige: string;
  fundstellen: AbgleichFundstelle[];
}

export interface AbgleichMerkmal {
  merkmal: string;
  titel: string;
  status: AbgleichStatus;
  einordnung: Einordnung[];
  dokumente: number;
  werte: AbgleichWert[];
}

export interface Abgleich {
  dokumente: number;
  merkmale: AbgleichMerkmal[];
  zaehlung: Record<AbgleichStatus, number>;
}

export const EINORDNUNG_TEXT: Record<Einordnung, string> = {
  im_dokument: "im selben Dokument",
  innerhalb_partei: "innerhalb einer Partei",
  zwischen_parteien: "zwischen den Beteiligten",
  partei_unbekannt: "Beteiligte unbekannt (Dokumente ohne Tag)",
};

/** Kurzfassung des Ergebnisses, z. B. "7 mögliche Abweichungen, 4 Übereinstimmungen in 9 Dokumenten". */
export function abgleichZusammenfassung(a: Pick<Abgleich, "dokumente" | "zaehlung">): string {
  const n = (zahl: number, eins: string, mehr: string) => `${zahl} ${zahl === 1 ? eins : mehr}`;
  return (
    `${n(a.zaehlung.abweichend, "mögliche Abweichung", "mögliche Abweichungen")}, ` +
    `${n(a.zaehlung.uebereinstimmend, "Übereinstimmung", "Übereinstimmungen")} ` +
    `in ${n(a.dokumente, "Dokument", "Dokumenten")}`
  );
}

// --- Sprachmodell ---------------------------------------------------------------------------------

export interface KiModell {
  name: string;
  groesse: number | null;
  parameter: string | null;
  quantisierung: string | null;
}

/** Stand des lokalen Modellprogramms (Ollama, LM Studio). */
export interface KiLokalStatus {
  anbieter: string;
  endpunkt: string;
  modell: string;
  kontext: number;
  anbieter_titel: string;
  anbieter_liste: { id: string; titel: string; endpunkt: string }[];
  empfohlen: string;
  erreichbar: boolean;
  modelle: KiModell[];
  /** Programm erreichbar und gewähltes Modell installiert. */
  bereit: boolean;
  hinweis: string | null;
}

/** Stand der externen KI; der Schlüssel selbst kommt nie zur Oberfläche, nur seine letzten vier Zeichen. */
export interface KiExternStatus {
  freigegeben: boolean;
  anbieter: string;
  anbieter_titel: string;
  anbieter_liste: { id: string; titel: string; adresse: string; vorschlag: string }[];
  adresse: string;
  modell: string;
  kontext: number;
  schluessel_hinterlegt: boolean;
  schluessel_ende: string | null;
  /** Ob der Anbieter bei dieser Abfrage angefragt wurde (nur die Modellliste, keine Inhalte). */
  geprueft: boolean;
  erreichbar: boolean;
  modelle: KiModell[];
  bereit: boolean;
  hinweis: string | null;
}

export interface KiStatus {
  /** Welches Modell Analyse und Chat verwenden. */
  /** Schalter „KI verwenden“ aus: kein Sprachmodell wird gefragt. */
  abgeschaltet: boolean;
  aktiv: "lokal" | "extern";
  /** Dokumentinhalte gehen an einen externen Anbieter. */
  extern: boolean;
  bereit: boolean;
  modell: string;
  titel: string;
  kontext: number;
  hinweis: string | null;
  lokal: KiLokalStatus;
  externe: KiExternStatus;
}

/** Für die Anzeige in der Navigation, ohne Anfrage an ein Modell. */
export interface KiModus {
  /** KI in den Einstellungen ausgeschaltet; Knöpfe, die ein Sprachmodell brauchen, sind ausgeblendet. */
  aus: boolean;
  aktiv: "lokal" | "extern";
  titel: string | null;
  modell: string;
  /** Nur lokal: Modell auf diesem Rechner oder auf einem anderen Rechner im eigenen Netzwerk. */
  ort: "geraet" | "netzwerk" | null;
}

/** Kurzname des KI-Modus für Navigation und Startseite. */
export function kiModusName(modus: KiModus | null): string {
  if (modus?.aus) return "Nicht aktiv";
  if (modus?.aktiv === "extern") return `Externer Anbieter (${modus.titel})`;
  return modus?.ort === "netzwerk" ? "Lokales Netzwerk" : "Eigener Rechner";
}

export type KiAufgabe =
  | "zusammenfassung_dokument"
  | "zusammenfassung_akte"
  | "widersprueche"
  | "chronologie"
  | "gegenueberstellung"
  | "chat"
  | "metadaten";

export type GegenueberstellungErgebnis =
  | "traegt"
  | "traegt_teilweise"
  | "traegt_nicht"
  | "nicht_beurteilbar"
  | "nicht_pruefbar";

/** Stelle aus einer Entscheidung, am gespeicherten Volltext geprüft. */
export interface UrteilStelle {
  stelle: string;
  rn: number | null;
  treffer: "woertlich" | "angenaehert";
  ausschnitt: { davor: string; wert: string; danach: string };
}

/** Ein Urteilszitat: was der Schriftsatz der Entscheidung entnimmt und was sie an der Stelle sagt. */
export interface GegenueberstellungZitat {
  zitat: string;
  gericht: string;
  aktenzeichen: string | null;
  rn_zitiert: number | null;
  dokument_id: number;
  dateiname: string;
  abschnitt: number;
  zitierstelle: KiFundstelle;
  urteil_id: number | null;
  urteil: string | null;
  ergebnis: GegenueberstellungErgebnis;
  status: "belegt" | "ohne_beleg" | "nicht_pruefbar";
  hinweis: string | null;
  stellen: string[];
  behauptung?: string;
  entscheidung?: string;
  begruendung?: string;
  schriftsatz_belege?: KiFundstelle[];
  urteil_belege?: UrteilStelle[];
  gespeichert?: boolean;
}

export interface Gegenueberstellung {
  zitate: GegenueberstellungZitat[];
  /** Zitate mit Volltext, die noch nicht gegenübergestellt sind. */
  offen: number;
  anzahl: number;
  modell: string | null;
}

export interface KiFundstelle extends AbgleichFundstelle {
  /** Ob das Zitat des Modells wörtlich oder nur angenähert im Dokument steht. */
  treffer: "woertlich" | "angenaehert";
}

export interface KiAussage {
  text: string;
  art: string;
  status: "belegt" | "ohne_beleg";
  fundstellen: KiFundstelle[];
}

interface KiErgebnisKopf {
  modell: string;
  erstellt_am: string;
  gespeichert: boolean;
  /** Anzahl der Anfragen bei Widersprüchen und Chronologie. */
  teile?: number;
  /** Teile, die das Modell auch beim zweiten Versuch unbrauchbar beantwortet hat; dann nicht gespeichert. */
  luecken?: number[];
  /** Dokumente, aus denen Absätze fehlen, weil das Modell dort unbrauchbar antwortete. */
  luecken_dokumente?: { dateiname: string; absaetze: string[] }[];
}

export interface KiZusammenfassung extends KiErgebnisKopf {
  dokument_id?: number;
  dateiname?: string;
  teile?: number;
  aussagen: KiAussage[];
  zaehlung: { belegt: number; ohne_beleg: number };
  /** Nur bei der Akte: die zusammengefassten Dokumente. */
  dokumente?: { dokument_id: number; dateiname: string }[];
}

export interface KiAngabe {
  text: string;
  haltung: string;
  fundstelle: KiFundstelle;
}

export interface KiWiderspruch {
  thema: string;
  art: "widerspruch" | "spannung";
  erklaerung: string;
  einordnung: Einordnung[];
  angaben: KiAngabe[];
}

export interface KiWidersprueche extends KiErgebnisKopf {
  dokumente: { dokument_id: number; dateiname: string; angaben: number; verworfen: number }[];
  angaben: number;
  verworfen: number;
  widersprueche: KiWiderspruch[];
}

export interface KiEreignis {
  /** ISO-Datum („2025-06-27“) oder Monat („2025-06“), zum Sortieren. */
  datum: string;
  /** Wie angezeigt: „27.06.2025“ oder „Mitte Juni 2025“. */
  anzeige: string;
  art: "ereignis" | "frist" | "dokument";
  ereignis: string;
  streitig: boolean;
  /** belegt: Das Datum steht in einem der zitierten Absätze. */
  status: "belegt" | "ohne_beleg";
  quellen: KiAngabe[];
}

export interface KiChronologie extends KiErgebnisKopf {
  dokumente: { dokument_id: number; dateiname: string }[];
  angaben: number;
  verworfen: number;
  ereignisse: KiEreignis[];
}

export const EREIGNIS_ART_TEXT: Record<KiEreignis["art"], string> = {
  ereignis: "Ereignis",
  frist: "Frist",
  dokument: "Dokument",
};

export interface KiAuftrag {
  auftrag_id: number;
  aufgabe: KiAufgabe;
  status: "laeuft" | "fertig" | "fehler" | "abgebrochen";
  text: string;
  schritt: number | null;
  von: number | null;
  sekunden: number;
  ergebnis: unknown;
  fehler: string | null;
}

export interface KiErgebnisse {
  zusammenfassung_akte: KiZusammenfassung | null;
  widersprueche: KiWidersprueche | null;
  chronologie: KiChronologie | null;
  /** Zusammenfassungen je Dokument, Schlüssel ist die Dokumentnummer. */
  dokumente: Record<string, KiZusammenfassung>;
}

export const ART_TEXT: Record<string, string> = {
  tatsache: "Inhalt",
  vortrag: "Vortrag",
  bestreiten: "Bestreiten",
  rechtsansicht: "Rechtsansicht",
  antrag: "Antrag",
  entscheidung: "Gericht",
  sonstiges: "Sonstiges",
  gegenstand: "Gegenstand",
  verlauf: "Verlauf",
  streitig: "Streitig",
  offen: "Offen",
};

export const HALTUNG_TEXT: Record<string, string> = {
  behauptet: "behauptet",
  bestritten: "bestreitet",
  unstreitig: "unstreitig",
  festgestellt: "festgestellt",
};

// --- Ausgabe der KI-Ergebnisse ---------------------------------------------------------------------------

export type ExportTeil = "widersprueche" | "chronologie" | "zusammenfassung_akte" | "dokumente";
export type ExportFormat = "docx" | "pdf" | "xlsx" | "md" | "txt";

export const EXPORT_FORMATE: { id: ExportFormat; titel: string }[] = [
  { id: "docx", titel: "Word" },
  { id: "pdf", titel: "PDF" },
  { id: "xlsx", titel: "Excel" },
  { id: "md", titel: "Markdown" },
  { id: "txt", titel: "Text" },
];

export interface Druckansicht {
  titel: string;
  html: string;
  stil: string;
}

/** Welche Teile der Analyse gespeicherte Ergebnisse haben, in der Reihenfolge der Ausgabe. */
export function exportTeile(e: KiErgebnisse): { id: ExportTeil; titel: string; vorhanden: boolean }[] {
  const n = (zahl: number | undefined) => (zahl != null ? ` (${zahl})` : "");
  return [
    { id: "widersprueche", titel: `Widersprüche${n(e.widersprueche?.widersprueche.length)}`, vorhanden: e.widersprueche != null },
    { id: "chronologie", titel: `Chronologie${n(e.chronologie?.ereignisse.length)}`, vorhanden: e.chronologie != null },
    { id: "zusammenfassung_akte", titel: "Zusammenfassung der Akte", vorhanden: e.zusammenfassung_akte != null },
    {
      id: "dokumente",
      titel: `Zusammenfassungen der Dokumente${n(Object.keys(e.dokumente).length || undefined)}`,
      vorhanden: Object.keys(e.dokumente).length > 0,
    },
  ];
}

/** Druckdialog des Systems. Unter macOS druckt window.print() in der App nichts; der Befehl der App kann es überall. */
export async function drucken(): Promise<void> {
  try {
    await invoke("drucken");
  } catch {
    window.print();
  }
}

/** Laufzeit lesbar: „45 s“, „3:05 min“. */
export function dauerText(sekunden: number): string {
  if (sekunden < 60) return `${sekunden} s`;
  return `${Math.floor(sekunden / 60)}:${String(sekunden % 60).padStart(2, "0")} min`;
}

/** Modellgröße auf der Festplatte, z. B. „9,3 GB“. */
export function groesseText(bytes: number | null): string {
  if (!bytes || bytes < 1e8) return "";
  return `${(bytes / 1e9).toLocaleString("de-DE", { maximumFractionDigits: 1 })} GB`;
}

/** Ob ein gespeichertes Ergebnis zur Akte noch passt: dieselben Dokumente wie jetzt. */
export function veraltet(ergebnis: { dokumente?: { dokument_id: number }[] } | null, dokumentIds: number[]): boolean {
  if (!ergebnis?.dokumente) return false;
  const damals = ergebnis.dokumente.map((d) => d.dokument_id).sort((a, b) => a - b);
  const jetzt = [...dokumentIds].sort((a, b) => a - b);
  return damals.length !== jetzt.length || damals.some((id, i) => id !== jetzt[i]);
}

/** Erstellzeitpunkt eines Ergebnisses in Ortszeit, z. B. „13.10.2026, 18:05“. */
export function zeitpunkt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

// --- Chat mit Akte und Dokument -----------------------------------------------------------------------

export interface ChatAussage {
  text: string;
  /** tatsache: aus den Dokumenten; einschaetzung: Würdigung des Modells; hinweis: etwa „steht nicht in der Akte“;
   * berechnung: von der App mit dem Rechner der Toolbox gerechnet. */
  art: "tatsache" | "einschaetzung" | "hinweis" | "berechnung";
  status: "belegt" | "ohne_beleg" | "hinweis";
  fundstellen: KiFundstelle[];
  /** Zitate aus Normen der Wissensbasis, am gespeicherten Wortlaut geprüft. */
  normbelege?: ChatNormbeleg[];
  urteilsbelege?: ChatUrteilsbeleg[];
  berechnung?: ChatBerechnung;
}

export interface ChatNormbeleg {
  /** z. B. „§ 280 Abs. 1 BGB“ */
  norm: string;
  gesetz: string;
  bezeichnung: string;
  titel: string | null;
  /** Stand der Fassung in der Wissensbasis. */
  fassung: string;
  fassung_id: number;
  treffer: "woertlich" | "angenaehert";
  ausschnitt: { davor: string; wert: string; danach: string };
}

/** Zitat aus einer Entscheidung, die der Akte im Volltext vorliegt. */
export interface ChatUrteilsbeleg {
  urteil_id: number;
  /** z. B. „BGH, Entscheidung vom 14.01.2021 – VII ZR 193/19“ */
  urteil: string;
  /** „Rn. 22“, „Leitsatz“ oder „Abschn. 3“ */
  stelle: string;
  rn: number | null;
  treffer: "woertlich" | "angenaehert";
  ausschnitt: { davor: string; wert: string; danach: string };
}

export interface ChatEingabe {
  feld: string;
  titel: string;
  wert: string;
  status: "belegt" | "ohne_beleg";
  fundstelle: KiFundstelle | null;
  /** frage: aus der Frage übernommen; heute: Tag der Frage. */
  quelle: "frage" | "heute" | null;
}

export type ChatBerechnung =
  | { rechner: "zinsen"; ergebnis: ZinsErgebnis | null; eingaben: ChatEingabe[]; fehlt: string[]; fehler: string | null; belegt: boolean; text: string }
  | { rechner: "frist"; ergebnis: FristErgebnis | null; eingaben: ChatEingabe[]; fehlt: string[]; fehler: string | null; belegt: boolean; text: string };

export interface ChatAuswahl {
  vollstaendig: boolean;
  absaetze: number;
  von: number;
  dokumente: number;
  dokumente_von: number;
}

export interface ChatEintrag {
  id: number;
  rolle: "frage" | "antwort";
  erstellt_am: string;
  /** Nur bei Fragen. */
  text?: string;
  aussagen?: ChatAussage[];
  auswahl?: ChatAuswahl;
  modell?: string;
  /** Name des externen Anbieters, wenn die Frage das Gerät verlassen hat. */
  extern?: string | null;
  /** Bei Fragen, ob zitierte Entscheidungen den Vortrag tragen: die Gegenüberstellung je Zitat. */
  gegenueberstellung?: Gegenueberstellung;
  /** Zusatzwissen, das mit der Frage ging. */
  wissen?: {
    rechner?: boolean;
    gesetze?: string[];
    fehlend?: string[];
    zeichen?: number;
    gekuerzt?: boolean;
    urteile?: string[];
    urteile_fehlend?: string[];
    urteile_zeichen?: number;
  };
}

/** Was dem Modell vorlag, z. B. „alle 3 Dokumente vollständig“ oder „120 von 450 Absätzen aus 6 von 8 Dokumenten“. */
export function auswahlText(a: ChatAuswahl): string {
  const doks = (n: number) => `${n} ${n === 1 ? "Dokument" : "Dokumenten"}`;
  if (a.vollstaendig) {
    return a.dokumente_von === 1 ? "das Dokument vollständig" : `alle ${a.dokumente_von} Dokumente vollständig`;
  }
  const aus = a.dokumente_von === 1 ? "" : ` aus ${a.dokumente === a.dokumente_von ? doks(a.dokumente) : `${a.dokumente} von ${doks(a.dokumente_von)}`}`;
  return `${a.absaetze} von ${a.von} Absätzen${aus}, ausgewählt nach den Begriffen der Frage`;
}

// ---- Toolbox: Rechner aus JuraBox Lite ----

export interface ZinsZeile {
  von: string;
  bis: string;
  tage: number;
  satz: string;
  grundlage: string;
  zinsen: string;
  zinssaldo: string;
  restschuld: string;
  ereignis: string;
}

export interface ZinsErgebnis {
  zeilen: ZinsZeile[];
  summe_tage: number;
  summe_zinsen: string;
  summe_zinsen_genau: string;
  pauschale: string;
  hauptforderung: string;
  offene_zinsen: string;
  gesamt: string;
  aktueller_satz: string;
  zinsen_pro_tag: string;
  grundlagen: string[];
  basiszins_quelle: string;
  hinweise: string[];
}

export interface BasiszinsStand {
  quelle: string;
  stand: string;
  saetze: { ab: string; satz: string; eigen: boolean }[];
  aktuell: { ab: string; satz: string };
  bekannt_bis: string;
}

export interface FristErgebnis {
  bezugstag: string;
  wochentag_bezugstag: string;
  fristbeginn: string;
  wochentag_fristbeginn: string;
  rechnerisches_ende: string;
  wochentag_rechnerisch: string;
  ende: string;
  wochentag: string;
  hinweise: string[];
  verschoben: boolean;
  grund: string;
  grundlagen: string[];
  land: string;
  feiertage_stand: string;
}

export interface KostenPosten {
  nr: string;
  text: string;
  satz: string | null;
  betrag: string;
}

export interface KostenAbrechnung {
  titel: string;
  posten: KostenPosten[];
  netto: string;
  summe: string;
  /** Gegenseite: so viele gleiche Anwälte stehen hinter dieser Abrechnung. */
  anzahl?: number;
}

export interface ProzesskostenErgebnis {
  streitwert: string;
  fassung: string;
  fassung_titel: string;
  gebuehr_gkg: string;
  gebuehr_rvg: string;
  gericht: KostenPosten[];
  vorgerichtlich: KostenAbrechnung | null;
  eigene: KostenAbrechnung[];
  gegner: KostenAbrechnung[];
  summe_gericht: string;
  summe_eigene: string;
  summe_gegner: string;
  kostenrisiko: string;
  umsatzsteuer: string | null;
  hinweise: string[];
  grundlagen: string[];
}

export const BUNDESLAENDER: [string, string][] = [
  ["BW", "Baden-Württemberg"], ["BY", "Bayern"], ["BE", "Berlin"], ["BB", "Brandenburg"], ["HB", "Bremen"],
  ["HH", "Hamburg"], ["HE", "Hessen"], ["MV", "Mecklenburg-Vorpommern"], ["NI", "Niedersachsen"],
  ["NW", "Nordrhein-Westfalen"], ["RP", "Rheinland-Pfalz"], ["SL", "Saarland"], ["SN", "Sachsen"],
  ["ST", "Sachsen-Anhalt"], ["SH", "Schleswig-Holstein"], ["TH", "Thüringen"],
];

/** Betrag aus dem Kern ("1234.5") deutsch, mit zwei oder mehr Nachkommastellen: "1.234,50 €". */
export function euro(betrag: string | number, stellen = 2): string {
  return Number(betrag).toLocaleString("de-DE", { minimumFractionDigits: stellen, maximumFractionDigits: stellen }) + " €";
}

/** Gebührensatz aus dem Kern deutsch: "1.3" → "1,3", "3" → "3,0". */
export function satzDe(satz: string): string {
  return satz.includes(".") ? satz.replace(".", ",") : satz + ",0";
}

/** Prozentsatz aus dem Kern ("8.62") deutsch: "8,62 %". */
export function prozent(satz: string | number): string {
  return Number(satz).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " %";
}

/** ISO-Datum (JJJJ-MM-TT) als TT.MM.JJJJ, ohne Umweg über die Zeitzone. */
export function datumDe(iso: string): string {
  const [j, m, t] = iso.split("-");
  return `${t}.${m}.${j}`;
}

/** ISO-Zeitpunkt ("2026-10-17T21:30:00+02:00") als "17.10.2026, 21:30", so wie er gespeichert ist. */
export function zeitpunktDe(iso: string): string {
  const uhr = iso.slice(11, 16);
  return datumDe(iso.slice(0, 10)) + (uhr ? `, ${uhr}` : "");
}

/** Datum eines Dokuments für die Anzeige: Wert, kurze Herkunft und Erläuterung mit Fundstelle. */
export function dokumentDatum(
  d: Pick<AktenDokument, "datum" | "datum_quelle" | "datum_seite" | "datum_text" | "gespeichert_am" | "gespeichert_quelle">,
): { text: string; herkunft: string; erklaerung: string } {
  const gespeichert =
    d.gespeichert_am &&
    `Zuletzt gespeichert: ${zeitpunktDe(d.gespeichert_am)} (${d.gespeichert_quelle === "word" ? "laut Word" : "Dateidatum"}).`;
  if (!d.datum || d.datum_quelle === "unbekannt" || !d.datum_quelle) {
    return { text: "–", herkunft: "", erklaerung: "Im Dokument steht keine Datumszeile; ein Speicherdatum ist nicht bekannt." };
  }
  switch (d.datum_quelle) {
    case "dokument":
      return {
        text: datumDe(d.datum),
        herkunft: "aus dem Dokument",
        erklaerung: [
          `Datumszeile${d.datum_seite != null ? ` auf S. ${d.datum_seite}` : ""}: „${d.datum_text}“.`,
          gespeichert,
        ]
          .filter(Boolean)
          .join(" "),
      };
    case "word":
      return {
        text: datumDe(d.datum),
        herkunft: "zuletzt gespeichert",
        erklaerung: `Keine Datumszeile im Dokument. ${gespeichert}`,
      };
    case "datei":
      return {
        text: datumDe(d.datum),
        herkunft: "Dateidatum",
        erklaerung: `Keine Datumszeile im Dokument. ${gespeichert}`,
      };
    case "manuell":
      return {
        text: datumDe(d.datum),
        herkunft: "von Hand",
        erklaerung: "Von Hand eingetragen (Ansicht „Details“).",
      };
  }
}

/** Heutiges Datum als JJJJ-MM-TT in lokaler Zeit. */
export function heuteIso(jetzt = new Date()): string {
  const z = (n: number) => String(n).padStart(2, "0");
  return `${jetzt.getFullYear()}-${z(jetzt.getMonth() + 1)}-${z(jetzt.getDate())}`;
}

export interface Umgebung {
  id: string;
  name: string;
  angelegt_am: string | null;
  standard: boolean;
  aktiv: boolean;
}

export interface UmgebungsListe {
  aktiv: string;
  umgebungen: Umgebung[];
}

/** Die aktive Arbeitsumgebung; angezeigt wird sie erst, wenn es mehr als eine gibt. */
export function aktiveUmgebung(liste: UmgebungsListe | null): Umgebung | null {
  if (!liste || liste.umgebungen.length < 2) return null;
  return liste.umgebungen.find((u) => u.id === liste.aktiv) ?? null;
}

// ---------------------------------------------------------------- Eigene Daten

export interface FeldDef {
  schluessel: string;
  titel: string;
  typ: "text" | "email" | "tel" | "url" | "auswahl" | "mehrfach" | "mehrzeilig" | "ja_nein" | "datum";
  pflicht: boolean;
  hinweis?: string;
  optionen?: string[];
  hoechstens?: number;
  vorgabe?: string;
}

export type Werte = Record<string, string | string[] | boolean>;

export interface EigeneFelder {
  felder: Record<string, FeldDef[]>;
  formen: Record<string, string>;
}

export interface EigenePerson {
  id: number;
  daten: Werte;
  archiviert: boolean;
  geaendert_am: string;
  mitgliedschaft: Werte;
}

export interface EigeneOrganisation {
  id: number;
  art: "kanzlei" | "unternehmen" | "konzerngesellschaft" | "beauftragte_kanzlei";
  daten: Werte;
  archiviert: boolean;
  geaendert_am: string;
  anwaelte?: EigenePerson[];
}

export type Organisationsform = "einzelanwalt" | "kanzlei" | "rechtsabteilung";

export interface EigeneDaten {
  profil: {
    form: Organisationsform | null;
    organisation_id: number | null;
    person_id: number | null;
    assistent_fertig: boolean;
  };
  formen: Record<string, string>;
  organisation: EigeneOrganisation | null;
  organisation_felder: string;
  organisation_name: string;
  inhaber: EigenePerson | null;
  inhaber_felder: string;
  berufstraeger: EigenePerson[];
  konzerngesellschaften: EigeneOrganisation[];
  beauftragte_kanzleien: EigeneOrganisation[];
  fehlend: string[];
  hinweise: string[];
}

/** Logo (data-URL) und Kurzbezeichnung der aktiven Umgebung, dazu der Name aus „Eigene Daten“. */
export interface Marke {
  logo: string | null;
  kurzbezeichnung: string;
  name: string;
  /** Ob Word das Logo in den Briefkopf übernehmen kann (PNG/JPG oder ein schon gerendertes Druckbild). */
  druckbild?: boolean;
}

/**
 * Rendert ein Logo (data-URL, z. B. SVG) als PNG, 300 Pixel hoch, für den Briefkopf in Word.
 * Word kann SVG und WebP nicht einbetten; die Oberfläche kann sie zeichnen, der Kern nicht.
 */
export function logoAlsPng(logo: string, hoehe = 300): Promise<string> {
  return new Promise((fertig, fehler) => {
    const bild = new Image();
    bild.onload = () => {
      const b = bild.naturalWidth || 900;
      const h = bild.naturalHeight || 300;
      const leinwand = document.createElement("canvas");
      leinwand.height = hoehe;
      leinwand.width = Math.max(1, Math.round((b / h) * hoehe));
      const zeichnung = leinwand.getContext("2d");
      if (!zeichnung) return fehler(new Error("Zeichnen nicht möglich"));
      zeichnung.drawImage(bild, 0, 0, leinwand.width, leinwand.height);
      fertig(leinwand.toDataURL("image/png"));
    };
    bild.onerror = () => fehler(new Error("Das Logo ließ sich nicht zeichnen."));
    bild.src = logo;
  });
}

/** Legt für ein SVG- oder WebP-Logo das PNG für Word an, falls es fehlt; sonst unverändert. */
export async function mitDruckbild(marke: Marke): Promise<Marke> {
  if (!marke.logo || marke.druckbild !== false) return marke;
  try {
    return await kern<Marke>("marke.druckbild_setzen", { png: await logoAlsPng(marke.logo) });
  } catch {
    return marke; // Dann erscheint im Reiter „Schriftstücke“ ein Hinweis.
  }
}

export interface EigeneKurzstand {
  text: string;
  eingerichtet: boolean;
  fehlend: number;
  hinweise: number;
}

export interface EigeneAenderung {
  id: number;
  zeitpunkt: string;
  objekt: string;
  bezeichnung: string;
  feld: string;
  alt: string | null;
  neu: string | null;
}

/** „Dr. Erika Muster“ aus den Personendaten. */
export function personName(daten: Werte): string {
  return [daten.titel, daten.vorname, daten.nachname].filter((t) => typeof t === "string" && t).join(" ");
}

/** Anzeigetext eines Feldwerts; leer, wenn nichts eingetragen ist. */
export function feldText(feld: FeldDef, wert: Werte[string] | undefined): string {
  if (wert === undefined || wert === null) return "";
  if (feld.typ === "ja_nein") return wert === true ? "ja" : "";
  if (Array.isArray(wert)) return wert.join(", ");
  if (feld.typ === "datum" && typeof wert === "string" && wert) return datumDe(wert);
  return String(wert);
}

/** Anfangswerte eines Formulars: gespeicherte Werte, sonst Vorgaben. */
export function startwerte(felder: FeldDef[], gespeichert: Werte | null | undefined): Werte {
  const werte: Werte = {};
  for (const f of felder) {
    const g = gespeichert?.[f.schluessel];
    if (g !== undefined) werte[f.schluessel] = g;
    else if (f.typ === "mehrfach") werte[f.schluessel] = [];
    else if (f.typ === "ja_nein") werte[f.schluessel] = false;
    else werte[f.schluessel] = gespeichert ? "" : (f.vorgabe ?? "");
  }
  return werte;
}

// ---------------------------------------------------------------- Diagnose

export type DiagnoseStand = "ok" | "warnung" | "fehler" | "aus";

export interface DiagnosePruefung {
  id: string;
  gruppe: string;
  gruppe_titel: string;
  titel: string;
}

export interface DiagnoseErgebnis {
  id: string;
  gruppe: string;
  titel: string;
  stand: DiagnoseStand;
  meldung: string;
  details: string[];
  hilfe: string | null;
  dauer_ms: number;
}

/** Klartext-Bericht zum Weitergeben; enthält nur die Prüfergebnisse, keine Dokumentinhalte. */
export function diagnoseBericht(
  pruefungen: DiagnosePruefung[],
  ergebnisse: Record<string, DiagnoseErgebnis>,
  zeitpunkt: Date,
): string {
  const zeichen: Record<DiagnoseStand, string> = { ok: "OK", warnung: "HINWEIS", fehler: "FEHLER", aus: "AUS" };
  const zeilen = [`JuraBox-Diagnose vom ${zeitpunkt.toLocaleString("de-DE")}`];
  let gruppe = "";
  for (const p of pruefungen) {
    if (p.gruppe_titel !== gruppe) {
      gruppe = p.gruppe_titel;
      zeilen.push("", `## ${gruppe}`);
    }
    const e = ergebnisse[p.id];
    if (!e) {
      zeilen.push(`- ${p.titel}: nicht geprüft`);
      continue;
    }
    zeilen.push(`- [${zeichen[e.stand]}] ${p.titel}: ${e.meldung}`);
    for (const d of e.details) zeilen.push(`    ${d}`);
    if (e.hilfe) zeilen.push(`    Was tun: ${e.hilfe}`);
  }
  return zeilen.join("\n");
}

// ---------------------------------------------------------------- Sortieren von Tabellen

export interface Sortierung {
  spalte: string;
  absteigend: boolean;
}

type SortWert = string | number | null | undefined;

/**
 * Sortiert nach einer Spalte; Texte deutsch und mit Zahlen in natürlicher Reihenfolge („2 O“ vor „10 O“).
 * Leere Werte stehen immer am Ende, auch bei absteigender Sortierung.
 */
export function sortiert<T>(liste: T[], s: Sortierung, werte: Record<string, (x: T) => SortWert>): T[] {
  const wert = werte[s.spalte];
  if (!wert) return liste;
  const leer = (v: SortWert) => v == null || v === "";
  return [...liste].sort((a, b) => {
    const x = wert(a);
    const y = wert(b);
    if (leer(x) || leer(y)) return leer(x) === leer(y) ? 0 : leer(x) ? 1 : -1;
    const c =
      typeof x === "number" && typeof y === "number"
        ? x - y
        : String(x).localeCompare(String(y), "de", { numeric: true, sensitivity: "base" });
    return s.absteigend ? -c : c;
  });
}

/** Sortierschlüssel für eigene Aktenzeichen Nummer/Jahr („102/26 RS“): erst das Jahr, dann die Nummer. */
export function aktenzeichenSchluessel(az: string | null | undefined): string | null {
  if (!az) return null;
  const m = /^(\d+)\s*\/\s*(\d{2,4})/.exec(az.trim());
  return m ? `${m[2].slice(-2)}-${m[1].padStart(6, "0")}` : az;
}

// --- Nachrichten auf der Startseite (RSS/Atom) --------------------------------------------------------

export interface NachrichtenFeed {
  id: string;
  titel: string;
  url: string;
  hinzugefuegt: string;
}

export interface NachrichtenVorschlag {
  titel: string;
  url: string;
  hinweis: string;
  eingetragen: boolean;
}

export interface NachrichtenEinstellungen {
  feeds: NachrichtenFeed[];
  vorschlaege: NachrichtenVorschlag[];
}

export interface Nachricht {
  titel: string;
  link: string | null;
  datum: string | null;
  auszug: string;
  quelle: string;
  feed_id: string;
}

export interface NachrichtenListe {
  feeds: number;
  eintraege: Nachricht[];
  gesamt: number;
  stand: string | null;
  laeuft: boolean;
  fehler: { feed_id: string; titel: string; text: string }[];
}

/** „vor 5 Min.“, „vor 3 Std.“, „gestern“ bzw. das Datum: wann eine Nachricht erschienen ist. */
export function nachrichtAlter(iso: string | null, jetzt: Date = new Date()): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const minuten = Math.round((jetzt.getTime() - d.getTime()) / 60000);
  if (minuten < 1) return "gerade eben";
  if (minuten < 60) return `vor ${minuten} Min.`;
  if (minuten < 60 * 24 && d.getDate() === jetzt.getDate()) return `vor ${Math.round(minuten / 60)} Std.`;
  const gestern = new Date(jetzt);
  gestern.setDate(jetzt.getDate() - 1);
  if (d.toDateString() === gestern.toDateString()) return "gestern";
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}

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
