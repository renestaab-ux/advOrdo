import { ReactNode } from "react";

// Schlichte Strichsymbole, damit keine Symbolbibliothek nötig ist. Alle auf einem 24er-Raster.
const S = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

const PFADE = {
  start: (
    <>
      <path d="M3 11 12 4l9 7" />
      <path d="M5.5 9.5V20h13V9.5" />
      <path d="M10 20v-5h4v5" />
    </>
  ),
  akten: (
    <>
      <path d="M3 7h6l2 2h10v10H3z" />
      <path d="M7 13h10M7 16h7" />
    </>
  ),
  akteNeu: (
    <>
      <path d="M3 7h6l2 2h10v10H3z" />
      <path d="M12 11.5v6M9 14.5h6" />
    </>
  ),
  beteiligte: (
    <>
      <circle cx="9" cy="8.5" r="3.2" />
      <path d="M3 19.5c.7-3.6 3-5.5 6-5.5s5.3 1.9 6 5.5" />
      <path d="M15.5 5.6a3.2 3.2 0 0 1 0 6M17.5 14.4c1.8.6 3 2.3 3.5 5.1" />
    </>
  ),
  suche: (
    <>
      <circle cx="10.5" cy="10.5" r="6" />
      <path d="m15 15 5.5 5.5" />
    </>
  ),
  gesetze: (
    <>
      <path d="M14.5 5.2c-.6-1-1.6-1.5-2.8-1.5-1.7 0-3 1-3 2.5 0 3.4 6.6 2.9 6.6 6.6 0 1.6-1.4 2.7-3.3 2.7" />
      <path d="M9.5 18.8c.6 1 1.6 1.5 2.8 1.5 1.7 0 3-1 3-2.5 0-3.4-6.6-2.9-6.6-6.6 0-1.6 1.4-2.7 3.3-2.7" />
    </>
  ),
  rechtsprechung: (
    <>
      <path d="M12 4v16M7 20h10M5 7h14" />
      <path d="M5 7 2.5 13a2.5 2.5 0 0 0 5 0zM19 7l-2.5 6a2.5 2.5 0 0 0 5 0z" />
    </>
  ),
  einstellungen: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </>
  ),
  toolbox: (
    <>
      <rect x="3" y="8" width="18" height="11" rx="1.5" />
      <path d="M9 8V5.5h6V8M3 12.5h18M10.5 12.5v2h3v-2" />
    </>
  ),
  eigene: (
    <>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 20c.8-4 3.5-6 7-6s6.2 2 7 6" />
    </>
  ),
  dokumente: (
    <>
      <path d="M6 3h8l4 4v14H6z" />
      <path d="M14 3v4h4M9 12h6M9 15.5h6" />
    </>
  ),
  vergleich: (
    <>
      <rect x="3" y="4" width="7.5" height="16" rx="1" />
      <rect x="13.5" y="4" width="7.5" height="16" rx="1" />
      <path d="M5.5 9h2.5M16 9h2.5M5.5 13h2.5M16 13h2.5" />
    </>
  ),
  analyse: (
    <>
      <path d="M10 4.5 11.6 9 16 10.5 11.6 12 10 16.5 8.4 12 4 10.5 8.4 9z" />
      <path d="M17.5 14.5 18.3 16.7 20.5 17.5 18.3 18.3 17.5 20.5 16.7 18.3 14.5 17.5 16.7 16.7z" />
    </>
  ),
  chat: (
    <>
      <path d="M4 5h16v11H9l-5 4z" />
      <path d="M8 9.5h8M8 12.5h5" />
    </>
  ),
  stammdaten: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="1.5" />
      <path d="M8 9h8M8 12.5h8M8 16h5" />
    </>
  ),
  zurueck: <path d="M15 5 8 12l7 7" />,
  einklappen: (
    <>
      <path d="M4 4v16" />
      <path d="M15 6 9 12l6 6" />
    </>
  ),
  ausklappen: (
    <>
      <path d="M4 4v16" />
      <path d="m10 6 6 6-6 6" />
    </>
  ),
  filter: <path d="M4 5h16l-6 7.5V19l-4-2v-4.5z" />,
} satisfies Record<string, ReactNode>;

export type SymbolName = keyof typeof PFADE;

/** Ein Symbol in Textgröße; für Knöpfe ohne Text bitte ein title oder aria-label am Knopf setzen. */
export default function Zeichen({ name, groesse = 20 }: { name: SymbolName; groesse?: number }) {
  return (
    <svg className="symbol" viewBox="0 0 24 24" width={groesse} height={groesse} aria-hidden {...S}>
      {PFADE[name]}
    </svg>
  );
}
