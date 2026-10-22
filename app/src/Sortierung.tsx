import { useState } from "react";
import { Sortierung } from "./kern";

/** Sortierung einer Tabelle, je Gerät gemerkt; ohne Speicher gilt die Vorgabe bis zum Neustart. */
export function useSortierung(schluessel: string, vorgabe: Sortierung): [Sortierung, (spalte: string) => void] {
  const [s, setS] = useState<Sortierung>(() => {
    try {
      const gespeichert = JSON.parse(localStorage.getItem(schluessel) ?? "null");
      if (gespeichert && typeof gespeichert.spalte === "string") return { spalte: gespeichert.spalte, absteigend: !!gespeichert.absteigend };
    } catch {
      // Vorgabe nehmen
    }
    return vorgabe;
  });
  function wechseln(spalte: string) {
    // Erster Klick aufsteigend, zweiter Klick auf dieselbe Spalte kehrt um.
    const neu = { spalte, absteigend: s.spalte === spalte ? !s.absteigend : false };
    setS(neu);
    try {
      localStorage.setItem(schluessel, JSON.stringify(neu));
    } catch {
      // nur bis zum Neustart
    }
  }
  return [s, wechseln];
}

/** Spaltenkopf zum Sortieren: Klick sortiert, erneuter Klick kehrt die Reihenfolge um. */
export function SortKopf({
  spalte,
  titel,
  sortierung,
  onSortieren,
}: {
  spalte: string;
  titel: string;
  sortierung: Sortierung;
  onSortieren: (spalte: string) => void;
}) {
  const aktiv = sortierung.spalte === spalte;
  return (
    <th aria-sort={aktiv ? (sortierung.absteigend ? "descending" : "ascending") : "none"}>
      <button
        className={aktiv ? "sortier-kopf aktiv" : "sortier-kopf"}
        onClick={(e) => {
          e.stopPropagation();
          onSortieren(spalte);
        }}
        title={`Nach „${titel}“ sortieren`}
      >
        {titel}
        <span className="sortier-pfeil" aria-hidden>
          {aktiv ? (sortierung.absteigend ? "▼" : "▲") : "↕"}
        </span>
      </button>
    </th>
  );
}
