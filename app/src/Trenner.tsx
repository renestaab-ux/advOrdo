import { PointerEvent as ReactPointerEvent, RefObject, useRef } from "react";
import { trennerSchritt } from "./barrierefrei";

/**
 * Verschiebbare Trennlinie vor einer Seitenleiste rechts. Ziehen mit der Maus; ohne Ziehen (WCAG 2.2, 2.5.7):
 * Einzelklick wechselt zwischen Standard und breit, Doppelklick setzt zurück; mit der Tastatur Pfeil links/rechts
 * (Umschalt: große Schritte), Pos1 = Standard (2.1.1).
 */
export default function Trenner({
  label,
  titel,
  breite,
  min,
  standard,
  rahmen,
  rest,
  onZiehen,
  onSetze,
}: {
  label: string;
  titel: string;
  breite: number;
  min: number;
  standard: number;
  /** Fläche, in der Liste/Text und Seitenleiste stehen; begrenzt die größte Breite. */
  rahmen: RefObject<HTMLElement | null>;
  /** Platz, der links mindestens bleibt. */
  rest: number;
  onZiehen: (e: ReactPointerEvent<HTMLDivElement>) => void;
  onSetze: (breite: number) => void;
}) {
  const start = useRef<number | null>(null);
  const max = () => Math.max(min, Math.round((rahmen.current?.getBoundingClientRect().width ?? 1200) - rest));
  return (
    <div
      className="trenner"
      role="separator"
      tabIndex={0}
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={breite}
      aria-valuemin={min}
      aria-valuemax={max()}
      aria-valuetext={`Seitenleiste ${breite} Pixel breit`}
      title={`${titel}. Klick: breit oder Standard; Doppelklick setzt zurück; Tastatur: Pfeil links/rechts`}
      onPointerDown={(e) => {
        start.current = e.clientX;
        onZiehen(e);
      }}
      onClick={(e) => {
        // Nur ein Klick ohne Bewegung zählt; nach dem Ziehen bleibt die gezogene Breite.
        if (start.current != null && Math.abs(e.clientX - start.current) > 3) return;
        onSetze(Math.min(breite < standard + 150 ? standard + 240 : standard, max()));
      }}
      onDoubleClick={() => onSetze(standard)}
      onKeyDown={(e) => {
        const neu = trennerSchritt(e.key, e.shiftKey, breite, min, max(), standard);
        if (neu == null) return;
        e.preventDefault();
        onSetze(neu);
      }}
    />
  );
}
