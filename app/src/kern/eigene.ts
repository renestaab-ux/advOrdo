import { kern } from "./basis";
import { datumDe } from "./toolbox";

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
  /** Fläche hinter dem Logo in Leiste und Startseite: weißer Rahmen (Vorgabe) oder der eingestellte Farbakzent. */
  hintergrund?: LogoHintergrund;
}

export type LogoHintergrund = "weiss" | "akzent";

/** CSS-Klasse für den Logo-Hintergrund; ohne Angabe gilt der weiße Rahmen. */
export function logoGrundKlasse(marke: Marke | null | undefined): string {
  return marke?.hintergrund === "akzent" ? "logo-grund-akzent" : "logo-grund-weiss";
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
