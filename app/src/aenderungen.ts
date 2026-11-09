/**
 * Abgleich zwischen den Fenstern der App (Hauptfenster und Arbeitsfenster der Akten).
 *
 * Alle Fenster benutzen denselben Kern, aber jedes hält seine Listen selbst. Ändert ein Fenster Notizen,
 * Anmerkungen oder Lesezeichen, meldet ``kern()`` das den anderen Fenstern (Tauri-Ereignis), und die betroffenen
 * Ansichten laden neu. Das eigene Fenster lädt ohnehin selbst nach und ignoriert die Meldung.
 */
import { emit, listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useEffect, useRef } from "react";

export type Bereich = "notizen" | "anmerkungen" | "lesezeichen";

export const EREIGNIS = "daten-geaendert";

interface Meldung {
  bereich: Bereich;
  von: string;
}

/** Welcher Bereich sich durch einen Aufruf des Kerns ändert; null bei lesenden Aufrufen. */
export function geaenderterBereich(methode: string): Bereich | null {
  if (/^akten\.notiz_/.test(methode)) return "notizen";
  if (/^anmerkungen\.(anlegen|anlegen_seite|aendern|loeschen|bedeutungen_setzen)$/.test(methode)) return "anmerkungen";
  if (/^lesezeichen\.(?!liste$|inhalt$)/.test(methode)) return "lesezeichen";
  return null;
}

const istDesktop = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

function eigenesFenster(): string {
  return getCurrentWindow().label;
}

/** Nach einem erfolgreichen Aufruf: den anderen Fenstern melden, wenn er etwas geändert hat. */
export async function aenderungMelden(methode: string): Promise<void> {
  const bereich = geaenderterBereich(methode);
  if (!bereich || !istDesktop) return;
  try {
    await emit(EREIGNIS, { bereich, von: eigenesFenster() } satisfies Meldung);
  } catch {
    // Ohne Ereignisse sehen die anderen Fenster die Änderung beim nächsten Öffnen.
  }
}

/** Ruft ``neuLaden`` auf, wenn ein anderes Fenster etwas in einem der ``bereiche`` geändert hat. */
export function useFremdeAenderung(bereiche: Bereich[], neuLaden: () => void) {
  const fn = useRef(neuLaden);
  fn.current = neuLaden;
  const schluessel = bereiche.join(",");
  useEffect(() => {
    if (!istDesktop) return;
    let aus: (() => void) | null = null;
    let beendet = false;
    void listen<Meldung>(EREIGNIS, (e) => {
      if (e.payload.von !== eigenesFenster() && schluessel.split(",").includes(e.payload.bereich)) fn.current();
    }).then((f) => {
      if (beendet) f();
      else aus = f;
    });
    return () => {
      beendet = true;
      aus?.();
    };
  }, [schluessel]);
}
