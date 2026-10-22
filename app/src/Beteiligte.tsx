import { useCallback, useEffect, useState } from "react";
import { BeteiligterFormular } from "./AkteStammdaten";
import { AktenOptionen, Beteiligter, akteTitel, istDesktop, kern } from "./kern";

type Art = "" | "person" | "organisation";

/**
 * Bereich „Beteiligte“: das Beteiligtenverzeichnis der aktiven Umgebung. Jede Person und Organisation steht dort
 * einmal und wird in den Akten nur verwiesen; Änderungen hier gelten für alle Akten.
 */
export default function Beteiligte({ onAkte }: { onAkte: (akteId: number) => void }) {
  const [optionen, setOptionen] = useState<AktenOptionen | null>(null);
  const [suche, setSuche] = useState("");
  const [art, setArt] = useState<Art>("");
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
          <option value="">Alle</option>
          <option value="person">Personen</option>
          <option value="organisation">Organisationen</option>
        </select>
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
        </section>
      )}

      <table className="dokumente verzeichnis">
        <thead>
          <tr>
            <th>Name</th>
            <th>Art</th>
            <th>Rolle</th>
            <th>Ort</th>
            <th>Akten</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {liste.map((b) => (
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
      {liste.length === 0 && !laeuft && (
        <p className="leer">{suche.trim() ? "Kein Eintrag gefunden." : "Noch keine Beteiligten. Sie entstehen beim Erfassen in einer Akte oder hier."}</p>
      )}
    </div>
  );
}
