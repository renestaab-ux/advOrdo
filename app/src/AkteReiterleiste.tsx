import { KeyboardEvent, ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";
import Zeichen, { SymbolName } from "./Symbole";
import { menueZiel, reiterAufteilen } from "./reiterleiste";

export interface LeistenReiter<T extends string> {
  id: T;
  titel: string;
  symbol: SymbolName;
  /** Zusatz hinter dem Titel, z. B. die Anzahl der Dokumente oder das Fristzeichen. */
  zusatz?: ReactNode;
  /** Hinweis, der auch am Knopf „Mehr“ erscheint, solange der Reiter im Menü liegt (z. B. „!“ bei Fristen). */
  hinweis?: ReactNode;
}

/** Bis zu dieser Breite brechen die Reiter um (Schrift „Doppelt“, WCAG 1.4.10); dann gibt es kein Menü „Mehr“. */
const UMBRUCH = "(max-width: 760px)";

function useUmbruch(): boolean {
  const [umbruch, setUmbruch] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.(UMBRUCH).matches);
  useEffect(() => {
    const m = window.matchMedia?.(UMBRUCH);
    if (!m?.addEventListener) return;
    const aendern = () => setUmbruch(m.matches);
    m.addEventListener("change", aendern);
    return () => m.removeEventListener("change", aendern);
  }, []);
  return umbruch;
}

/**
 * Reiterleiste der Akte. Passen nicht alle Reiter in die Zeile (Notebook), kommen die hinteren in das Menü
 * „Mehr“; der gewählte Reiter bleibt immer sichtbar. Gemessen wird an einer unsichtbaren Kopie aller Reiter,
 * so stimmt die Aufteilung auch bei anderer Schriftgröße oder ausgeblendeten Symbolen.
 */
