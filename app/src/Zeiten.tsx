import { FormEvent, Fragment, useEffect, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import {
  Notiz,
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
import ZeitVereinbarung from "./ZeitVereinbarung";
import { useLaufenderTimer } from "./zeitTimer";
import { LeerHinweis } from "./Symbole";

const heute = () => new Date().toLocaleDateString("sv-SE"); // JJJJ-MM-TT in Ortszeit

interface Formular {
  datum: string;
  bearbeiter_id: string;
  /** Abweichende Stufe nur für diesen Eintrag (z. B. Reisezeit); leer: Stufe des Bearbeiters bzw. unverändert. */
  stufe_id: string;
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
  const [timerStufe, setTimerStufe] = useState("");
  const leer = (): Formular => ({
    datum: heute(),
    bearbeiter_id: einst?.standard_bearbeiter_id ? String(einst.standard_bearbeiter_id) : "",
    stufe_id: "",
    dauer: "",
    von: "",
    bis: "",
    taetigkeit: "",
    abrechenbar: true,
  });
  const [f, setF] = useState<Formular | null>(null);
  const [bearbeitet, setBearbeitet] = useState<number | null>(null);
  const [loeschfrage, setLoeschfrage] = useState<ZeitEintrag | null>(null);
  const [details, setDetails] = useState<number | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
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
    setF(
      (alt) =>
        alt ?? {
          datum: heute(),
          bearbeiter_id: std,
          stufe_id: "",
          dauer: "",
          von: "",
          bis: "",
          taetigkeit: "",
          abrechenbar: true,
        },
    );
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
            stufe_id: timerStufe ? Number(timerStufe) : null,
            taetigkeit,
          }),
        true,
      )
    ) {
      setTaetigkeit("");
      setTimerStufe("");
    }
  }

  async function speichern(e: FormEvent) {
    e.preventDefault();
    if (!f) return;
    const daten = {
      datum: f.datum,
      bearbeiter_id: f.bearbeiter_id ? Number(f.bearbeiter_id) : null,
      stufe_id: f.stufe_id ? Number(f.stufe_id) : null,
      dauer: f.von && f.bis ? "" : f.dauer,
      von: f.von,
      bis: f.bis,
      taetigkeit: f.taetigkeit,
      abrechenbar: f.abrechenbar,
    };
    const ok = await mit(() =>
      kern<ZeitListe>("zeit.speichern", {
        akte_id: akteId,
        daten,
        eintrag_id: bearbeitet,
      }),
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
      stufe_id: "",
      dauer: stundenText(z.laeuft_seit ? 0 : z.minuten),
      von: "",
      bis: "",
      taetigkeit: z.taetigkeit,
      abrechenbar: z.abrechenbar,
    });
  }

  async function exportieren() {
    setFehler(null);
    setMeldung(null);
    const ziel = await save({
      title: "Zeiten exportieren",
      defaultPath: `Zeiten ${new Date().toLocaleDateString("sv-SE")}.xlsx`,
      filters: [
        { name: "Excel", extensions: ["xlsx"] },
        { name: "Tabelle (CSV)", extensions: ["csv"] },
        { name: "PDF (Tätigkeitsnachweis)", extensions: ["pdf"] },
        { name: "Word", extensions: ["docx"] },
      ],
    });
    if (!ziel) return;
    try {
      const r = await kern<{ pfad: string; anzahl: number }>("zeit.exportieren", { akte_id: akteId, pfad: ziel });
      setMeldung(`${r.anzahl} Einträge exportiert nach ${r.pfad}.`);
    } catch (x) {
      setFehler(String(x));
    }
  }

  if (!liste || !einst || !f) {
    return (
      <div className="zeiten">{fehler ? <p className="fehler" role="alert">{fehler}</p> : <p className="status" role="status">Lade …</p>}</div>
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

      {liste.hinweise.map((h) => (
        <p key={h} className="hinweis">
          {h}
        </p>
      ))}

      <ZeitVereinbarung
        akteId={akteId}
        v={liste.vereinbarung}
        anteil={g.budget_anteil}
        taktungen={einst.taktungen}
        onGespeichert={setListe}
        onSchriftstuecke={onKostennote}
      />

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
              <select
                aria-label="Stufe"
                title="Abweichende Stufe nur für diesen Eintrag, z. B. Reisezeit"
                value={timerStufe}
                onChange={(x) => setTimerStufe(x.target.value)}
              >
                <option value="">Stufe wie Bearbeiter</option>
                {einst.stufen.map((st) => (
                  <option key={st.id} value={st.id}>
                    {st.name} · {euro(st.satz)}
                  </option>
                ))}
              </select>
              <input
                className="text"
                placeholder="Tätigkeit, z. B. Klageerwiderung vom 01.12. auf Einwände zum Mangel prüfen"
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
          <label className="feld" title="Abweichende Stufe nur für diesen Eintrag, z. B. Reisezeit">
            Stufe
            <select value={f.stufe_id} onChange={(x) => setF({ ...f, stufe_id: x.target.value })}>
              <option value="">{bearbeitet ? "unverändert" : "wie Bearbeiter"}</option>
              {einst.stufen.map((st) => (
                <option key={st.id} value={st.id}>
                  {st.name} · {euro(st.satz)}
                </option>
              ))}
            </select>
          </label>
          <label className="feld">
            Tätigkeit
            <input
              placeholder="konkret, z. B. Telefonat mit Frau Brückner zur Vergleichsbereitschaft"
              value={f.taetigkeit}
              onChange={(x) => setF({ ...f, taetigkeit: x.target.value })}
            />
          </label>
        </div>
        <div className="notiz-optionen">
          <label>
            <input
              type="checkbox"
              checked={f.abrechenbar}
              onChange={(x) => setF({ ...f, abrechenbar: x.target.checked })}
            />{" "}
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

      {fehler && <p className="fehler" role="alert">{fehler}</p>}
      {meldung && <p className="meldung">{meldung}</p>}
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
        <LeerHinweis symbol="zeiten">Noch keine Zeiten in dieser Akte.</LeerHinweis>
      ) : (
        <section className="karte zeit-liste">
          <div className="kopf">
            <h3>Erfasste Zeiten</h3>
            <span className="leise klein">
              Taktung {liste.taktung === 1 ? "minutengenau" : `${liste.taktung} Min. je Eintrag`}
            </span>
            <button className="zweitrangig klein" onClick={() => void exportieren()}>
              Exportieren …
            </button>
          </div>
          <table className="staffel">
            <thead>
              <tr>
                <th>Datum</th>
                <th>Bearbeiter</th>
                <th>Tätigkeit</th>
                <th className="zahl" title="Erfasst (Stunden:Minuten)">
                  Dauer
                </th>
                <th className="zahl" title="Nach der Taktung">
                  Getaktet
                </th>
                <th className="zahl">Betrag</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {liste.eintraege.map((z) => (
                <Fragment key={z.id}>
                  <tr className={z.kostennote_id ? "abgerechnet" : undefined}>
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
                      {z.notiz && (
                        <button className="status-marke link" title={z.notiz} onClick={() => setDetails(z.id)}>
                          Notiz
                        </button>
                      )}
                      {z.abrechenbar && !z.satz && <span className="status-marke hinweis">ohne Stundensatz</span>}
                    </td>
                    <td className="zahl">{stundenText(z.minuten)}</td>
                    <td className="zahl">{z.abrechenbar ? stundenText(z.getaktet) : ""}</td>
                    <td className="zahl" title={z.satz ? `${euro(z.satz)} je Stunde` : undefined}>
                      {z.betrag ? euro(z.betrag) : ""}
                    </td>
                    <td className="zeit-aktionen">
                      <button
                        className="link klein"
                        aria-expanded={details === z.id}
                        onClick={() => setDetails(details === z.id ? null : z.id)}
                      >
                        Details
                      </button>
                      {!z.kostennote_id && (
                        <>
                          {!z.laeuft_seit && z.datum === heute() && (
                            <button
                              className="link klein"
                              title="Timer für diesen Eintrag weiterlaufen lassen"
                              onClick={() =>
                                void mit(
                                  () =>
                                    kern<ZeitListe>("zeit.starten", {
                                      akte_id: akteId,
                                      eintrag_id: z.id,
                                    }),
                                  true,
                                )
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
                  {details === z.id && (
                    <tr className="zeit-details">
                      <td colSpan={7}>
                        <ZeitDetails
                          z={z}
                          onNotiz={(text) =>
                            mit(() => kern<ZeitListe>("zeit.notiz_speichern", { eintrag_id: z.id, text }))
                          }
                          onVerknuepfen={(notiz_id) =>
                            mit(() => kern<ZeitListe>("zeit.notiz_verknuepfen", { eintrag_id: z.id, notiz_id }))
                          }
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
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
        Bearbeiter und die allgemeine Taktung:{" "}
        <button className="link klein" onClick={onEinstellungen}>
          Einstellungen → Zeiterfassung
        </button>
      </p>
    </div>
  );
}

const uhr = (iso: string) => iso.slice(11, 16);
const zeitpunkt = (iso: string) => `${datumDe(iso.slice(0, 10))}, ${uhr(iso)} Uhr`;

/** Wann erfasst wurde: Timer-Läufe und von–bis von Hand, dazu Anlage und letzte Änderung. */
function ZeitDetails({
  z,
  onNotiz,
  onVerknuepfen,
}: {
  z: ZeitEintrag;
  onNotiz: (text: string) => Promise<boolean>;
  onVerknuepfen: (notizId: number | null) => Promise<boolean>;
}) {
  const [notiz, setNotiz] = useState<string | null>(null);
  // Vorhandene Notizen der Akte zur Auswahl; erst geladen, wenn man verknüpfen will.
  const [auswahl, setAuswahl] = useState<Notiz[] | null>(null);
  const zeiten = z.abschnitte.map((a) => `${uhr(a.von)}–${uhr(a.bis)}`).join(", ");
  const vorlage = `${z.taetigkeit || "Zeiterfassung"}, ${datumDe(z.datum)}${zeiten ? `, ${zeiten} Uhr` : ""} (${z.bearbeiter})\n`;
  const summe = z.abschnitte.reduce(
    (m, a) => m + Math.max(1, Math.round((Date.parse(a.bis) - Date.parse(a.von)) / 60000)),
    0,
  );
  return (
    <div className="zeit-details-inhalt">
      {z.abschnitte.length === 0 && !z.laeuft_seit ? (
        <p className="leise">
          Keine Uhrzeiten: Es wurde nur eine Dauer angegeben (oder der Eintrag stammt aus einer älteren Version).
        </p>
      ) : (
        <ul>
          {z.abschnitte.map((a) => (
            <li key={a.von}>
              {uhr(a.von)}–{uhr(a.bis)} Uhr{" "}
              <span className="leise">({a.quelle === "timer" ? "Timer" : "von Hand"})</span>
            </li>
          ))}
          {z.laeuft_seit && (
            <li>
              seit {uhr(z.laeuft_seit)} Uhr <span className="leise">(Timer läuft)</span>
            </li>
          )}
        </ul>
      )}
      {z.abschnitte.length > 0 &&
        !z.laeuft_seit &&
        summe !== z.minuten &&
        Math.abs(summe - z.minuten) > z.abschnitte.length && (
          <p className="leise">
            Die Dauer wurde von Hand auf {stundenText(z.minuten)} geändert (Zeitspannen ergeben {stundenText(summe)}).
          </p>
        )}
      {notiz !== null ? (
        <form
          className="zeit-notiz"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await onNotiz(notiz)) setNotiz(null);
          }}
        >
          <textarea rows={4} value={notiz} onChange={(e) => setNotiz(e.target.value)} autoFocus />
          <span className="aktionen">
            <button type="submit" disabled={!notiz.trim()}>
              Notiz speichern
            </button>
            <button type="button" className="zweitrangig" onClick={() => setNotiz(null)}>
              Abbrechen
            </button>
          </span>
        </form>
      ) : z.notiz ? (
        <div className="zeit-notiz">
          <p className="notiz-text">{z.notiz}</p>
          <span>
            <button className="link klein" onClick={() => setNotiz(z.notiz ?? "")}>
              Notiz bearbeiten
            </button>
            {" · "}
            <button className="link klein" onClick={() => void onVerknuepfen(null)}>
              Verknüpfung lösen
            </button>
            <span className="leise klein"> · steht auch im Reiter „Notizen“</span>
          </span>
        </div>
      ) : auswahl !== null ? (
        <label className="feld zeit-notiz-wahl">
          Vorhandene Notiz der Akte
          <select
            autoFocus
            defaultValue=""
            onChange={async (e) => {
              if (e.target.value && (await onVerknuepfen(Number(e.target.value)))) setAuswahl(null);
            }}
          >
            <option value="">{auswahl.length ? "– Notiz wählen –" : "Keine Notizen in dieser Akte"}</option>
            {auswahl.map((n) => (
              <option key={n.id} value={n.id}>
                {datumDe(n.angelegt_am.slice(0, 10))} · {n.text.split("\n")[0].slice(0, 80)}
                {n.zeiteintrag ? " (schon mit einer Zeit verknüpft)" : ""}
              </option>
            ))}
          </select>
          <button type="button" className="link klein" onClick={() => setAuswahl(null)}>
            Abbrechen
          </button>
        </label>
      ) : (
        <span>
          <button className="link klein" onClick={() => setNotiz(vorlage)}>
            Notiz dazu
          </button>
          {" · "}
          <button
            className="link klein"
            onClick={() => void kern<Notiz[]>("akten.notizen", { akte_id: z.akte_id }).then(setAuswahl)}
          >
            Vorhandene Notiz verknüpfen
          </button>
        </span>
      )}
      <p className="leise klein">
        Angelegt am {zeitpunkt(z.angelegt_am)}
        {z.geaendert_am !== z.angelegt_am && ` · zuletzt geändert am ${zeitpunkt(z.geaendert_am)}`}
      </p>
    </div>
  );
}
