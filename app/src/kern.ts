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
}

/** Anzeige einer Akte in Auswahllisten: „12/26 · Brückner ./. Autohaus“; ohne Aktenzeichen nur der Name. */
export function akteTitel(a: Pick<Akte, "name" | "aktenzeichen">): string {
  return a.aktenzeichen ? `${a.aktenzeichen} · ${a.name}` : a.name;
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
  rollen?: { text: string; gruppe: "eigene" | "gegen" | "gericht" | "neutral" | "funktion" }[];
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
}

export type DatumQuelle = "dokument" | "word" | "datei" | "unbekannt";

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
  zitat: string | null;
  gericht: string;
  aktenzeichen: string | null;
  datum: string | null;
  quelle: UrteilQuelle;
  herkunft: string | null;
  dateiname: string;
  format: string;
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
  aktiv: "lokal" | "extern";
  titel: string | null;
  modell: string;
}

export type KiAufgabe = "zusammenfassung_dokument" | "zusammenfassung_akte" | "widersprueche" | "chronologie" | "chat";

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
  /** tatsache: aus den Dokumenten; einschaetzung: Würdigung des Modells; hinweis: etwa „steht nicht in der Akte“. */
  art: "tatsache" | "einschaetzung" | "hinweis";
  status: "belegt" | "ohne_beleg" | "hinweis";
  fundstellen: KiFundstelle[];
}

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
