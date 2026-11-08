/**
 * Offene Bearbeitungen, nach denen die App vor dem Beenden fragt (Fenster schließen, ⌘Q, „advOrdo beenden“).
 *
 * Formulare melden sich hier an, sobald darin etwas eingegeben wurde, und ab, wenn gespeichert, abgebrochen oder
 * das Formular geschlossen wurde. Die Rückfrage selbst steht in ``TimerHinweise.tsx``.
 */
import { FormEvent, useEffect, useRef } from "react";

export type Bearbeitung = {
  /** Was offen ist, für die Rückfrage, z. B. „Beteiligter“ oder „Stammdaten der Akte“. */
  was: string;
  /** Speichert die Eingaben; false, wenn das Speichern scheitert. Fehlt, wenn nur Verwerfen oder Zurück geht. */
  speichern?: () => Promise<boolean>;
};

const offen = new Map<symbol, Bearbeitung>();

export function offeneBearbeitungen(): Bearbeitung[] {
  return [...offen.values()];
}

/** Für Tests. */
export function bearbeitungenLeeren() {
  offen.clear();
}

/**
 * Meldet eine Bearbeitung an, solange ``aktiv`` gilt, und beim Schließen der Komponente ab. Für Formulare, die
 * selbst wissen, ob etwas ungespeichert ist (Stammdaten).
 */
export function useUngespeichert(aktiv: boolean, was: string, speichern?: () => Promise<boolean>) {
  const schluessel = useRef(Symbol(was));
  const speichernRef = useRef(speichern);
  speichernRef.current = speichern;
  useEffect(() => {
    const s = schluessel.current;
    if (!aktiv) return;
    offen.set(s, { was, speichern: speichernRef.current && (() => speichernRef.current!()) });
    return () => {
      offen.delete(s);
    };
  }, [aktiv, was]);
}

/**
 * Für ein gewöhnliches Formular: Die erste Eingabe meldet die Bearbeitung an, Absenden und Schließen melden sie ab.
 * ``formular`` kommt als Eigenschaften an das ``<form>``.
 */
export function useBearbeitung(was: string) {
  const schluessel = useRef(Symbol(was));
  useEffect(() => {
    const s = schluessel.current;
    return () => {
      offen.delete(s);
    };
  }, []);
  return {
    formular: {
      onInput: () => {
        if (!offen.has(schluessel.current)) offen.set(schluessel.current, { was });
      },
      onSubmitCapture: (_e: FormEvent) => {
        offen.delete(schluessel.current);
      },
    },
    /** Nach Verwerfen, wenn das Formular offen bleibt (etwa ein geleertes Eingabefeld). */
    erledigt: () => {
      offen.delete(schluessel.current);
    },
  };
}
