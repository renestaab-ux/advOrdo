import { FormEvent, useEffect, useState } from "react";
import {
  MandantVereinbarungen as MandantDaten,
  VereinbarungDaten,
  ZeitListe,
  ZeitVereinbarung as Vereinbarung,
  akteTitel,
  datumDe,
  euro,
  kern,
} from "./kern";
import { useBearbeitung } from "./ungespeichert";

/** Kernwerte („4500.00“) deutsch zum Bearbeiten („4500,00“). */
const de = (t: string | null) => (t ?? "").replace(".", ",");

export const taktText = (t: number) => (t === 1 ? "minutengenau" : `${t} Min.`);

/** „vereinbart am 01.10.2026 · Taktung 6 Min. · RVG-Mindestvergütung“ */
export function vereinbarungText(v: VereinbarungDaten, allgemein: number): string {
  return [
    v.vereinbart_am ? `vereinbart am ${datumDe(v.vereinbart_am)}` : "ohne Datum",
    `Taktung ${taktText(v.taktung ?? allgemein)}${v.taktung ? "" : " (wie Einstellungen)"}`,
    v.mindestverguetung ? "RVG-Mindestvergütung" : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

type Art = "einzel" | "rahmen";

/**
 * Karte im Reiter „Zeiten“: welche Vergütungsvereinbarung für die Akte gilt. Eine Rahmenvereinbarung mit dem
 * Mandanten gilt für alle seine Akten; eine Einzelvereinbarung ersetzt sie für diese Akte. Dazu die Kostenschätzung
 * der Akte.
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
  const [offen, setOffen] = useState<Art | "budget" | null>(null);
  const [budget, setBudget] = useState(de(v.kostenschaetzung));
  const [fehler, setFehler] = useState<string | null>(null);
  useEffect(() => setBudget(de(v.kostenschaetzung)), [v.kostenschaetzung]);

  async function speichern(daten: Record<string, unknown>) {
    setFehler(null);
    try {
      onGespeichert(await kern<ZeitListe>("zeit.vereinbarung_speichern", { akte_id: akteId, daten }));
      setOffen(null);
    } catch (x) {
      setFehler(String(x));
    }
  }

  const m = v.mandant;
  return (
    <section className="karte zeit-vereinbarung" aria-label="Vergütungsvereinbarung">
      <h3>{m ? `Vergütungsvereinbarung mit ${m.name}` : "Vergütungsvereinbarung"}</h3>

      {v.art === "einzel" && v.einzel ? (
        <p className="zeit-vereinbarung-stand">
          <span className="status-marke">Einzelvereinbarung</span> {vereinbarungText(v.einzel, v.taktung_allgemein)}
          {v.rahmen && <span className="leise klein"> · ersetzt in dieser Akte die Rahmenvereinbarung</span>}
        </p>
      ) : v.art === "rahmen" && v.rahmen ? (
        <p className="zeit-vereinbarung-stand">
          <span className="status-marke">Rahmenvereinbarung</span> {vereinbarungText(v.rahmen, v.taktung_allgemein)}
          {m && m.akten > 1 && (
            <span className="leise klein"> · gilt für alle {m.akten} Akten ohne Einzelvereinbarung</span>
          )}
        </p>
      ) : (
        <p className="zeit-vereinbarung-stand leise">Keine Vereinbarung vermerkt.</p>
      )}
      {v.notiz && offen === null && <p className="leise klein">{v.notiz}</p>}
      {v.kostenschaetzung && (
        <p className="zeit-vereinbarung-stand">
          Kostenschätzung dieser Akte {euro(v.kostenschaetzung)}
          {anteil !== null && ` (${anteil} % erreicht)`}
        </p>
      )}
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

      {offen === "einzel" || offen === "rahmen" ? (
        <VereinbarungFormular
          wert={(offen === "einzel" ? v.einzel : v.rahmen) ?? null}
          taktungen={taktungen}
          allgemein={v.taktung_allgemein}
          hinweis={
            offen === "einzel"
              ? "Gilt nur für diese Akte und ersetzt hier eine Rahmenvereinbarung ganz."
              : `Gilt für alle Akten von ${m?.name ?? "diesem Mandanten"} ohne Einzelvereinbarung.`
          }
          onSpeichern={(d) => speichern({ ...d, art: offen })}
          onAbbrechen={() => setOffen(null)}
        />
      ) : offen === "budget" ? (
        <form
          className="zeit-vereinbarung-form"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void speichern({ kostenschaetzung: budget });
          }}
        >
          <label className="feld kurz">
            Kostenschätzung dieser Akte (netto)
            <input
              inputMode="decimal"
              placeholder="z. B. 4.500"
              value={budget}
              onChange={(x) => setBudget(x.target.value)}
            />
          </label>
          <div className="zeit-vereinbarung-knoepfe">
            <button type="submit">Speichern</button>
            <button type="button" className="zweitrangig" onClick={() => setOffen(null)}>
              Abbrechen
            </button>
          </div>
        </form>
      ) : (
        <div className="zeit-vereinbarung-knoepfe">
          <button className="zweitrangig klein" onClick={() => setOffen("einzel")}>
            {v.einzel ? "Einzelvereinbarung bearbeiten" : "Einzelvereinbarung für diese Akte"}
          </button>
          {m && (
            <button className="zweitrangig klein" onClick={() => setOffen("rahmen")}>
              {v.rahmen ? "Rahmenvereinbarung bearbeiten" : "Rahmenvereinbarung anlegen"}
            </button>
          )}
          {v.einzel && (
            <button
              className="link klein"
              onClick={() => {
                if (window.confirm("Einzelvereinbarung dieser Akte aufheben? Dann gilt wieder die Rahmenvereinbarung."))
                  void speichern({ einzel_aufheben: true });
              }}
            >
              Einzelvereinbarung aufheben
            </button>
          )}
          <button className="link klein" onClick={() => setOffen("budget")}>
            {v.kostenschaetzung ? "Kostenschätzung ändern" : "Kostenschätzung eintragen"}
          </button>
        </div>
      )}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
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

/** Felder einer Vereinbarung (Datum, Taktung, Mindestvergütung, Notiz); auch für die Daten eines Mandanten. */
export function VereinbarungFormular({
  wert,
  taktungen,
  allgemein,
  hinweis,
  onSpeichern,
  onAbbrechen,
}: {
  wert: VereinbarungDaten | null;
  taktungen: number[];
  allgemein: number;
  hinweis: string;
  onSpeichern: (d: Record<string, unknown>) => Promise<unknown>;
  onAbbrechen: () => void;
}) {
  const vereinbarungBearb = useBearbeitung("Vergütungsvereinbarung");
  const [f, setF] = useState({
    vereinbart_am: wert?.vereinbart_am ?? "",
    taktung: wert?.taktung ? String(wert.taktung) : "",
    mindestverguetung: wert?.mindestverguetung ?? false,
    notiz: wert?.notiz ?? "",
  });
  return (
    <form {...vereinbarungBearb.formular}
      className="zeit-vereinbarung-form"
      onSubmit={(e) => {
        e.preventDefault();
        void onSpeichern({
          taktung: f.taktung ? Number(f.taktung) : null,
          vereinbart_am: f.vereinbart_am || null,
          mindestverguetung: f.mindestverguetung,
          notiz: f.notiz,
        });
      }}
    >
      <p className="leise klein">{hinweis} Die Taktung hier geht der aus den Einstellungen vor.</p>
      <div className="schrift-wahl">
        <label className="feld kurz">
          Vereinbart am
          <input type="date" value={f.vereinbart_am} onChange={(x) => setF({ ...f, vereinbart_am: x.target.value })} />
        </label>
        <label className="feld">
          Taktung
          <select value={f.taktung} onChange={(x) => setF({ ...f, taktung: x.target.value })}>
            <option value="">wie Einstellungen ({taktText(allgemein)})</option>
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
        RVG-Mindestvergütung vereinbart: in gerichtlichen Verfahren mindestens die gesetzlichen Gebühren, es wird nur
        das Höhere berechnet
      </label>
      <label className="feld">
        Notiz
        <input
          className="text"
          placeholder="z. B. Sondersätze, Abrechnung quartalsweise"
          value={f.notiz}
          onChange={(x) => setF({ ...f, notiz: x.target.value })}
        />
      </label>
      <div className="zeit-vereinbarung-knoepfe">
        <button type="submit">Speichern</button>
        <button type="button" className="zweitrangig" onClick={onAbbrechen}>
          Abbrechen
        </button>
      </div>
    </form>
  );
}

/**
 * In den Daten eines Mandanten: die Rahmenvereinbarung (gilt für alle seine Akten) und die Akten mit eigener
 * Einzelvereinbarung. Gibt es beides, ist die Rahmenvereinbarung hervorgehoben.
 */
export function MandantVereinbarungen({ mandant, onAkte }: { mandant: string; onAkte: (akteId: number) => void }) {
  const [d, setD] = useState<MandantDaten | null>(null);
  const [offen, setOffen] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    setD(null);
    setOffen(false);
    kern<MandantDaten>("zeit.mandant_vereinbarungen", { mandant }).then(setD, (x) => setFehler(String(x)));
  }, [mandant]);

  async function ausfuehren(methode: string, params: Record<string, unknown>) {
    setFehler(null);
    try {
      setD(await kern<MandantDaten>(methode, { mandant, ...params }));
      setOffen(false);
    } catch (x) {
      setFehler(String(x));
    }
  }

  if (!d) return fehler ? <p className="fehler" role="alert">{fehler}</p> : null;
  const beides = d.rahmen !== null && d.einzel.length > 0;
  return (
    <div className="beziehungen mandant-vereinbarungen">
      <h4>Vergütungsvereinbarungen</h4>
      {offen ? (
        <VereinbarungFormular
          wert={d.rahmen}
          taktungen={d.taktungen}
          allgemein={d.taktung_allgemein}
          hinweis={`Rahmenvereinbarung: gilt für alle Akten dieses Mandanten (derzeit ${d.akten}) ohne Einzelvereinbarung.`}
          onSpeichern={(daten) => ausfuehren("zeit.rahmen_speichern", { daten })}
          onAbbrechen={() => setOffen(false)}
        />
      ) : d.rahmen ? (
        <div className={`rahmen-vereinbarung${beides ? " hervorgehoben" : ""}`}>
          <p>
            <span className="status-marke">Rahmenvereinbarung</span> {vereinbarungText(d.rahmen, d.taktung_allgemein)}
          </p>
          {d.rahmen.notiz && <p className="leise klein">{d.rahmen.notiz}</p>}
          <p className="leise klein">
            Gilt für {d.akten === 1 ? "die Akte" : `alle ${d.akten} Akten`} dieses Mandanten
            {d.einzel.length > 0
              ? `, außer ${d.einzel.length === 1 ? "der Akte" : "den Akten"} mit Einzelvereinbarung`
              : ""}
            .
          </p>
          <div className="zeit-vereinbarung-knoepfe">
            <button className="zweitrangig klein" onClick={() => setOffen(true)}>
              Rahmenvereinbarung bearbeiten
            </button>
            <button
              className="link klein"
              onClick={() => {
                if (window.confirm("Rahmenvereinbarung löschen? Einzelvereinbarungen der Akten bleiben bestehen."))
                  void ausfuehren("zeit.rahmen_loeschen", {});
              }}
            >
              Löschen
            </button>
          </div>
        </div>
      ) : (
        <div className="zeit-vereinbarung-knoepfe">
          <span className="leise">Keine Rahmenvereinbarung.</span>
          <button className="zweitrangig klein" onClick={() => setOffen(true)}>
            Rahmenvereinbarung anlegen
          </button>
        </div>
      )}
      {d.einzel.length > 0 && (
        <>
          <p className="leise klein">Einzelvereinbarungen (gelten nur für ihre Akte):</p>
          <ul className="eintraege">
            {d.einzel.map((e) => (
              <li key={e.akte_id}>
                <button className="link" onClick={() => onAkte(e.akte_id)}>
                  {akteTitel({ name: e.akte, aktenzeichen: e.aktenzeichen })}
                </button>
                <span className="leise">{vereinbarungText(e, d.taktung_allgemein)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
    </div>
  );
}
