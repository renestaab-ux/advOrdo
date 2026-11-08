import type { Beteiligung, ZitatStatus } from "./akten";
import type { KiAuftrag } from "./ki";

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
  /** Zahl der Markierungen und Kommentare (Anmerkungen.tsx). */
  anmerkungen?: number;
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
  art: "absatz" | "tabelle" | "fussnote" | "kopfzeile";
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

/** Fundstelle in einem Dokument: Abschnitt, Seite, Randnummer und der Satz, aus dem ein Vorschlag stammt. */
export interface Fundstelle {
  dokument_id: number;
  dateiname: string;
  abschnitt: number;
  seite: number | null;
  rn: number | null;
  text?: string;
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

/** Ergebnis je Datei von `akten.importieren_dateien`: eingelesen (`dokument_id`, `neu`) oder mit `fehler`. */
export interface ImportErgebnisDatei {
  name: string;
  dokument_id?: number;
  neu?: boolean;
  fehler?: string;
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
