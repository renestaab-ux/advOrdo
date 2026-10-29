import { useCallback, useEffect, useState } from "react";
import { BeteiligterFormular } from "./AkteStammdaten";
import { AktenOptionen, Beteiligter, akteTitel, istDesktop, kern, sortiert } from "./kern";
import { SortKopf, useSortierung } from "./Sortierung";
import { MandantVereinbarungen } from "./ZeitVereinbarung";

type Art = "" | "person" | "organisation";
type Seite = "" | "eigene" | "gegen" | "gericht" | "neutral" | "ohne";

const SEITEN: [Seite, string][] = [
  ["", "Rolle: alle"],
  ["eigene", "Eigene Seite (Mandant …)"],
  ["gegen", "Gegenseite"],
  ["gericht", "Gericht"],
  ["neutral", "Neutral / Dritte"],
  ["ohne", "In keiner Akte"],
];

/** Ob ein Eintrag zur gewählten Seite gehört; Geschäftsführer zählen zur Seite ihrer Firma. */
function aufSeite(b: Beteiligter, seite: Seite): boolean {
  if (!seite) return true;
  if (seite === "ohne") return (b.akten_anzahl ?? 0) === 0;
  return (b.rollen ?? []).some((r) => r.gruppe === seite || (r.gruppe === "funktion" && r.seite === seite));
}

/**
 * Bereich „Beteiligte“: das Beteiligtenverzeichnis der aktiven Umgebung. Jede Person und Organisation steht dort
 * einmal und wird in den Akten nur verwiesen; Änderungen hier gelten für alle Akten.
 */
