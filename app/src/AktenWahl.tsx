import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { Akte, aktePasst, zuletztGeoeffnet } from "./kern";

/** So viele Treffer zeigt die Liste; mehr Akten grenzt man über das Suchfeld ein. */
const HOECHSTENS = 50;

type Zeile = { art: "alle" } | { art: "akte"; akte: Akte } | { art: "titel"; text: string };

function parteien(a: Akte): string {
  const m = a.mandanten.join(", ");
  const g = a.gegner.join(", ");
  return m && g ? `${m} ./. ${g}` : m || g;
}

/**
 * Auswahl „Suchen in“ für die Volltextsuche: ein Knopf, der eine Liste mit Suchfeld öffnet. Ohne Eingabe stehen oben
 * „Alle Akten“ und die zuletzt geöffneten Akten; mit Eingabe die passenden Akten nach Aktenzeichen, Bezeichnung,
 * Parteien oder Gericht. Bedienbar mit Pfeiltasten, Eingabe und Escape. `akteId` null bedeutet „Alle Akten“.
 */
export default function AktenWahl({
  akten,
  akteId,
  onWahl,
}: {
  akten: Akte[];
  akteId: number | null;
  onWahl: (id: number | null) => void;
}) {
  const [offen, setOffen] = useState(false);
  const [suche, setSuche] = useState("");
  const [markiert, setMarkiert] = useState(0);
  const rahmen = useRef<HTMLDivElement>(null);
  const liste = useRef<HTMLUListElement>(null);

  const gewaehlt = akteId == null ? null : akten.find((a) => a.id === akteId) ?? null;

  const { zeilen, weitere } = useMemo(() => {
    const z: Zeile[] = [];
    if (!suche.trim()) {
      z.push({ art: "alle" });
      const zuletzt = zuletztGeoeffnet(akten, 5);
      if (zuletzt.length) {
        z.push({ art: "titel", text: "Zuletzt geöffnet" });
        zuletzt.forEach((a) => z.push({ art: "akte", akte: a }));
      }
      const uebrige = akten.filter((a) => !zuletzt.includes(a));
      if (uebrige.length) {
        z.push({ art: "titel", text: zuletzt.length ? "Weitere Akten" : "Akten" });
        uebrige.slice(0, HOECHSTENS).forEach((a) => z.push({ art: "akte", akte: a }));
      }
      return { zeilen: z, weitere: Math.max(0, uebrige.length - HOECHSTENS) };
    }
    const passend = akten.filter((a) => aktePasst(a, suche));
    passend.slice(0, HOECHSTENS).forEach((a) => z.push({ art: "akte", akte: a }));
    return { zeilen: z, weitere: Math.max(0, passend.length - HOECHSTENS) };
  }, [akten, suche]);

  const waehlbar = zeilen.map((z, i) => (z.art === "titel" ? -1 : i)).filter((i) => i >= 0);

  // Beim Öffnen steht die Markierung auf der aktuellen Wahl, beim Tippen auf dem ersten Treffer.
  useEffect(() => {
    if (!offen) return;
    const aktuell = zeilen.findIndex((z) => (z.art === "alle" ? akteId == null : z.art === "akte" && z.akte.id === akteId));
    setMarkiert(suche.trim() || aktuell < 0 ? waehlbar[0] ?? 0 : aktuell);
  }, [offen, suche]);

  useEffect(() => {
    liste.current?.querySelector(".markiert")?.scrollIntoView({ block: "nearest" });
  }, [markiert, offen]);

  // Klick außerhalb schließt die Liste.
  useEffect(() => {
    if (!offen) return;
    const zu = (e: MouseEvent) => {
      if (!rahmen.current?.contains(e.target as Node)) setOffen(false);
    };
    document.addEventListener("mousedown", zu);
    return () => document.removeEventListener("mousedown", zu);
  }, [offen]);

  function nimm(z: Zeile | undefined) {
    if (!z || z.art === "titel") return;
    onWahl(z.art === "alle" ? null : z.akte.id);
    setOffen(false);
    setSuche("");
  }

  function taste(e: KeyboardEvent) {
    const pos = waehlbar.indexOf(markiert);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setMarkiert(waehlbar[Math.min(waehlbar.length - 1, pos + 1)] ?? markiert);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setMarkiert(waehlbar[Math.max(0, pos - 1)] ?? markiert);
    } else if (e.key === "Enter") {
      e.preventDefault();
      nimm(zeilen[markiert]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOffen(false);
    }
  }

  return (
    <div className="akten-wahl-feld" ref={rahmen}>
      <button
        type="button"
        className="akten-wahl-knopf"
        aria-haspopup="listbox"
        aria-expanded={offen}
        onClick={() => setOffen(!offen)}
        title={gewaehlt ? `Gesucht wird nur in der Akte ${gewaehlt.aktenzeichen ?? gewaehlt.name}` : "Gesucht wird in allen Akten"}
      >
        <span className="akten-wahl-text">
          {gewaehlt ? (
            <>
              Akte: {gewaehlt.aktenzeichen && <strong>{gewaehlt.aktenzeichen}</strong>} {gewaehlt.name}
            </>
          ) : (
            "Alle Akten"
          )}
        </span>
        <span aria-hidden>▾</span>
      </button>
      {offen && (
        <div className="akten-wahl-liste">
          <input
            autoFocus
            type="search"
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
            onKeyDown={taste}
            placeholder="Akte suchen: Aktenzeichen, Partei, Gericht …"
            aria-label="Akte suchen"
          />
          <ul role="listbox" ref={liste}>
            {zeilen.map((z, i) =>
              z.art === "titel" ? (
                <li key={`t${i}`} className="akten-wahl-titel" role="presentation">
                  {z.text}
                </li>
              ) : (
                <li
                  key={z.art === "alle" ? "alle" : z.akte.id}
                  role="option"
                  aria-selected={z.art === "alle" ? akteId == null : z.akte.id === akteId}
                  className={`akten-wahl-zeile${i === markiert ? " markiert" : ""}`}
                  onMouseEnter={() => setMarkiert(i)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    nimm(z);
                  }}
                >
                  {z.art === "alle" ? (
                    <strong>Alle Akten</strong>
                  ) : (
                    <>
                      <div>
                        {z.akte.aktenzeichen && <strong>{z.akte.aktenzeichen}</strong>} {z.akte.name}
                      </div>
                      {parteien(z.akte) && <div className="leise klein">{parteien(z.akte)}</div>}
                    </>
                  )}
                </li>
              ),
            )}
            {zeilen.length === 0 && <li className="akten-wahl-titel">Keine Akte passt zu „{suche}“.</li>}
            {weitere > 0 && (
              <li className="akten-wahl-titel">
                {weitere} weitere {weitere === 1 ? "Akte" : "Akten"}, bitte genauer eingrenzen.
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