export default function AkteReiterleiste<T extends string>({
  reiter,
  aktiv,
  onWahl,
}: {
  reiter: LeistenReiter<T>[];
  aktiv: T | null;
  onWahl: (id: T) => void;
}) {
  const umbruch = useUmbruch();
  const zeile = useRef<HTMLDivElement>(null);
  const mass = useRef<HTMLDivElement>(null);
  const mehrMass = useRef<HTMLButtonElement>(null);
  const mehrKnopf = useRef<HTMLButtonElement>(null);
  const menue = useRef<HTMLDivElement>(null);
  const [aufteilung, setAufteilung] = useState<{ sichtbar: number[]; mehr: number[] }>({
    sichtbar: reiter.map((_, i) => i),
    mehr: [],
  });
  const [offen, setOffen] = useState(false);
  const [markiert, setMarkiert] = useState(0);
  // Nach einer Wahl im Menü bekommt der nun sichtbare Reiter den Fokus.
  const [fokusAuf, setFokusAuf] = useState<T | null>(null);
  const aktivStelle = aktiv == null ? -1 : reiter.findIndex((r) => r.id === aktiv);
  const kennung = reiter.map((r) => r.id).join(",");

  useLayoutEffect(() => {
    const z = zeile.current;
    const m = mass.current;
    if (!z || !m) return;
    function messen() {
      if (!z || !m) return;
      if (umbruch) {
        setAufteilung({ sichtbar: reiter.map((_, i) => i), mehr: [] });
        return;
      }
      const knoepfe = Array.from(m.querySelectorAll<HTMLElement>(".akte-reiter-knopf:not(.mehr)"));
      const abstand = parseFloat(getComputedStyle(m).columnGap || "0") || 0;
      // Jeder Reiter mit dem Abstand zum nächsten; ein Pixel Reserve gegen Rundung.
      const breiten = knoepfe.map((k) => k.getBoundingClientRect().width + abstand + 1);
      const stil = getComputedStyle(z);
      const innen = z.clientWidth - (parseFloat(stil.paddingLeft) || 0) - (parseFloat(stil.paddingRight) || 0);
      const mehrBreite = (mehrMass.current?.getBoundingClientRect().width ?? 90) + abstand;
      const neu = reiterAufteilen(breiten, innen, mehrBreite, aktivStelle);
      setAufteilung((alt) =>
        alt.sichtbar.join() === neu.sichtbar.join() && alt.mehr.join() === neu.mehr.join() ? alt : neu,
      );
    }
    messen();
    if (typeof ResizeObserver === "undefined") return;
    const beobachter = new ResizeObserver(messen);
    beobachter.observe(z);
    beobachter.observe(m);
    return () => beobachter.disconnect();
    // reiter wird über kennung verglichen; Zusätze ändern die Breite, die der Beobachter an `mass` sieht.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kennung, aktivStelle, umbruch]);

  const imMenue = aufteilung.mehr.map((i) => reiter[i]).filter(Boolean);

  useEffect(() => {
    if (imMenue.length === 0) setOffen(false);
  }, [imMenue.length]);

  useEffect(() => {
    if (!offen) return;
    function klick(e: MouseEvent) {
      if (!menue.current?.contains(e.target as Node) && !mehrKnopf.current?.contains(e.target as Node)) setOffen(false);
    }
    document.addEventListener("mousedown", klick);
    return () => document.removeEventListener("mousedown", klick);
  }, [offen]);

  useEffect(() => {
    if (!offen) return;
    menue.current?.querySelectorAll<HTMLElement>('[role="menuitem"]')[markiert]?.focus();
  }, [offen, markiert]);

  useEffect(() => {
    if (fokusAuf == null) return;
    zeile.current?.querySelector<HTMLElement>(`[data-reiter="${fokusAuf}"]`)?.focus();
    setFokusAuf(null);
  }, [fokusAuf, aufteilung]);

  function oeffnen(erster: number) {
    setMarkiert(erster);
    setOffen(true);
  }

  function schliessen(fokusZurueck: boolean) {
    setOffen(false);
    if (fokusZurueck) mehrKnopf.current?.focus();
  }

  function waehle(id: T) {
    setOffen(false);
    onWahl(id);
    setFokusAuf(id);
  }

  function knopfTaste(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      oeffnen(0);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      oeffnen(imMenue.length - 1);
    }
  }

  function menueTaste(e: KeyboardEvent<HTMLDivElement>) {
    const ziel = menueZiel(e.key, markiert, imMenue.length);
    if (ziel != null) {
      e.preventDefault();
      setMarkiert(ziel);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      schliessen(true);
    } else if (e.key === "Tab") {
      setOffen(false);
    }
  }

  const knopfInhalt = (r: LeistenReiter<T>) => (
    <>
      <Zeichen name={r.symbol} groesse={16} />
      {r.titel}
      {r.zusatz}
    </>
  );
  const hinweiseImMenue = imMenue.filter((r) => r.hinweis);

  return (
    <div className="akte-reiter-zeile" ref={zeile}>
      <nav className="akte-reiter" role="tablist" aria-label="Bereiche der Akte">
        {aufteilung.sichtbar.map((i) => reiter[i]).filter(Boolean).map((r) => (
          <button
            key={r.id}
            data-reiter={r.id}
            role="tab"
            aria-selected={aktiv === r.id}
            className={aktiv === r.id ? "akte-reiter-knopf aktiv" : "akte-reiter-knopf"}
            onClick={() => onWahl(r.id)}
          >
            {knopfInhalt(r)}
          </button>
        ))}
      </nav>
      {imMenue.length > 0 && (
        <div className="akte-reiter-mehr">
          <button
            ref={mehrKnopf}
            type="button"
            className={offen ? "akte-reiter-knopf mehr offen" : "akte-reiter-knopf mehr"}
            aria-haspopup="menu"
            aria-expanded={offen}
            aria-label={`Weitere Bereiche der Akte: ${imMenue.map((r) => r.titel).join(", ")}`}
            title={imMenue.map((r) => r.titel).join(", ")}
            onClick={() => (offen ? schliessen(false) : oeffnen(0))}
            onKeyDown={knopfTaste}
          >
            Mehr ({imMenue.length})
            {hinweiseImMenue.map((r) => (
              <span key={r.id}>{r.hinweis}</span>
            ))}
            <span aria-hidden>▾</span>
          </button>
          {offen && (
            <div className="akte-reiter-menue" role="menu" aria-label="Weitere Bereiche der Akte" ref={menue} onKeyDown={menueTaste}>
              {imMenue.map((r, i) => (
                <button
                  key={r.id}
                  type="button"
                  role="menuitem"
                  tabIndex={i === markiert ? 0 : -1}
                  className="akte-reiter-menuezeile"
                  onMouseEnter={() => setMarkiert(i)}
                  onClick={() => waehle(r.id)}
                >
                  {knopfInhalt(r)}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {/* Unsichtbare Kopie zum Messen; für Bildschirmleser und Tastatur nicht vorhanden. */}
      <div className="akte-reiter-masshalter" aria-hidden>
      <div className="akte-reiter-mass" ref={mass}>
        {reiter.map((r) => (
          <button key={r.id} type="button" tabIndex={-1} className={aktiv === r.id ? "akte-reiter-knopf aktiv" : "akte-reiter-knopf"}>
            {knopfInhalt(r)}
          </button>
        ))}
        <button ref={mehrMass} type="button" tabIndex={-1} className="akte-reiter-knopf mehr">
          Mehr (00) ! <span>▾</span>
        </button>
      </div>
      </div>
    </div>
  );
}
