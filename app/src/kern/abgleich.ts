import type { KiAuftrag, KiWidersprueche } from "./ki";

// --- Abgleich ------------------------------------------------------------------------------------

/** "verschieden": Die Werte weichen ab, meinen laut KI aber Verschiedenes (nur beim Vergleich mit KI). */
export type AbgleichStatus = "abweichend" | "verschieden" | "uebereinstimmend" | "einzeln";
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
  /** Nur beim Vergleich mit KI: worauf sich der Wert laut KI bezieht, Haltung des Verfassers, wer ihn fand. */
  bezug?: string;
  haltung?: string;
  quelle?: "ki" | "regel";
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
  /** Nur beim Vergleich mit KI: Merkmal von der KI gebildet oder nur von den Regeln gefunden. */
  quelle?: "ki" | "regel";
  /** Nur beim Vergleich mit KI: Einschätzung der Abweichung durch das Modell. */
  erklaerung?: string;
  /** Möglicher Zahlendreher zwischen zwei Werten, mit der Häufigkeit beider Werte im Text; sonst leer. */
  hinweis?: string;
}

export interface Abgleich {
  dokumente: number;
  merkmale: AbgleichMerkmal[];
  zaehlung: Partial<Record<AbgleichStatus, number>> & Record<"abweichend" | "uebereinstimmend" | "einzeln", number>;
}

/** Vergleich mit KI: Aufbau wie der regelbasierte Abgleich, dazu Herkunft und inhaltliche Widersprüche. */
export interface KiVergleich extends Abgleich {
  quelle: "ki";
  modell: string;
  erstellt_am: string;
  gespeichert: boolean;
  unvollstaendig: boolean;
  luecken_dokumente: { dateiname: string; absaetze: string[] }[];
  ki_dokumente: { dokument_id: number; dateiname: string; werte: number; verworfen: number; bestritten: number }[];
  inhaltlich: KiWidersprueche;
}

/** Antwort von ki.vergleich. */
export type KiVergleichStand =
  | { status: "aus"; abgeschaltet: boolean; hinweis?: string }
  | { status: "fertig"; ergebnis: KiVergleich }
  | { status: "laeuft"; auftrag: KiAuftrag }
  | { status: "belegt"; aufgabe: string | null }
  | { status: "extern" };

export const EINORDNUNG_TEXT: Record<Einordnung, string> = {
  im_dokument: "im selben Dokument",
  innerhalb_partei: "innerhalb einer Partei",
  zwischen_parteien: "zwischen den Beteiligten",
  partei_unbekannt: "Beteiligte unbekannt (Dokumente ohne Tag)",
};

/** Kurzfassung des Ergebnisses, z. B. "7 mögliche Abweichungen, 4 Übereinstimmungen in 9 Dokumenten". */
export function abgleichZusammenfassung(a: Pick<Abgleich, "dokumente" | "zaehlung">): string {
  const n = (zahl: number, eins: string, mehr: string) => `${zahl} ${zahl === 1 ? eins : mehr}`;
  const verschieden = a.zaehlung.verschieden
    ? `${n(a.zaehlung.verschieden, "Abweichung", "Abweichungen")} laut KI zu Verschiedenem, `
    : "";
  return (
    `${n(a.zaehlung.abweichend, "mögliche Abweichung", "mögliche Abweichungen")}, ` +
    verschieden +
    `${n(a.zaehlung.uebereinstimmend, "Übereinstimmung", "Übereinstimmungen")} ` +
    `in ${n(a.dokumente, "Dokument", "Dokumenten")}`
  );
}