export default function Beteiligte({ onAkte }: { onAkte: (akteId: number) => void }) {
  const [optionen, setOptionen] = useState<AktenOptionen | null>(null);
  const [suche, setSuche] = useState("");
  const [art, setArt] = useState<Art>("");
  const [kategorie, setKategorie] = useState("");
  const [seite, setSeite] = useState<Seite>("");
  const [sortierung, sortieren] = useSortierung("beteiligte.sortierung", { spalte: "name", absteigend: false });
  const [liste, setListe] = useState<Beteiligter[]>([]);
  const [formular, setFormular] = useState<{ art: "person" | "organisation"; eintrag?: Beteiligter; nr: number } | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);

  const ausfuehren = useCallback(async <T,>(f: () => Promise<T>) => {
    setLaeuft(true);
    setFehler(null);
    try {
      return await f();
    } catch (e) {
      setFehler(String(e));
      return undefined;
    } finally {
      setLaeuft(false);
    }
  }, []);

  const laden = useCallback(async () => {
    setListe(await kern<Beteiligter[]>("beteiligte.liste", { suche, art: art || null }));
  }, [suche, art]);

  useEffect(() => {
    if (!istDesktop) return;
    void ausfuehren(async () => setOptionen(await kern<AktenOptionen>("akten.optionen")));
  }, [ausfuehren]);

  useEffect(() => {
    if (!istDesktop) return;
    const t = setTimeout(() => void ausfuehren(laden), 200);
    return () => clearTimeout(t);
  }, [laden, ausfuehren]);

  async function oeffnen(id: number) {
    const e = await ausfuehren(() => kern<Beteiligter>("beteiligte.eintrag", { beteiligter_id: id }));
    if (e) setFormular({ art: e.art, eintrag: e, nr: Date.now() });
  }

  async function loeschen(b: Beteiligter) {
    if (!window.confirm(`„${b.name}“ aus dem Beteiligtenverzeichnis löschen?`)) return;
    const r = await ausfuehren(() => kern("beteiligte.loeschen", { beteiligter_id: b.id }));
    if (r) {
      if (formular?.eintrag?.id === b.id) setFormular(null);
      setMeldung(`„${b.name}“ gelöscht.`);
      await laden();
    }
  }

  if (!istDesktop) return <p className="leer">Das Beteiligtenverzeichnis gibt es nur in der Desktop-App.</p>;

  const offen = formular?.eintrag;
  const sichtbar = sortiert(
    liste.filter((b) => (!kategorie || art === "person" || b.daten.kategorie === kategorie) && aufSeite(b, seite)),
    sortierung,
    {
      // Personen nach Nachnamen, Organisationen nach Namen.
      name: (b) => (b.art === "person" ? `${b.daten.nachname ?? ""} ${b.daten.vorname ?? ""}`.trim() || b.name : b.name),
      art: (b) => (b.art === "person" ? "Person" : `Organisation ${b.daten.kategorie ?? ""}`),
      rolle: (b) => b.rollen?.[0]?.text,
      ort: (b) => b.daten.ort as string,
      akten: (b) => b.akten_anzahl ?? 0,
    },
  );

  return (
    <div className="beteiligte-verzeichnis">
      <header className="kopf">
        <h1>Beteiligte</h1>
        <span className="aktionen">
          <button className="zweitrangig" onClick={() => setFormular({ art: "person", nr: Date.now() })}>
            Neue Person …
          </button>
          <button className="zweitrangig" onClick={() => setFormular({ art: "organisation", nr: Date.now() })}>
            Neue Organisation …
          </button>
        </span>
      </header>
      <p className="erklaerung">
        Alle Personen und Organisationen dieser Umgebung. Jeder Eintrag steht nur einmal hier; Änderungen gelten in allen
        Akten, an denen er beteiligt ist.
      </p>

      <div className="verzeichnis-filter">
        <input value={suche} onChange={(e) => setSuche(e.target.value)} placeholder="Name suchen, auch früherer Name"
          aria-label="Beteiligte suchen" />
        <select value={art} onChange={(e) => setArt(e.target.value as Art)} aria-label="Art">
          <option value="">Art: alle</option>
          <option value="person">Personen</option>
          <option value="organisation">Organisationen</option>
        </select>
        {art !== "person" && optionen && (
          <select value={kategorie} onChange={(e) => setKategorie(e.target.value)} aria-label="Kategorie">
            <option value="">Kategorie: alle</option>
            {optionen.kategorien.map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
        )}
        <select value={seite} onChange={(e) => setSeite(e.target.value as Seite)} aria-label="Rolle">
          {SEITEN.map(([k, t]) => (
            <option key={k} value={k}>
              {t}
            </option>
          ))}
        </select>
        {((kategorie && art !== "person") || seite) && (
          <span className="leise">
            {sichtbar.length} von {liste.length}
          </span>
        )}
      </div>

      {fehler && <p className="fehler">{fehler}</p>}
      {meldung && !fehler && <p className="meldung">{meldung}</p>}

      {formular && optionen && (
        <section className="karte">
          <BeteiligterFormular
            key={formular.nr}
            art={formular.art}
            eintrag={formular.eintrag}
            vorbelegung={formular.eintrag ? "" : suche}
            kategorien={optionen.kategorien}
            beziehungen={optionen.beziehungen}
            funktionen={optionen.funktionen ?? []}
            ausfuehren={ausfuehren}
            rolleText=""
            ohneAkte
            onFertig={(neu, uebernehmen) => {
              setFormular(null);
              if (neu) setMeldung(`„${neu.name}“ gespeichert.`);
              // Neu angelegt oder „Vorhandenen öffnen“: gleich zum Bearbeiten öffnen, etwa für Vertreter.
              if (neu && uebernehmen) void oeffnen(neu.id);
              void ausfuehren(laden);
            }}
          />
          {offen && (offen.akten ?? []).length > 0 && (
            <div className="beziehungen">
              <h4>Beteiligt an</h4>
              <ul className="eintraege">
                {(offen.akten ?? []).map((a) => (
                  <li key={`${a.akte_id}-${a.rolle}`}>
                    <button className="link" onClick={() => onAkte(a.akte_id)}>
                      {akteTitel({ name: a.akte, aktenzeichen: a.aktenzeichen })}
                    </button>
                    <span className="leise">{optionen.rollen[a.rolle]?.text ?? a.rolle}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {offen && (offen.akten ?? []).some((a) => a.rolle === "mandant") && (
            <MandantVereinbarungen mandant={`b:${offen.id}`} onAkte={onAkte} />
          )}
        </section>
      )}

      <table className="dokumente verzeichnis">
        <thead>
          <tr>
            <SortKopf spalte="name" titel="Name" sortierung={sortierung} onSortieren={sortieren} />
            <SortKopf spalte="art" titel="Art" sortierung={sortierung} onSortieren={sortieren} />
            <SortKopf spalte="rolle" titel="Rolle" sortierung={sortierung} onSortieren={sortieren} />
            <SortKopf spalte="ort" titel="Ort" sortierung={sortierung} onSortieren={sortieren} />
            <SortKopf spalte="akten" titel="Akten" sortierung={sortierung} onSortieren={sortieren} />
            <th />
          </tr>
        </thead>
        <tbody>
          {sichtbar.map((b) => (
            <tr key={b.id} className={offen?.id === b.id ? "gewaehlt" : undefined}>
              <td>
                <button className="link" onClick={() => void oeffnen(b.id)}>
                  {b.name}
                </button>
              </td>
              <td className="leise">
                {b.art === "person" ? "Person" : `Organisation${b.daten.kategorie ? ` · ${b.daten.kategorie}` : ""}`}
              </td>
              <td>
                {(b.rollen ?? []).length > 0 ? (
                  <span className="rollen">
                    {(b.rollen ?? []).map((r) => (
                      <span key={r.text} className={`rolle-marke ${r.gruppe} ${r.seite ?? ""}`.trim()}>
                        {r.text}
                      </span>
                    ))}
                  </span>
                ) : (
                  <span className="leise">–</span>
                )}
              </td>
              <td>{(b.daten.ort as string) || "–"}</td>
              <td>{b.akten_anzahl ?? 0}</td>
              <td>
                {(b.akten_anzahl ?? 0) === 0 && (
                  <button className="link gefahr" onClick={() => void loeschen(b)} disabled={laeuft}>
                    Löschen
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {sichtbar.length === 0 && !laeuft && (
        <p className="leer">
          {suche.trim() || kategorie || seite
            ? "Kein Eintrag passt zu Suche und Filtern."
            : "Noch keine Beteiligten. Sie entstehen beim Erfassen in einer Akte oder hier."}
        </p>
      )}
    </div>
  );
}
