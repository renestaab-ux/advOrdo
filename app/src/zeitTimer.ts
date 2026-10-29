import { useCallback, useEffect, useState } from "react";
import { ZEIT_EREIGNIS, ZeitLaufend, istDesktop, kern } from "./kern";

/**
 * Der laufende Timer der Zeiterfassung (höchstens einer je Umgebung) mit sekundengenauer Anzeige.
 * Neu geladen, wenn ein Teil der Oberfläche einen Timer startet oder anhält (``zeitGeaendert``), und jede Minute,
 * damit ein Timer aus einem anderen Fenster auftaucht.
 */
export function useLaufenderTimer(umgebung?: string): { laufend: ZeitLaufend | null; sekunden: number; neu: () => void } {
  const [laufend, setLaufend] = useState<ZeitLaufend | null>(null);
  const [geladen, setGeladen] = useState(0);
  const [jetzt, setJetzt] = useState(() => Date.now());

  const neu = useCallback(() => {
    if (!istDesktop) return;
    void kern<ZeitLaufend | null>("zeit.laufend").then(
      (l) => {
        setLaufend(l);
        setGeladen(Date.now());
        setJetzt(Date.now());
      },
      () => setLaufend(null),
    );
  }, []);

  useEffect(() => {
    neu();
    window.addEventListener(ZEIT_EREIGNIS, neu);
    const t = setInterval(neu, 60_000);
    return () => {
      window.removeEventListener(ZEIT_EREIGNIS, neu);
      clearInterval(t);
    };
  }, [neu, umgebung]);

  useEffect(() => {
    if (!laufend) return;
    const t = setInterval(() => setJetzt(Date.now()), 1000);
    return () => clearInterval(t);
  }, [laufend]);

  const sekunden = laufend ? laufend.sekunden + Math.max(0, Math.floor((jetzt - geladen) / 1000)) : 0;
  return { laufend, sekunden, neu };
}
