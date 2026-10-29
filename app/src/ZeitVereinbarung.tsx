import { FormEvent, useEffect, useState } from "react";
import { ZeitListe, ZeitVereinbarung as Vereinbarung, datumDe, euro, kern } from "./kern";

/** Kernwerte („4500.00“) deutsch zum Bearbeiten („4500,00“). */
const de = (t: string | null) => (t ?? "").replace(".", ",");

const taktText = (t: number) => (t === 1 ? "minutengenau" : `${t} Min.`);

/**
 * Karte im Reiter „Zeiten“: Vergütungsvereinbarung mit dem Mandanten (gilt für alle seine Akten) und die
 * Kostenschätzung dieser Akte. Die Taktung der Vereinbarung geht der aus den Einstellungen vor.
 */
export default function ZeitVereinbarung({
  akteId,
  v,
  anteil,
  taktungen,
  onGespeichert,
  onSchriftstuecke,
}: {
  akteId: number;
  v: Vereinbarung;
  anteil: number | null;
  taktungen: number[];
  onGespeichert: (l: ZeitListe) => void;
  onSchriftstuecke: () => void;
}) {
  const [offen, setOffen] = useState(false);
  const [f, setF] = useState(() => formular(v));
  const [fehler, setFehler] = useState<string | null>(null);
  useEffect(() => setF(formular(v)), [v]);

  async function speichern(e: FormEvent) {
    e.preventDefault();
    setFehler(null);
    const daten: Record<string, unknown> = { kostenschaetzung: f.kostenschaetzung };
    if (v.mandant) {
      Object.assign(daten, {
        taktung: f.taktung ? Number(f.taktung) : null,
        vereinbart_am: f.vereinbart_am || null,
        mindestverguetung: f.mindestverguetung,
        notiz: f.notiz,
      });
    }
    try {
      onGespeichert(await kern<ZeitListe>("zeit.vereinbarung_speichern", { akte_id: akteId, daten }));
      setOffen(false);
    } catch (x) {
      setFehler(String(x));
    }
  }

  const teile: string[] = [];
  if (v.mandant) {
    teile.push(v.vereinbart_am ? `vereinbart am ${datumDe(v.vereinbart_am)}` : "keine Vereinbarung vermerkt");
    teile.push(`Taktung ${taktText(v.taktung)}${v.taktung_eigen ? "" : " (wie Einstellungen)"}`);
    if (v.mindestverguetung) teile.push("RVG-Mindestvergütung");
  }
  if (v.kostenschaetzung)
    teile.push(`Kostenschätzung ${euro(v.kostenschaetzung)}${anteil !== null ? ` (${anteil} % erreicht)` : ""}`);

  return (
    <section className="karte zeit-vereinbarung" aria-label="Vergütungsvereinbarung">
      <div className="kopf">
        <h3>{v.mandant ? `Vergütungsvereinbarung mit ${v.mandant.name}` : "Vergütungsvereinbarung"}</h3>
        {!offen && (
          <button className="zweitrangig klein" onClick={() => setOffen(true)}>
            {v.vermerkt || v.kostenschaetzung ? "Bearbeiten" : "Eintragen"}
          </button>
        )}
      </div>
      {!v.mandant && (
        <p className="leise klein">
          Der Akte ist noch kein Mandant zugeordnet. Die Vereinbarung gilt je Mandant; hier lässt sich nur die
          Kostenschätzung der Akte eintragen.
        </p>
      )}
      {teile.length > 0 && <p className="zeit-vereinbarung-stand">{teile.join(" · ")}</p>}
      {anteil !== null && (
        <div
          className={`zeit-budget${anteil >= 100 ? " ueber" : anteil >= 80 ? " knapp" : ""}`}
          role="meter"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.min(anteil, 100)}
          aria-label="Anteil der Kostenschätzung"
        >
          <span style={{ width: `${Math.min(anteil, 100)}%` }} />
        </div>
      )}
      {offen && (
        <form onSubmit={speichern}>
          {v.mandant && (
            <>
              <p className="leise klein">
                Gilt für {v.mandant.akten === 1 ? "diese Akte" : `alle ${v.mandant.akten} Akten`} von {v.mandant.name}.
                Die Taktung hier geht der aus den Einstellungen vor.
              </p>
              <div className="schrift-wahl">
                <label className="feld kurz">
                  Vereinbart am
                  <input
                    type="date"
                    value={f.vereinbart_am}
                    onChange={(x) => setF({ ...f, vereinbart_am: x.target.value })}
                  />
                </label>
                <label className="feld">
                  Taktung
                  <select value={f.taktung} onChange={(x) => setF({ ...f, taktung: x.target.value })}>
                    <option value="">wie Einstellungen ({taktText(v.taktung_allgemein)})</option>
                    {taktungen.map((t) => (
                      <option key={t} value={t}>
                        {t === 1 ? "minutengenau" : `${t} Minuten${t > 6 ? " – über der empfohlenen Grenze" : ""}`}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="haken">
                <input
                  type="checkbox"
                  checked={f.mindestverguetung}
                  onChange={(x) => setF({ ...f, mindestverguetung: x.target.checked })}
                />{" "}
                RVG-Mindestvergütung vereinbart: in gerichtlichen Verfahren mindestens die gesetzlichen Gebühren, es
                wird nur das Höhere berechnet
              </label>
              <label className="feld">
                Notiz
                <input
                  className="text"
                  placeholder="z. B. Rahmenvereinbarung, Sondersätze, Abrechnung quartalsweise"
                  value={f.notiz}
                  onChange={(x) => setF({ ...f, notiz: x.target.value })}
                />
              </label>
            </>
          )}
          <label className="feld kurz">
            Kostenschätzung dieser Akte (netto)
            <input
              inputMode="decimal"
              placeholder="z. B. 4.500"
              value={f.kostenschaetzung}
              onChange={(x) => setF({ ...f, kostenschaetzung: x.target.value })}
            />
          </label>
          <div className="zeit-vereinbarung-knoepfe">
            <button type="submit">Speichern</button>
            <button
              type="button"
              className="zweitrangig"
              onClick={() => {
                setF(formular(v));
                setOffen(false);
              }}
            >
              Abbrechen
            </button>
          </div>
          {fehler && <p className="fehler">{fehler}</p>}
        </form>
      )}
      {v.notiz && !offen && <p className="leise klein">{v.notiz}</p>}
      <p className="leise klein">
        Eine Vorlage für die Vereinbarung mit Stundensätzen, Taktung und Kostenschätzung gibt es unter{" "}
        <button className="link klein" onClick={onSchriftstuecke}>
          Schriftstücke → Vergütungsvereinbarung
        </button>
        .
      </p>
    </section>
  );
}

function formular(v: Vereinbarung) {
  return {
    vereinbart_am: v.vereinbart_am ?? "",
    taktung: v.taktung_eigen ? String(v.taktung_eigen) : "",
    mindestverguetung: v.mindestverguetung,
    notiz: v.notiz,
    kostenschaetzung: de(v.kostenschaetzung),
  };
}
