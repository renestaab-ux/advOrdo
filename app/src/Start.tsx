import { ReactNode, useEffect, useState } from "react";
import { EigeneKurzstand, istDesktop, kern } from "./kern";

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
      <path d="M38.1 20.6 L42.8 21.3 L42.8 26.7 L38.1 27.4 L36.4 31.6 L39.2 35.4 L35.4 39.2 L31.6 36.4 L27.4 38.1 L26.7 42.8 L21.3 42.8 L20.6 38.1 L16.4 36.4 L12.6 39.2 L8.8 35.4 L11.6 31.6 L9.9 27.4 L5.2 26.7 L5.2 21.3 L9.9 20.6 L11.6 16.4 L8.8 12.6 L12.6 8.8 L16.4 11.6 L20.6 9.9 L21.3 5.2 L26.7 5.2 L27.4 9.9 L31.6 11.6 L35.4 8.8 L39.2 12.6 L36.4 16.4Z" />
      <circle cx="24" cy="24" r="6" />
    </svg>
  ),
};

const KACHELN: { ziel: StartZiel; titel: string; text: string; bald?: boolean }[] = [
  { ziel: "anlegen", titel: "Akte anlegen", text: "Neues Mandat mit Bezeichnung anlegen" },
  { ziel: "akte", titel: "Mit Akte arbeiten", text: "Dokumente, Suche, Vergleich und Analyse" },
  { ziel: "eigene", titel: "Eigene Daten", text: "Kanzlei bzw. Unternehmen und Ihre Person" },
  { ziel: "toolbox", titel: "Toolbox", text: "Verzugszinsen- und Fristenrechner, eigenes Fenster" },
  { ziel: "einstellungen", titel: "Einstellungen", text: "Sprachmodell und externe KI" },
];

/** Startbildschirm nach Renés Skizze: große Kacheln für die Einstiege. */
export default function Start({ onWahl, umgebung }: { onWahl: (ziel: StartZiel) => void; umgebung: string | null }) {
  // Stand der Eigenen Daten für die Kachel, z. B. „3 Angaben fehlen“.
  const [profil, setProfil] = useState<EigeneKurzstand | null>(null);
  useEffect(() => {
    if (istDesktop) void kern<EigeneKurzstand>("eigene.kurzstand").then(setProfil, () => setProfil(null));
  }, []);
  return (
    <div className="start">
      <h1>JuraBox</h1>
      {umgebung && (
        <p className="umgebung-zeile">
          Umgebung: <strong>{umgebung}</strong>
        </p>
      )}
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
            {k.ziel === "eigene" && profil && (
              <span className={profil.eingerichtet && profil.fehlend === 0 ? "kachel-stand gut" : "kachel-stand"}>
                {profil.text}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
