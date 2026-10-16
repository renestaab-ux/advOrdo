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

/** Eine Seite des Original-PDFs, vom Kern als PNG gerendert. */
export interface Seitenbild {
  seite: number;
  seiten: number;
  breite: number;
  hoehe: number;
  bild: string;
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
  entscheidung: { gericht: string; spruchkoerper: string | null; datum: string | null; aktenzeichen: string; link: string | null } | null;
  fundstellen: (Fundstelle & { rn_zitiert: number | null; rn_vorhanden: boolean | null })[];
  /** Volltext, der zur Akte vorliegt (selbst ergänzt oder geladen). */
  urteil: UrteilInfo | null;
  /** Höchste Randnummer im Volltext, wenn einer vorliegt. */
  rn_hoechste: number | null;
}

/** Eine Entscheidung im Volltext zur Akte, z. B. ein PDF-Ausdruck aus juris. */
export interface UrteilInfo {
  id: number;
  zitat: string | null;
  gericht: string;
  aktenzeichen: string | null;
  datum: string | null;
  quelle: "manuell" | "rii";
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
  quellen: { quelle: "manuell" | "rii"; herkunft: string | null; anzahl: number }[];
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

export interface KiStatus {
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

export type KiAufgabe = "zusammenfassung_dokument" | "zusammenfassung_akte" | "widersprueche" | "chronologie";

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
