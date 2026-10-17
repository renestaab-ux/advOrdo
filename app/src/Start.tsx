import { ReactNode } from "react";

export type StartZiel = "anlegen" | "akte" | "eigene" | "toolbox" | "einstellungen";

// Schlichte Strichsymbole, damit keine Symbolbibliothek nötig ist.
const S = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;
const SYMBOLE: Record<StartZiel, ReactNode> = {
  anlegen: (
    <svg viewBox="0 0 48 48" {...S}>
      <path d="M6 14h14l4 4h18v22H6z" />
      <path d="M24 24v10M19 29h10" />
    </svg>
  ),
  akte: (
    <svg viewBox="0 0 48 48" {...S}>
      <path d="M6 14h14l4 4h18v22H6z" />
      <path d="M14 26h20M14 32h14" />
    </svg>
  ),
  eigene: (
    <svg viewBox="0 0 48 48" {...S}>
      <circle cx="24" cy="17" r="7" />
      <path d="M10 40c1.5-8 7-12 14-12s12.5 4 14 12" />
    </svg>
  ),
  toolbox: (
    <svg viewBox="0 0 48 48" {...S}>
      <rect x="6" y="18" width="36" height="20" rx="2" />
      <path d="M18 18v-5h12v5M6 26h36M21 26v4h6v-4" />
    </svg>
  ),
  einstellungen: (
    <svg viewBox="0 0 48 48" {...S}>
      <circle cx="24" cy="24" r="6" />
      <path d="M24 6v6M24 36v6M6 24h6M36 24h6M11.3 11.3l4.2 4.2M32.5 32.5l4.2 4.2M11.3 36.7l4.2-4.2M32.5 15.5l4.2-4.2" />
    </svg>
  ),
};

const KACHELN: { ziel: StartZiel; titel: string; text: string; bald?: boolean }[] = [
  { ziel: "anlegen", titel: "Akte anlegen", text: "Neues Mandat mit Bezeichnung anlegen" },
  { ziel: "akte", titel: "Mit Akte arbeiten", text: "Dokumente, Suche, Vergleich und Analyse" },
  { ziel: "eigene", titel: "Eigene Daten", text: "Kanzleidaten", bald: true },
  { ziel: "toolbox", titel: "Toolbox", text: "Verzugszinsen- und Fristenrechner, eigenes Fenster" },
  { ziel: "einstellungen", titel: "Einstellungen", text: "Sprachmodell und externe KI" },
];

/** Startbildschirm nach Renés Skizze: große Kacheln für die Einstiege. */
export default function Start({ onWahl }: { onWahl: (ziel: StartZiel) => void }) {
  return (
    <div className="start">
      <h1>JuraBox</h1>
      <div className="kacheln">
        {KACHELN.map((k) => (
          <button
            key={k.ziel}
            className="kachel"
            onClick={() => onWahl(k.ziel)}
            disabled={k.bald}
            title={k.bald ? "Folgt in einem späteren Schritt" : undefined}
          >
            <span className="kachel-symbol" aria-hidden>
              {SYMBOLE[k.ziel]}
            </span>
            <span className="kachel-titel">
              {k.titel}
              {k.bald && <span className="bald">bald</span>}
            </span>
            <span className="kachel-text">{k.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
