import { invoke } from "@tauri-apps/api/core";
import type { AbgleichFundstelle, Einordnung } from "./abgleich";
import type { FristErgebnis, ProzesskostenErgebnis, ZinsErgebnis } from "./toolbox";

// --- Sprachmodell ---------------------------------------------------------------------------------

export interface KiModell {
  name: string;
  groesse: number | null;
  parameter: string | null;
  quantisierung: string | null;
  /** Nur Apple Intelligence: Kontextgröße, wie macOS sie meldet. */
  kontext?: number | null;
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
  schluessel_ort?: "schluesselbund" | "datei";
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

/** Lokales Modell auf einem anderen Rechner per http: Dokumentinhalte gehen unverschlüsselt durchs eigene Netz. */
export function unverschluesseltImNetz(endpunkt: string): boolean {
  let url: URL;
  try {
    url = new URL(endpunkt.trim());
  } catch {
    return false;
  }
  if (url.protocol !== "http:") return false;
  const host = url.hostname.replace(/^\[|\]$/g, "").toLowerCase();
  return !(host === "localhost" || host.endsWith(".localhost") || host === "::1" || /^127\./.test(host));
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
  | "metadaten"
  | "vergleich"
  | "leistungstest";

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
  titel?: string;
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
  /** frage: aus der Frage übernommen; heute: Tag der Frage; annahme: von der App angenommen, Dokumente sagen nichts; akte: aus den Stammdaten. */
  quelle: "frage" | "heute" | "annahme" | "akte" | null;
}

export type ChatBerechnung =
  | { rechner: "zinsen"; ergebnis: ZinsErgebnis | null; eingaben: ChatEingabe[]; fehlt: string[]; fehler: string | null; belegt: boolean; text: string }
  | { rechner: "frist"; ergebnis: FristErgebnis | null; eingaben: ChatEingabe[]; fehlt: string[]; fehler: string | null; belegt: boolean; text: string }
  | { rechner: "prozesskosten"; ergebnis: ProzesskostenErgebnis | null; eingaben: ChatEingabe[]; fehlt: string[]; fehler: string | null; belegt: boolean; text: string };

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
