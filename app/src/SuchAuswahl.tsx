import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { optionPasst } from "./kern";

/** Ab so vielen Einträgen zeigt das Formular statt eines Dropdowns die Auswahl mit Suchfeld. */
export const SUCHE_AB = 12;

/**
 * Auswahl aus einer langen Liste, etwa der Rechtsanwaltskammern: ein Knopf, der eine Liste mit Suchfeld öffnet. Tippen
 * grenzt die Liste ein („münchen“ findet die Kammer für den OLG-Bezirk München), Pfeiltasten und Eingabe wählen,
 * Escape schließt. Wer auf dem geschlossenen Knopf einfach lostippt, landet mit dem ersten Buchstaben im Suchfeld.
 * Der leere Wert „–“ steht oben und nimmt die Angabe wieder heraus.
 */
export default function SuchAuswahl({
  optionen,
  wert,
  onWahl,
  bezeichnung,
}: {
  optionen: string[];
  wert: string;
  onWahl: (wert: string) => void;
  bezeichnung: string;
}) {
  const [offen, setOffen] = useState(false);
  const [suche, setSuche] = useState("");
  const [markiert, setMarkiert] = useState(0);
  const rahmen = useRef<HTMLDivElement>(null);
  const knopf = useRef<HTMLButtonElement>(null);
  const liste = useRef<HTMLUListElement>(null);

  // Ohne Eingabe steht „–“ (leer) vor allen Einträgen, mit Eingabe nur die Treffer.
  const zeilen = useMemo(
    () => (suche.trim() ? optionen.filter((o) => optionPasst(o, suche)) : ["", ...optionen]),
    [optionen, suche],
  );

  useEffect(() => {
    if (!offen) return;
    const aktuell = zeilen.indexOf(wert);
    setMarkiert(suche.trim() || aktuell < 0 ? 0 : aktuell);
  }, [offen, suche]);

  useEffect(() => {
    liste.current?.querySelector(".markiert")?.scrollIntoView({ block: "nearest" });
  }, [markiert, offen]);

  // Klick außerhalb schließt die Liste.
  useEffect(() => {
    if (!offen) return;
    const zu = (e: MouseEvent) => {
      if (!rahmen.current?.contains(e.target as Node)) schliessen(false);
    };
    document.addEventListener("mousedown", zu);
    return () => document.removeEventListener("mousedown", zu);
  }, [offen]);

  function schliessen(fokus: boolean) {
    setOffen(false);
    setSuche("");
    if (fokus) knopf.current?.focus();
  }

  function nimm(o: string | undefined) {
    if (o === undefined) return;
    onWahl(o);
    schliessen(true);
  }

  function knopfTaste(e: KeyboardEvent) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOffen(true);
    } else if (e.key.length === 1 && e.key !== " " && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      setSuche(e.key);
      setOffen(true);
    }
  }

  function suchTaste(e: KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setMarkiert(Math.min(zeilen.length - 1, markiert + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setMarkiert(Math.max(0, markiert - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      nimm(zeilen[markiert]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      schliessen(true);
    } else if (e.key === "Tab") {
      schliessen(false);
    }
  }

  return (
    <div className="such-auswahl" ref={rahmen}>
      <button
        type="button"
        ref={knopf}
        className="such-auswahl-knopf"
        aria-haspopup="listbox"
        aria-expanded={offen}
        aria-label={`${bezeichnung}: ${wert || "keine Angabe"}`}
        title={wert || undefined}
        onClick={() => (offen ? schliessen(false) : setOffen(true))}
        onKeyDown={knopfTaste}
      >
        <span className="such-auswahl-text">{wert || "–"}</span>
        <span aria-hidden>▾</span>
      </button>
      {offen && (
        <div className="such-auswahl-liste">
          <input
            autoFocus
            type="search"
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
            onKeyDown={suchTaste}
            placeholder="Tippen zum Suchen, z. B. München"
            aria-label={`${bezeichnung} suchen`}
          />
          <ul role="listbox" ref={liste} aria-label={bezeichnung}>
            {zeilen.map((o, i) => (
              <li
                key={o || "leer"}
                role="option"
                aria-selected={o === wert}
                className={`such-auswahl-zeile${i === markiert ? " markiert" : ""}${o ? "" : " leise"}`}
                onMouseEnter={() => setMarkiert(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  nimm(o);
                }}
              >
                {o || "– keine Angabe"}
              </li>
            ))}
            {zeilen.length === 0 && <li className="such-auswahl-titel">Kein Eintrag passt zu „{suche}“.</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
