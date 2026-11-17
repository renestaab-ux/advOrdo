import { getCurrentWebview } from "@tauri-apps/api/webview";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { istDesktop } from "./kern";

/** Darstellung der Oberfläche je Gerät: Hell/Dunkel, Farbakzent und Schriftgröße (Einstellungen → Allgemeines). */
export type Thema = "system" | "hell" | "dunkel";
export type Akzent = "blau" | "petrol" | "gruen" | "bordeaux" | "violett" | "graphit";
/** Leiste links: in der dunklen Nuance des Farbakzents oder weiß (im Dunkelmodus neutral) mit Farbakzent. */
export type Leiste = "farbig" | "weiss";

/** Einzelne Hilfen des barrierefreien Modus; der Hauptschalter setzt alle auf einmal. */
export interface Barrierefreiheit {
  /** Hoher Kontrast: kräftige Schrift- und Randfarben, unterstrichene Verweise, Ampeln auch als Form. */
  kontrast: boolean;
  /** Mehr Zeilenabstand und größere Klickflächen. */
  abstaende: boolean;
  /** Breiter, auffälliger Rahmen um das Element, auf dem die Tastatur steht. */
  fokus: boolean;
  /** Keine Animationen und kein weiches Blättern. */
  bewegung: boolean;
}

export interface Darstellung {
  thema: Thema;
  akzent: Akzent;
  leiste: Leiste;
  /** Faktor für die ganze Oberfläche, 1 = normal. */
  schrift: number;
  barrierefrei: Barrierefreiheit;
}

export type Hilfe = keyof Barrierefreiheit;

export const HILFEN: { id: Hilfe; titel: string; erklaerung: string }[] = [
  {
    id: "kontrast",
    titel: "Hoher Kontrast",
    erklaerung: "Kräftige Schrift- und Randfarben ohne zarte Grautöne, Verweise unterstrichen, Ampeln zusätzlich als Form.",
  },
  {
    id: "abstaende",
    titel: "Mehr Abstand und größere Klickflächen",
    erklaerung: "Größerer Zeilenabstand, Knöpfe und Felder mindestens 36 Pixel hoch.",
  },
  {
    id: "fokus",
    titel: "Deutlicher Tastaturrahmen",
    erklaerung: "Ein breiter, farbiger Rahmen zeigt immer, wo die Tastatur gerade steht.",
  },
  {
    id: "bewegung",
    titel: "Bewegung reduzieren",
    erklaerung: "Keine Animationen, kein weiches Blättern. Gilt ohnehin, wenn das Betriebssystem Animationen abschaltet.",
  },
];

/** Schriftgröße, die der Hauptschalter mindestens einstellt. */
export const SCHRIFT_BARRIEREFREI = 1.25;

export const BARRIEREFREI_AUS: Barrierefreiheit = { kontrast: false, abstaende: false, fokus: false, bewegung: false };
export const BARRIEREFREI_AN: Barrierefreiheit = { kontrast: true, abstaende: true, fokus: true, bewegung: true };

/** Der Hauptschalter gilt als an, sobald alle Hilfen an sind. */
export function modusAn(b: Barrierefreiheit): boolean {
  return HILFEN.every((h) => b[h.id]);
}

/** Hauptschalter: an schaltet alle Hilfen ein und vergrößert die Schrift mindestens auf „Sehr groß“; aus schaltet nur die Hilfen ab. */
export function modusSetzen(d: Darstellung, an: boolean): Darstellung {
  if (!an) return { ...d, barrierefrei: { ...BARRIEREFREI_AUS } };
  return { ...d, barrierefrei: { ...BARRIEREFREI_AN }, schrift: Math.max(d.schrift, SCHRIFT_BARRIEREFREI) };
}

export const THEMEN: { id: Thema; titel: string }[] = [
  { id: "hell", titel: "Hell" },
  { id: "dunkel", titel: "Dunkel" },
  { id: "system", titel: "Systemstandard" },
];

/** Zwei Nuancen je Farbe: die dunkle für Leiste und Kopfband, die helle für Knöpfe und Hervorhebungen. */
export type Nuancen = { dunkel: string; hell: string };

