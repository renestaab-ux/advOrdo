import type { ZitatStatus } from "./akten";
import type { Fundstelle } from "./dokumente";

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
  urteile: ({
    sha256: string;
    fundstellen: { nr: number; rn: number | null; ausschnitt: { vor: string; treffer: string; nach: string } }[];
  } & Pick<UrteilInfo, "id" | "gericht" | "aktenzeichen" | "datum" | "kopf">)[];
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
