import { FormEvent, Fragment, useCallback, useEffect, useState } from "react";
import { GesetzVorschlag, Schreibweise, kern } from "./kern";

// Vorschläge je Abkürzung nur einmal beim Kern erfragen; mehrere Zitate desselben Gesetzes teilen sie.
const vorschlagsSpeicher = new Map<string, Promise<GesetzVorschlag[]>>();

export function vorschlaegeVergessen() {
  vorschlagsSpeicher.clear();
}

/**
 * „Könnte … gemeint sein?“ unter einem Zitat mit unbekanntem Gesetz. Ein Klick legt eine eigene Schreibweise an; sie gilt
 * danach für alle Akten, und die betroffenen Zitate werden sofort neu geprüft.
 */
export function GesetzVorschlaege({
  gesetz,
  onZuordnen,
  gesperrt,
}: {
  gesetz: string;
  onZuordnen: (von: string, nach: string) => void;
  gesperrt?: boolean;
}) {
  const [vorschlaege, setVorschlaege] = useState<GesetzVorschlag[] | null>(null);
  useEffect(() => {
    let aktuell = true;
    let anfrage = vorschlagsSpeicher.get(gesetz);
    if (!anfrage) {
      anfrage = kern<GesetzVorschlag[]>("gesetze.vorschlaege", { gesetz }).catch(() => []);
      vorschlagsSpeicher.set(gesetz, anfrage);
    }
    void anfrage.then((v) => aktuell && setVorschlaege(v));
    return () => {
      aktuell = false;
    };
  }, [gesetz]);
  if (!vorschlaege || vorschlaege.length === 0) return null;
  return (
    <div className="meinten-sie">
      <span>Könnte</span>
      {vorschlaege.map((v, i) => (
        <Fragment key={v.abk}>
          {i > 0 && <span>{i === vorschlaege.length - 1 ? "oder" : ","}</span>}
          <button
            className="zweitrangig klein"
            disabled={gesperrt}
            title={`„${gesetz}“ künftig in allen Akten als ${v.abk} lesen${v.titel ? ` (${v.titel})` : ""}`}
            onClick={() => onZuordnen(gesetz, v.abk)}
          >
            {v.abk}
            {!v.geladen && <span className="leise"> (noch nicht geladen)</span>}
          </button>
        </Fragment>
      ))}
      <span>gemeint sein?</span>
    </div>
  );
}

/** Liste der eigenen Schreibweisen im Bereich „Gesetze“: anlegen und löschen. */
export function EigeneSchreibweisen({ gesetze, gesperrt }: { gesetze: string[]; gesperrt?: boolean }) {
  const [liste, setListe] = useState<Schreibweise[]>([]);
  const [von, setVon] = useState("");
  const [nach, setNach] = useState("");
  const [meldung, setMeldung] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const laden = useCallback(async () => {
    setListe(await kern<Schreibweise[]>("gesetze.schreibweisen"));
  }, []);
  useEffect(() => {
    void laden().catch((e) => setFehler(String(e)));
  }, [laden]);

  async function ausfuehren(f: () => Promise<{ dokumente: number }>, text: string) {
    setFehler(null);
    setMeldung(null);
    try {
      const r = await f();
      vorschlaegeVergessen();
      await laden();
      setMeldung(`${text} ${r.dokumente === 1 ? "Ein Dokument" : `${r.dokumente} Dokumente`} neu geprüft.`);
    } catch (e) {
      setFehler(String(e));
    }
  }

  async function anlegen(e: FormEvent) {
    e.preventDefault();
    await ausfuehren(() => kern("gesetze.schreibweise_setzen", { von, nach }), `„${von.trim()}“ meint jetzt ${nach.trim()}.`);
    setVon("");
    setNach("");
  }

  return (
    <details className="schreibweisen">
      <summary>Eigene Schreibweisen: {liste.length}</summary>
      <p className="leise">
        Steht in Schriftsätzen eine Abkürzung, die die App nicht kennt, etwa „AVBFernwärmV“, lässt sie sich hier
        einem Gesetz zuordnen. Das gilt für alle Akten. Im Ergebnis bleibt sichtbar, wie das Zitat im Text geschrieben
        war.
      </p>
      {liste.length > 0 && (
        <ul className="schreibweisen-liste">
          {liste.map((s) => (
            <li key={s.von}>
              <strong>{s.von}</strong> meint <strong>{s.nach}</strong>{" "}
              <button
                className="link"
                disabled={gesperrt}
                aria-label={`Schreibweise ${s.von} löschen`}
                onClick={() =>
                  void ausfuehren(() => kern("gesetze.schreibweise_loeschen", { von: s.von }), `„${s.von}“ gelöscht.`)
                }
              >
                löschen
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="schreibweise-neu" onSubmit={anlegen}>
        <input
          value={von}
          onChange={(e) => setVon(e.target.value)}
          placeholder="im Text, z. B. BDSG-neu"
          aria-label="Schreibweise im Text"
        />
        <span>meint</span>
        <input
          value={nach}
          onChange={(e) => setNach(e.target.value)}
          placeholder="Gesetz, z. B. BDSG"
          aria-label="Gemeintes Gesetz"
          list="schreibweise-gesetze"
        />
        <datalist id="schreibweise-gesetze">
          {gesetze.map((g) => (
            <option key={g} value={g} />
          ))}
        </datalist>
        <button type="submit" className="zweitrangig" disabled={gesperrt || !von.trim() || !nach.trim()}>
          Zuordnen
        </button>
      </form>
      {meldung && <p className="status" role="status">{meldung}</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
    </details>
  );
}