// Die Farben selbst stehen in styles/grundlagen.css (--leiste und --knopf); hier nur das zweifarbige Muster
// für die Auswahl, je ein Paar für die helle und die dunkle Oberfläche.
export const AKZENTE: { id: Akzent; titel: string; hell: Nuancen; dunkel: Nuancen }[] = [
  { id: "blau", titel: "Blau", hell: { dunkel: "#1b3550", hell: "#27507a" }, dunkel: { dunkel: "#142536", hell: "#3a6794" } },
  { id: "petrol", titel: "Petrol", hell: { dunkel: "#163f45", hell: "#22636b" }, dunkel: { dunkel: "#0f2c30", hell: "#2f7178" } },
  { id: "gruen", titel: "Grün", hell: { dunkel: "#21422a", hell: "#346b42" }, dunkel: { dunkel: "#152b1b", hell: "#3d7449" } },
  { id: "bordeaux", titel: "Bordeaux", hell: { dunkel: "#561c28", hell: "#84303f" }, dunkel: { dunkel: "#3a141c", hell: "#8a3a4a" } },
  { id: "violett", titel: "Violett", hell: { dunkel: "#3a2c57", hell: "#5c4787" }, dunkel: { dunkel: "#251c3a", hell: "#5f4a8c" } },
  { id: "graphit", titel: "Graphit", hell: { dunkel: "#2a2e33", hell: "#474d55" }, dunkel: { dunkel: "#1f2226", hell: "#555c65" } },
];

export const LEISTEN: { id: Leiste; titel: string }[] = [
  { id: "farbig", titel: "Farbig" },
  { id: "weiss", titel: "Weiß mit Farbakzent" },
];

/**
 * Hintergrund für das Farbmuster: links die Leiste (dunkle Nuance oder weiß), rechts die helle Nuance, hart geteilt.
 * Bei weißer Leiste im Dunkelmodus steht links die neutrale Fläche der dunklen Oberfläche.
 */
export function musterHintergrund(n: Nuancen, leiste: Leiste = "farbig", dunkel = false): string {
  const links = leiste === "weiss" ? (dunkel ? "#242528" : "#ffffff") : n.dunkel;
  return `linear-gradient(90deg, ${links} 50%, ${n.hell} 50%)`;
}

export const SCHRIFTGROESSEN: { wert: number; titel: string }[] = [
  { wert: 0.9, titel: "Klein" },
  { wert: 1, titel: "Normal" },
  { wert: 1.1, titel: "Groß" },
  { wert: 1.25, titel: "Sehr groß" },
  { wert: 1.5, titel: "Extra groß" },
  // WCAG 1.4.4: Text bis 200 % vergrößerbar, ohne dass Inhalt oder Funktion verloren geht.
  { wert: 2, titel: "Doppelt" },
];

export const VORGABE: Darstellung = { thema: "system", akzent: "blau", leiste: "farbig", schrift: 1, barrierefrei: BARRIEREFREI_AUS };

const SCHLUESSEL = "darstellung";

/** Liest die gespeicherte Darstellung; Unbekanntes fällt auf die Vorgabe zurück. */
export function darstellungLesen(roh?: string | null): Darstellung {
  let d: Partial<Darstellung> = {};
  try {
    d = JSON.parse(roh === undefined ? (localStorage.getItem(SCHLUESSEL) ?? "{}") : (roh ?? "{}")) ?? {};
  } catch {
    // Ohne Speicher oder bei kaputtem Eintrag gilt die Vorgabe.
  }
  return {
    thema: THEMEN.some((t) => t.id === d.thema) ? d.thema! : VORGABE.thema,
    akzent: AKZENTE.some((a) => a.id === d.akzent) ? d.akzent! : VORGABE.akzent,
    leiste: LEISTEN.some((l) => l.id === d.leiste) ? d.leiste! : VORGABE.leiste,
    schrift: SCHRIFTGROESSEN.some((s) => s.wert === d.schrift) ? d.schrift! : VORGABE.schrift,
    barrierefrei: barrierefreiLesen(d.barrierefrei),
  };
}

function barrierefreiLesen(roh: unknown): Barrierefreiheit {
  const b = (roh && typeof roh === "object" ? roh : {}) as Record<string, unknown>;
  const neu = { ...BARRIEREFREI_AUS };
  for (const h of HILFEN) neu[h.id] = b[h.id] === true;
  return neu;
}

