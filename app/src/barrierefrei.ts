import { RefObject, useEffect, useRef } from "react";

/** Hilfen für Tastatur und Bildschirmleser, die immer gelten (Stufe 2 des barrierefreien Modus). */

/** Alt + Ziffer springt in einen Bereich der Leiste (1 = Start …). Gibt den Index zurück oder null. */
export function bereichAusTaste(
  e: { altKey: boolean; ctrlKey: boolean; metaKey: boolean; shiftKey: boolean; code: string },
  anzahl: number,
): number | null {
  if (!e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return null;
  // Nach der Taste, nicht nach dem Zeichen: unter macOS liefert Wahl + 1 sonst „¡“.
  const m = /^(?:Digit|Numpad)([1-9])$/.exec(e.code);
  if (!m) return null;
  const i = Number(m[1]) - 1;
  return i < anzahl ? i : null;
}

const FOKUSSIERBAR =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Bedienbare Elemente in der Reihenfolge der Tabulatortaste. */
export function fokussierbare(wurzel: HTMLElement): HTMLElement[] {
  return Array.from(wurzel.querySelectorAll<HTMLElement>(FOKUSSIERBAR)).filter((el) => !el.closest("[hidden]"));
}

/** Wohin Tab bzw. Umschalt + Tab im Dialog führt: am Ende wieder zum Anfang und umgekehrt; null = wie üblich. */
export function naechsterImKreis(position: number, anzahl: number, rueckwaerts: boolean): number | null {
  if (anzahl === 0) return null;
  if (position < 0) return rueckwaerts ? anzahl - 1 : 0;
  if (rueckwaerts && position === 0) return anzahl - 1;
  if (!rueckwaerts && position === anzahl - 1) return 0;
  return null;
}

/**
 * Dialog per Tastatur: Fokus beim Öffnen hinein (sofern nicht schon drin, z. B. per autoFocus), Tab bleibt im Dialog,
 * Escape schließt (wenn `onSchliessen` gesetzt ist), beim Schließen springt der Fokus dorthin zurück, wo er vorher war.
 */
export function useDialog(ref: RefObject<HTMLElement | null>, onSchliessen?: () => void) {
  const schliessen = useRef(onSchliessen);
  schliessen.current = onSchliessen;
  // Schon beim ersten Zeichnen merken, bevor autoFocus den Fokus in den Dialog zieht.
  const vorherRef = useRef<HTMLElement | null | undefined>(undefined);
  if (vorherRef.current === undefined && typeof document !== "undefined")
    vorherRef.current = document.activeElement as HTMLElement | null;
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const vorher = vorherRef.current;
    if (!dialog.contains(document.activeElement)) (fokussierbare(dialog)[0] ?? dialog).focus();

    function taste(e: KeyboardEvent) {
      if (e.key === "Escape" && schliessen.current) {
        e.preventDefault();
        e.stopPropagation();
        schliessen.current();
      } else if (e.key === "Tab" && dialog) {
        const liste = fokussierbare(dialog);
        const ziel = naechsterImKreis(liste.indexOf(document.activeElement as HTMLElement), liste.length, e.shiftKey);
        if (ziel != null) {
          e.preventDefault();
          liste[ziel].focus();
        }
      }
    }
    dialog.addEventListener("keydown", taste);
    return () => {
      dialog.removeEventListener("keydown", taste);
      if (vorher && document.contains(vorher)) vorher.focus();
    };
    // Nur beim Öffnen und Schließen; das jeweils aktuelle onSchliessen steht in `schliessen`.
  }, [ref]);
}
