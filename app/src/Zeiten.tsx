import { FormEvent, useEffect, useState } from "react";
import {
  ZeitEinstellungen,
  ZeitEintrag,
  ZeitListe,
  datumDe,
  euro,
  kern,
  stundenText,
  uhrText,
  zeitGeaendert,
} from "./kern";
import { useLaufenderTimer } from "./zeitTimer";

const heute = () => new Date().toLocaleDateString("sv-SE"); // JJJJ-MM-TT in Ortszeit

interface Formular {
  datum: string;
  bearbeiter_id: string;
  dauer: string;
  von: string;
  bis: string;
  taetigkeit: string;
  abrechenbar: boolean;
}

/**
 * Reiter „Zeiten“ der Akte: Timer und Einträge von Hand, getaktet nach Einstellungen → Zeiterfassung. Offene Zeiten
 * übernimmt die Kostennote (Reiter „Schriftstücke“) als Posten „Stunden × Satz“.
 */
export default function Zeiten({
  akteId,
  onEinstellungen,
  onKostennote,
}: {
  akteId: number;
  onEinstellungen: () => void;
  onKostennote: () => void;
}) {
  const [liste, setListe] = useState<ZeitListe | null>(null);
  const [einst, setEinst] = useState<ZeitEinstellungen | null>(null);
  const [taetigkeit, setTaetigkeit] = useState("");
  const [timerWer, setTimerWer] = useState("");
  const leer = (): Formular => ({
    datum: heute(),
    bearbeiter_id: einst?.standard_bearbeiter_id ? String(einst.standard_bearbeiter_id) : "",
    dauer: "",
    von: "",
    bis: "",
    taetigkeit: "",
    abrechenbar: true,
  });
  const [f, setF] = useState<Formular | null>(null);
  const [bearbeitet, setBearbeitet] = useState<number | null>(null);
  const [loeschfrage, setLoeschfrage] = useState<ZeitEintrag | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const { laufend, sekunden } = useLaufenderTimer();

  async function laden() {
    const [l, e] = await Promise.all([
      kern<ZeitListe>("zeit.liste", { akte_id: akteId }),
      kern<ZeitEinstellungen>("zeit.einstellungen"),
    ]);
    setListe(l);
    setEinst(e);
    const std = e.standard_bearbeiter_id ? String(e.standard_bearbeiter_id) : "";
    setTimerWer((alt) => alt || std);
    setF((alt) => alt ?? { datum: heute(), bearbeiter_id: std, dauer: "", von: "", bis: "", taetigkeit: "", abrechenbar: true });
  }

  useEffect(() => {
    laden().catch((x) => setFehler(String(x)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [akteId]);

  // Timer anderswo gestartet oder angehalten (Seitenleiste): Liste neu.
  const laufendId = laufend?.id ?? null;
  useEffect(() => {
    void kern<ZeitListe>("zeit.liste", { akte_id: akteId }).then(setListe, () => undefined);
  }, [laufendId, akteId]);

  async function mit(f_: () => Promise<ZeitListe | null>, timer = false) {
    setFehler(null);
    try {
      const l = await f_();
      if (l) setListe(l);
      if (timer) zeitGeaendert();
      return true;
    } catch (x) {
      setFehler(String(x));
      return false;
    }
  }

  const aktive = einst?.bearbeiter.filter((b) => !b.archiviert) ?? [];
  const hierLaeuft = laufend && laufend.akte_id === akteId;

  async function starten() {
    if (
      await mit(
        () =>
          kern<ZeitListe>("zeit.starten", {
            akte_id: akteId,
            bearbeiter_id: timerWer ? Number(timerWer) : null,
            taetigkeit,
          }),
        true,
      )
    )
      setTaetigkeit("");
  }

  async function speichern(e: FormEvent) {
    e.preventDefault();
    if (!f) return;
    const daten = {
      datum: f.datum,
      bearbeiter_id: f.bearbeiter_id ? Number(f.bearbeiter_id) : null,
      dauer: f.von && f.bis ? "" : f.dauer,
      von: f.von,
      bis: f.bis,
      taetigkeit: f.taetigkeit,
      abrechenbar: f.abrechenbar,
    };
    const ok = await mit(() =>
      kern<ZeitListe>("zeit.speichern", { akte_id: akteId, daten, eintrag_id: bearbeitet }),
    );
    if (ok) {
      setBearbeitet(null);
      setF(leer());
    }
  }

  function bearbeiten(z: ZeitEintrag) {
    setBearbeitet(z.id);
    setF({
      datum: z.datum,
      bearbeiter_id: z.bearbeiter_id ? String(z.bearbeiter_id) : "",
      dauer: stundenText(z.laeuft_seit ? 0 : z.minuten),
      von: "",
      bis: "",
      taetigkeit: z.taetigkeit,
      abrechenbar: z.abrechenbar,
    });
  }

  if (!liste || !einst || !f) {
    return (
      <div className="zeiten">
        {fehler ? <p className="fehler">{fehler}</p> : <p className="status">Lade …</p>}
      </div>
    );
  }

  const g = liste.gesamt;
  // Bei laufendem Timer zählt die Uhr; die Dauer lässt sich erst nach dem Anhalten ändern.
  const bearbeitetLaeuft = !!liste.eintraege.find((z) => z.id === bearbeitet)?.laeuft_seit;
  return (
    <div className="zeiten">
      {aktive.length === 0 && (
        <p className="hinweis-box">
          Noch keine Bearbeiter angelegt. Stundensätze, Bearbeiter und Taktung legst du unter{" "}
          <button className="link" onClick={onEinstellungen}>
            Einstellungen → Zeiterfassung
          </button>{" "}
          fest.
        </p>
      )}

      <section className="karte zeit-timer" aria-label="Timer">
        {hierLaeuft ? (
          <div className="zeit-timer-zeile">
            <span className="zeit-uhr laeuft" aria-live="off">
              {uhrText(sekunden)}
            </span>
            <span>
              {laufend.bearbeiter}
              {laufend.taetigkeit && ` · ${laufend.taetigkeit}`}
            </span>
            <button onClick={() => void mit(() => kern<ZeitListe | null>("zeit.stoppen"), true)}>Anhalten</button>
          </div>
        ) : (
          <>
            {laufend && (
              <p className="hinweis klein">
                Ein Timer läuft gerade in der Akte „{laufend.akte}“ ({uhrText(sekunden)}). Ein neuer Timer hält ihn an.
              </p>
            )}
            <div className="zeit-timer-zeile">
              <span className="zeit-uhr">0:00:00</span>
              <select aria-label="Bearbeiter" value={timerWer} onChange={(x) => setTimerWer(x.target.value)}>
                <option value="">– Bearbeiter –</option>
                {aktive.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                    {b.stufe && ` (${b.stufe})`}
                  </option>
                ))}
              </select>
              <input
                className="text"
                placeholder="Tätigkeit, z. B. Klageerwiderung durcharbeiten"
                value={taetigkeit}
                onChange={(x) => setTaetigkeit(x.target.value)}
              />
              <button disabled={!timerWer} onClick={() => void starten()}>
                Timer starten
              </button>
            </div>
          </>
        )}
      </section>

      <form className="karte zeit-formular" onSubmit={speichern}>
        <h3>{bearbeitet ? "Eintrag ändern" : "Zeit von Hand erfassen"}</h3>
        <div className="schrift-wahl">
          <label className="feld kurz">
            Datum
            <input type="date" value={f.datum} onChange={(x) => setF({ ...f, datum: x.target.value })} />
          </label>
          <label className="feld">
            Bearbeiter
            <select value={f.bearbeiter_id} onChange={(x) => setF({ ...f, bearbeiter_id: x.target.value })}>
              <option value="">– wählen –</option>
              {einst.bearbeiter
                .filter((b) => !b.archiviert || String(b.id) === f.bearbeiter_id)
                .map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                    {b.stufe && ` (${b.stufe})`}
                  </option>
                ))}
            </select>
          </label>
          <label className="feld kurz" title="H:MM oder Stunden, z. B. 1:30 oder 1,5">
            Dauer
            <input
              placeholder="1:30 oder 1,5"
              value={f.dauer}
              disabled={!!(f.von && f.bis) || bearbeitetLaeuft}
              onChange={(x) => setF({ ...f, dauer: x.target.value })}
            />
          </label>
          <label className="feld kurz">
            oder von
            <input type="time" value={f.von} onChange={(x) => setF({ ...f, von: x.target.value })} />
          </label>
          <label className="feld kurz">
            bis
            <input type="time" value={f.bis} onChange={(x) => setF({ ...f, bis: x.target.value })} />
          </label>
        </div>
        <div className="schrift-wahl">
          <label className="feld">
            Tätigkeit
            <input
              placeholder="z. B. Besprechung mit der Mandantin"
              value={f.taetigkeit}
              onChange={(x) => setF({ ...f, taetigkeit: x.target.value })}
            />
          </label>
        </div>
        <div className="notiz-optionen">
          <label>
            <input type="checkbox" checked={f.abrechenbar} onChange={(x) => setF({ ...f, abrechenbar: x.target.checked })} />{" "}
            abrechenbar
          </label>
          <button type="submit">{bearbeitet ? "Änderung speichern" : "Zeit speichern"}</button>
          {bearbeitet && (
            <button
              type="button"
              className="zweitrangig"
              onClick={() => {
                setBearbeitet(null);
                setF(leer());
              }}
            >
              Abbrechen
            </button>
          )}
        </div>
      </form>

      {fehler && <p className="fehler">{fehler}</p>}
      {loeschfrage && (
        <div className="rueckfrage" role="alertdialog" aria-label="Zeiteintrag löschen?">
          <strong>Diesen Zeiteintrag löschen?</strong>
          <p>
            {datumDe(loeschfrage.datum)} · {loeschfrage.bearbeiter} · {stundenText(loeschfrage.minuten)} Std.
            {loeschfrage.taetigkeit && ` · ${loeschfrage.taetigkeit}`}
          </p>
          <div className="aktionen">
            <button
              className="gefahr-voll"
              onClick={() => {
                const id = loeschfrage.id;
                setLoeschfrage(null);
                void mit(() => kern<ZeitListe>("zeit.loeschen", { eintrag_id: id }), true);
              }}
            >
              Löschen
            </button>
            <button className="zweitrangig" onClick={() => setLoeschfrage(null)} autoFocus>
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {liste.eintraege.length === 0 ? (
        <p className="leer">Noch keine Zeiten in dieser Akte.</p>
      ) : (
        <section className="karte zeit-liste">
          <div className="kopf">
            <h3>Erfasste Zeiten</h3>
            <span className="leise klein">Taktung {liste.taktung} Min. je Eintrag</span>
          </div>
          <table className="staffel">
            <thead>
              <tr>
                <th>Datum</th>
                <th>Bearbeiter</th>
                <th>Tätigkeit</th>
                <th className="zahl" title="Erfasst (Stunden:Minuten)">Dauer</th>
                <th className="zahl" title="Nach der Taktung">Getaktet</th>
                <th className="zahl">Betrag</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {liste.eintraege.map((z) => (
                <tr key={z.id} className={z.kostennote_id ? "abgerechnet" : undefined}>
                  <td>{datumDe(z.datum)}</td>
                  <td>
                    {z.bearbeiter}
                    {z.stufe && <span className="leise klein"> · {z.stufe}</span>}
                  </td>
                  <td>
                    {z.taetigkeit || <span className="leise">–</span>}
                    {z.laeuft_seit && <span className="status-marke laufend">läuft</span>}
                    {!z.abrechenbar && <span className="status-marke">nicht abrechenbar</span>}
                    {z.kostennote && <span className="status-marke">abgerechnet mit {z.kostennote}</span>}
                    {z.abrechenbar && !z.satz && <span className="status-marke hinweis">ohne Stundensatz</span>}
                  </td>
                  <td className="zahl">{stundenText(z.minuten)}</td>
                  <td className="zahl">{z.abrechenbar ? stundenText(z.getaktet) : ""}</td>
                  <td className="zahl" title={z.satz ? `${euro(z.satz)} je Stunde` : undefined}>
                    {z.betrag ? euro(z.betrag) : ""}
                  </td>
                  <td className="zeit-aktionen">
                    {!z.kostennote_id && (
                      <>
                        {!z.laeuft_seit && (
                          <button
                            className="link klein"
                            title="Timer für diesen Eintrag weiterlaufen lassen"
                            onClick={() =>
                              void mit(() => kern<ZeitListe>("zeit.starten", { akte_id: akteId, eintrag_id: z.id }), true)
                            }
                          >
                            Fortsetzen
                          </button>
                        )}
                        <button className="link klein" onClick={() => bearbeiten(z)}>
                          Bearbeiten
                        </button>
                        <button className="link klein gefahr" onClick={() => setLoeschfrage(z)}>
                          Löschen
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Summen</h3>
          <table className="staffel">
            <thead>
              <tr>
                <th>Bearbeiter</th>
                <th className="zahl">Erfasst</th>
                <th className="zahl">Getaktet</th>
                <th className="zahl">Betrag</th>
              </tr>
            </thead>
            <tbody>
              {liste.summen.map((s) => (
                <tr key={`${s.bearbeiter}|${s.stufe}`}>
                  <td>
                    {s.bearbeiter}
                    {s.stufe && <span className="leise klein"> · {s.stufe}</span>}
                  </td>
                  <td className="zahl">{stundenText(s.minuten)}</td>
                  <td className="zahl">{stundenText(s.getaktet)}</td>
                  <td className="zahl">{euro(s.betrag)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td>Gesamt</td>
                <td className="zahl">{stundenText(g.minuten)}</td>
                <td className="zahl">{stundenText(g.getaktet)}</td>
                <td className="zahl">{euro(g.betrag)}</td>
              </tr>
              <tr>
                <td colSpan={2}>Davon noch nicht abgerechnet (netto)</td>
                <td className="zahl">{stundenText(g.offen_minuten)}</td>
                <td className="zahl">{euro(g.offen)}</td>
              </tr>
            </tfoot>
          </table>
          {Number(g.offen) > 0 && (
            <p className="leise klein">
              Offene Zeiten übernimmt die Kostennote mit „Zeiten übernehmen“.{" "}
              <button className="link klein" onClick={onKostennote}>
                Zur Kostennote
              </button>
            </p>
          )}
        </section>
      )}
      <p className="leise klein">
        Ein Stundenhonorar setzt eine Vergütungsvereinbarung in Textform voraus (§ 3a Abs. 1 S. 1 RVG). Stundensätze,
        Bearbeiter und Taktung:{" "}
        <button className="link klein" onClick={onEinstellungen}>
          Einstellungen → Zeiterfassung
        </button>
      </p>
    </div>
  );
}