export function darstellungSpeichern(d: Darstellung) {
  try {
    localStorage.setItem(SCHLUESSEL, JSON.stringify(d));
  } catch {
    // Ohne Speicher gilt die Darstellung nur bis zum Neustart.
  }
  darstellungAnwenden(d);
}

const systemDunkel = typeof window !== "undefined" ? window.matchMedia?.("(prefers-color-scheme: dark)") : undefined;
// Benutzereinstellungen des Systems übernehmen (EN 301 549, 11.7): „Kontrast erhöhen“ (macOS) bzw. Kontrastdesign.
const systemKontrast = typeof window !== "undefined" ? window.matchMedia?.("(prefers-contrast: more)") : undefined;

/** Ob das Betriebssystem mehr Kontrast verlangt; dann gilt „Hoher Kontrast“ auch ohne Schalter. */
export function systemWillKontrast(): boolean {
  return !!systemKontrast?.matches;
}
let aktuell: Darstellung = VORGABE;

/** Thema der Titelleiste für Tauri: „light“, „dark“ oder null (wie das System). */
export function fensterThema(d: Darstellung): "light" | "dark" | null {
  return d.thema === "system" ? null : d.thema === "dunkel" ? "dark" : "light";
}

/**
 * Zuletzt an das Fenster gegebenes Thema. Die Toolbox bekommt es schon beim Anlegen (`thema=` in der Adresse);
 * ein zweites Setzen direkt danach ließe unter Windows die Titelleiste schwarz und ohne sichtbare Knöpfe.
 */
let gesetztesThema: "light" | "dark" | null | undefined = (() => {
  const t = typeof location !== "undefined" ? new URLSearchParams(location.search).get("thema") : null;
  return t === "light" || t === "dark" ? t : t === "system" ? null : undefined;
})();

/** Ob die Oberfläche gerade dunkel ist; bei „Systemstandard“ nach der Einstellung des Betriebssystems. */
export function istDunkel(d: Darstellung = aktuell): boolean {
  return d.thema === "dunkel" || (d.thema === "system" && !!systemDunkel?.matches);
}

/** Setzt Farben und Thema an der Seite und die Vergrößerung des Fensters (wie Strg + Plus, aber dauerhaft). */
export function darstellungAnwenden(d: Darstellung) {
  aktuell = d;
  const wurzel = document.documentElement;
  wurzel.dataset.thema = istDunkel(d) ? "dunkel" : "hell";
  wurzel.dataset.akzent = d.akzent;
  wurzel.dataset.leiste = d.leiste;
  // Jede Hilfe als eigenes Merkmal an <html>; styles.css hängt die Regeln daran.
  for (const h of HILFEN) {
    if (d.barrierefrei[h.id] || (h.id === "kontrast" && systemWillKontrast())) wurzel.dataset[h.id] = "an";
    else delete wurzel.dataset[h.id];
  }
  if (istDesktop) {
    // Auch Titelleiste und Bedienelemente des Systems folgen der Wahl; null heißt „wie das System“.
    const thema = fensterThema(d);
    if (thema !== gesetztesThema) {
      gesetztesThema = thema;
      void getCurrentWindow()
        .setTheme(thema)
        .catch(() => undefined);
    }
    void getCurrentWebview()
      .setZoom(d.schrift)
      .catch(() => undefined);
  } else {
    // Nur in der Browser-Vorschau; die Desktop-App vergrößert über das Fenster, damit das Layout richtig umbricht.
    wurzel.style.setProperty("zoom", String(d.schrift));
  }
}

/** Beim Start jedes Fensters: anwenden und Änderungen aus anderen Fenstern (Toolbox) und vom System übernehmen. */
export function darstellungStarten() {
  darstellungAnwenden(darstellungLesen());
  window.addEventListener("storage", (e) => {
    if (e.key === SCHLUESSEL) darstellungAnwenden(darstellungLesen(e.newValue));
  });
  systemDunkel?.addEventListener?.("change", () => darstellungAnwenden(aktuell));
  systemKontrast?.addEventListener?.("change", () => darstellungAnwenden(aktuell));
}

/** Ob Bewegung vermieden werden soll: Schalter in advOrdo oder Einstellung des Betriebssystems. */
export function bewegungVermeiden(): boolean {
  return aktuell.barrierefrei.bewegung || !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}
