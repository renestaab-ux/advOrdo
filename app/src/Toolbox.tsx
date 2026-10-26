import { FormEvent, Fragment, useEffect, useState } from "react";
import {
  BUNDESLAENDER,
  BasiszinsStand,
  FristErgebnis,
  ZinsErgebnis,
  datumDe,
  euro,
  heuteIso,
  istDesktop,
  drucken,
  kern,
  prozent,
} from "./kern";
import Prozesskosten from "./Prozesskosten";

type Werkzeug = "zinsen" | "fristen" | "kosten";

const WERKZEUGE: { id: Werkzeug; titel: string; bald?: boolean }[] = [
  { id: "zinsen", titel: "Verzugszinsen" },
  { id: "fristen", titel: "Fristen" },
  { id: "kosten", titel: "Prozesskosten" },
];

/** Die Toolbox: Rechner aus JuraBox Lite, in einem eigenen Fenster. */
export default function Toolbox() {
  const [werkzeug, setWerkzeug] = useState<Werkzeug>("zinsen");
  return (
    <div className="toolbox">
      <header className="toolbox-kopf">
        <h1>Toolbox</h1>
        <nav className="toolbox-reiter" aria-label="Werkzeuge">
          {WERKZEUGE.map((w) => (
            <button
              key={w.id}
              className={w.id === werkzeug ? "reiter aktiv" : "reiter"}
              onClick={() => setWerkzeug(w.id)}
              disabled={w.bald}
              title={w.bald ? "Folgt in einem späteren Schritt" : undefined}
            >
              {w.titel}
              {w.bald && <span className="bald">bald</span>}
            </button>
          ))}
        </nav>
      </header>
      {!istDesktop && (
        <p className="hinweis-box">
          Die Rechner laufen im Analysekern und stehen nur in der Desktop-App zur Verfügung:{" "}
          <code>npm run tauri dev</code>
        </p>
      )}
      {werkzeug === "zinsen" && <Verzugszinsen />}
      {werkzeug === "fristen" && <Fristen />}
      {werkzeug === "kosten" && <Prozesskosten />}
    </div>
  );
}

interface Posten {
  datum: string;
  betrag: string;
}

const ARTEN: [string, string][] = [
  ["verbraucher", "Verbraucher beteiligt (§ 288 Abs. 1 BGB, + 5 Punkte)"],
  ["entgelt", "Entgeltforderung ohne Verbraucher (§ 288 Abs. 2 BGB, + 9 Punkte)"],
  ["dauerschuld", "Dauerschuldverhältnis über den 29.07.2014 hinweg (+ 8, dann + 9)"],
  ["dynamisch", "Basiszinssatz + eigene Punkte"],
  ["fest", "Fester Zinssatz"],
];

const METHODEN: [string, string][] = [
  ["act/act", "kalendergenau (act/act)"],
  ["act/365", "act/365"],
  ["act/360", "act/360"],
  ["act/365.25", "act/365,25"],
  ["act/366", "act/366"],
  ["30E/360", "30E/360 (Monat zu 30 Tagen)"],
];

function Verzugszinsen() {
  const [hauptbetrag, setHauptbetrag] = useState("");
  const [beginn, setBeginn] = useState("");
  const [ende, setEnde] = useState(heuteIso());
  const [art, setArt] = useState("verbraucher");
  const [punkte, setPunkte] = useState("5");
  const [festerSatz, setFesterSatz] = useState("5");
  const [methode, setMethode] = useState("act/act");
  const [verrechnung, setVerrechnung] = useState("zinsen_zuerst");
  const [pauschalen, setPauschalen] = useState(0);
  const [zugaenge, setZugaenge] = useState<Posten[]>([]);
  const [zahlungen, setZahlungen] = useState<Posten[]>([]);
  const [rate, setRate] = useState<Posten>({ datum: "", betrag: "" });
  const [ergebnis, setErgebnis] = useState<ZinsErgebnis | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const vollstaendig = (p: Posten) => p.datum && p.betrag.trim();
  const bereit = istDesktop && hauptbetrag.trim() !== "" && beginn !== "" && ende !== "";

  // Ergebnis schon beim Eingeben, kurz verzögert.
  useEffect(() => {
    if (!bereit) {
      setErgebnis(null);
      return;
    }
    let gueltig = true;
    const t = setTimeout(() => {
      kern<ZinsErgebnis>("rechner.verzugszinsen", {
        hauptbetrag,
        beginn,
        ende,
        art,
        punkte: punkte || "0",
        fester_satz: festerSatz || "0",
        methode,
        verrechnung,
        pauschalen,
        zugaenge: zugaenge.filter(vollstaendig),
        teilzahlungen: zahlungen.filter(vollstaendig),
        rate: vollstaendig(rate) ? { betrag: rate.betrag, erstes: rate.datum } : null,
      }).then(
        (e) => {
          if (!gueltig) return;
          setErgebnis(e);
          setFehler(null);
        },
        (f) => {
          if (!gueltig) return;
          setErgebnis(null);
          setFehler(String(f));
        },
      );
    }, 300);
    return () => {
      gueltig = false;
      clearTimeout(t);
    };
  }, [
    bereit,
    hauptbetrag,
    beginn,
    ende,
    art,
    punkte,
    festerSatz,
    methode,
    verrechnung,
    pauschalen,
    zugaenge,
    zahlungen,
    rate,
  ]);

  const zahlungenDa = zahlungen.some(vollstaendig) || vollstaendig(rate);
  return (
    <section className="rechner">
      <form className="rechner-formular" onSubmit={(e) => e.preventDefault()}>
        <label>
          Hauptforderung (€)
          <input
            inputMode="decimal"
            value={hauptbetrag}
            onChange={(e) => setHauptbetrag(e.target.value)}
            placeholder="z. B. 1.250,00"
          />
        </label>
        <label>
          Zinsen ab (erster Zinstag)
          <input type="date" value={beginn} onChange={(e) => setBeginn(e.target.value)} />
        </label>
        <label>
          Zinsen bis einschließlich
          <input type="date" value={ende} onChange={(e) => setEnde(e.target.value)} />
        </label>
        <label className="breit">
          Zinssatz
          <select value={art} onChange={(e) => setArt(e.target.value)}>
            {ARTEN.map(([w, t]) => (
              <option key={w} value={w}>
                {t}
              </option>
            ))}
          </select>
        </label>
        {art === "dynamisch" && (
          <label>
            Prozentpunkte über dem Basiszinssatz
            <input inputMode="decimal" value={punkte} onChange={(e) => setPunkte(e.target.value)} />
          </label>
        )}
        {art === "fest" && (
          <label>
            Zinssatz (% p. a.)
            <input inputMode="decimal" value={festerSatz} onChange={(e) => setFesterSatz(e.target.value)} />
          </label>
        )}
        <label>
          Zinsmethode
          <select value={methode} onChange={(e) => setMethode(e.target.value)}>
            {METHODEN.map(([w, t]) => (
              <option key={w} value={w}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label>
          Verzugspauschalen à 40 € (§ 288 Abs. 5 BGB)
          <input
            type="number"
            min={0}
            value={pauschalen}
            onChange={(e) => setPauschalen(Math.max(0, Number(e.target.value) || 0))}
          />
        </label>

        <PostenListe titel="Weitere Forderungen" posten={zugaenge} setPosten={setZugaenge} />
        <PostenListe titel="Teilzahlungen" posten={zahlungen} setPosten={setZahlungen} />
        <fieldset className="posten breit">
          <legend>Monatliche Ratenzahlung</legend>
          <div className="posten-zeile">
            <input
              type="date"
              aria-label="Erste Rate am"
              value={rate.datum}
              onChange={(e) => setRate({ ...rate, datum: e.target.value })}
            />
            <input
              inputMode="decimal"
              aria-label="Rate in Euro"
              placeholder="Rate in €"
              value={rate.betrag}
              onChange={(e) => setRate({ ...rate, betrag: e.target.value })}
            />
            <span className="leer">jeden Monat am selben Tag bis zum Ende</span>
          </div>
        </fieldset>
        {zahlungenDa && (
          <label className="breit">
            Verrechnung der Zahlungen
            <select value={verrechnung} onChange={(e) => setVerrechnung(e.target.value)}>
              <option value="zinsen_zuerst">
                zuerst auf die Zinsen, dann auf die Hauptforderung (§ 367 Abs. 1 BGB)
              </option>
              <option value="hauptschuld_zuerst">
                zuerst auf die Hauptforderung (§ 497 Abs. 3 BGB, Verbraucherdarlehen)
              </option>
            </select>
          </label>
        )}
      </form>

      {fehler && <p className="fehler">{fehler}</p>}
      {!ergebnis && !fehler && (
        <p className="leer">Hauptforderung und ersten Zinstag eingeben; das Ergebnis erscheint sofort.</p>
      )}
      {ergebnis && <ZinsAusgabe e={ergebnis} />}
      <BasiszinsVerwaltung />
    </section>
  );
}

function PostenListe({
  titel,
  posten,
  setPosten,
}: {
  titel: string;
  posten: Posten[];
  setPosten: (p: Posten[]) => void;
}) {
  const aendern = (i: number, p: Posten) => setPosten(posten.map((x, j) => (j === i ? p : x)));
  return (
    <fieldset className="posten breit">
      <legend>{titel}</legend>
      {posten.map((p, i) => (
        <div className="posten-zeile" key={i}>
          <input
            type="date"
            aria-label="Datum"
            value={p.datum}
            onChange={(e) => aendern(i, { ...p, datum: e.target.value })}
          />
          <input
            inputMode="decimal"
            aria-label="Betrag in Euro"
            placeholder="Betrag in €"
            value={p.betrag}
            onChange={(e) => aendern(i, { ...p, betrag: e.target.value })}
          />
          <button type="button" className="link" onClick={() => setPosten(posten.filter((_, j) => j !== i))}>
            entfernen
          </button>
        </div>
      ))}
      <button type="button" className="zweitrangig" onClick={() => setPosten([...posten, { datum: "", betrag: "" }])}>
        + hinzufügen
      </button>
    </fieldset>
  );
}

/** Ergebnis des Zinsrechners; auch im KI-Chat, dort ohne Drucken. */
export function ZinsAusgabe({ e, mitDruck = true }: { e: ZinsErgebnis; mitDruck?: boolean }) {
  return (
    <div className="rechner-ergebnis">
      <div className="kopf">
        <h2>Ergebnis</h2>
        {mitDruck && (
          <button className="zweitrangig nicht-drucken" onClick={() => void drucken()}>
            Drucken …
          </button>
        )}
      </div>
      <dl className="summen">
        <dt>Offene Hauptforderung</dt>
        <dd>{euro(e.hauptforderung)}</dd>
        <dt>Offene Zinsen</dt>
        <dd>{euro(e.offene_zinsen)}</dd>
        {Number(e.pauschale) > 0 && (
          <>
            <dt>Verzugspauschale</dt>
            <dd>{euro(e.pauschale)}</dd>
          </>
        )}
        <dt className="gesamt">Gesamtforderung</dt>
        <dd className="gesamt">{euro(e.gesamt)}</dd>
        <dt>Zinsen je weiteren Tag</dt>
        <dd>
          {euro(e.zinsen_pro_tag, 4)} (zuletzt {prozent(e.aktueller_satz)})
        </dd>
      </dl>
      {e.hinweise.map((h) => (
        <p key={h} className="hinweis">
          {h}
        </p>
      ))}
      <table className="staffel">
        <thead>
          <tr>
            <th>von</th>
            <th>bis</th>
            <th>Tage</th>
            <th>Zinssatz</th>
            <th>Restschuld</th>
            <th>Zinsen</th>
            <th>Zinssaldo</th>
          </tr>
        </thead>
        <tbody>
          {e.zeilen.map((z) => (
            <Fragment key={z.von}>
              {z.ereignis && (
                <tr className="ereignis">
                  <td colSpan={7}>{z.ereignis}</td>
                </tr>
              )}
              <tr>
                <td>{datumDe(z.von)}</td>
                <td>{datumDe(z.bis)}</td>
                <td className="zahl">{z.tage}</td>
                <td className="zahl" title={z.grundlage}>
                  {prozent(z.satz)}
                </td>
                <td className="zahl">{euro(z.restschuld)}</td>
                <td className="zahl">{euro(z.zinsen, 4)}</td>
                <td className="zahl">{euro(z.zinssaldo, 4)}</td>
              </tr>
            </Fragment>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={2}>Summe</td>
            <td className="zahl">{e.summe_tage}</td>
            <td colSpan={2} />
            <td className="zahl">{euro(e.summe_zinsen_genau, 4)}</td>
            <td />
          </tr>
        </tfoot>
      </table>
      <p className="grundlagen">
        Grundlage: {e.grundlagen.length ? e.grundlagen.join(", ") : "vereinbarter fester Zinssatz"}. Basiszinssatz laut
        Deutscher Bundesbank, zuletzt hinterlegt ab {e.basiszins_quelle}. Gerechnet wird ungerundet (Zeilen mit vier
        Nachkommastellen); auf den Cent gerundet sind nur die Endbeträge. Zahlungen wirken ab dem Folgetag; kein
        Zinseszins. Ohne Gewähr.
      </p>
    </div>
  );
}

function BasiszinsVerwaltung() {
  const [stand, setStand] = useState<BasiszinsStand | null>(null);
  const [ab, setAb] = useState("");
  const [satz, setSatz] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    if (istDesktop) void kern<BasiszinsStand>("rechner.basiszins").then(setStand, (f) => setFehler(String(f)));
  }, []);

  async function eintragen(e: FormEvent) {
    e.preventDefault();
    try {
      setStand(await kern<BasiszinsStand>("rechner.basiszins_eintragen", { ab, satz }));
      setAb("");
      setSatz("");
      setFehler(null);
    } catch (f) {
      setFehler(String(f));
    }
  }

  if (!stand) return null;
  const eigene = stand.saetze.filter((s) => s.eigen);
  return (
    <details className="basiszins nicht-drucken">
      <summary>
        Basiszinssatz: aktuell {prozent(stand.aktuell.satz)} seit {datumDe(stand.aktuell.ab)} (hinterlegt bis{" "}
        {datumDe(stand.bekannt_bis)})
      </summary>
      <p className="leer">
        Quelle: {stand.quelle}, Tabelle Stand {stand.stand}. Sobald die Bundesbank einen neuen Satz bekannt gibt (zum 1.
        Januar und 1. Juli), lässt er sich hier ergänzen. Hinterlegte Sätze werden nie überschrieben.
      </p>
      {eigene.length > 0 && (
        <ul>
          {eigene.map((s) => (
            <li key={s.ab}>
              ab {datumDe(s.ab)}: {prozent(s.satz)} (selbst eingetragen){" "}
              <button
                className="link"
                onClick={() => void kern<BasiszinsStand>("rechner.basiszins_entfernen", { ab: s.ab }).then(setStand)}
              >
                entfernen
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="posten-zeile" onSubmit={eintragen}>
        <input type="date" aria-label="Gültig ab" value={ab} onChange={(e) => setAb(e.target.value)} />
        <input
          inputMode="decimal"
          aria-label="Satz in Prozent"
          placeholder="Satz in %, z. B. 1,52"
          value={satz}
          onChange={(e) => setSatz(e.target.value)}
        />
        <button type="submit" className="zweitrangig" disabled={!ab || !satz.trim()}>
          Satz ergänzen
        </button>
      </form>
      {fehler && <p className="fehler">{fehler}</p>}
    </details>
  );
}

export function gespeichertesLand(): string {
  try {
    return localStorage.getItem("toolbox.land") ?? "BY";
  } catch {
    return "BY";
  }
}

function Fristen() {
  const [bezugstag, setBezugstag] = useState(heuteIso());
  const [beginn, setBeginn] = useState("ereignis");
  const [anzahl, setAnzahl] = useState(2);
  const [einheit, setEinheit] = useState("wochen");
  const [p193, setP193] = useState(true);
  const [land, setLand] = useState(gespeichertesLand);
  const [ergebnis, setErgebnis] = useState<FristErgebnis | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem("toolbox.land", land);
    } catch {
      // ohne Speicher gilt beim nächsten Mal wieder Bayern
    }
  }, [land]);

  useEffect(() => {
    if (!istDesktop || !bezugstag || anzahl < 1) {
      setErgebnis(null);
      return;
    }
    let gueltig = true;
    kern<FristErgebnis>("rechner.frist", {
      bezugstag,
      anzahl,
      einheit,
      beginn,
      paragraf_193: p193,
      land: land === "BY-ohne" ? "BY" : land,
      maria_himmelfahrt_bayern: land === "BY",
    }).then(
      (e) => {
        if (!gueltig) return;
        setErgebnis(e);
        setFehler(null);
      },
      (f) => gueltig && setFehler(String(f)),
    );
    return () => {
      gueltig = false;
    };
  }, [bezugstag, beginn, anzahl, einheit, p193, land]);

  return (
    <section className="rechner">
      <form className="rechner-formular" onSubmit={(e) => e.preventDefault()}>
        <label>
          Fristauslösendes Ereignis am
          <input type="date" value={bezugstag} onChange={(e) => setBezugstag(e.target.value)} />
        </label>
        <label>
          Dauer
          <span className="posten-zeile">
            <input type="number" min={1} value={anzahl} onChange={(e) => setAnzahl(Number(e.target.value) || 0)} />
            <select value={einheit} onChange={(e) => setEinheit(e.target.value)} aria-label="Einheit">
              <option value="tage">Tage</option>
              <option value="wochen">Wochen</option>
              <option value="monate">Monate</option>
              <option value="jahre">Jahre</option>
            </select>
          </span>
        </label>
        <label>
          Bundesland (Feiertage)
          <select value={land} onChange={(e) => setLand(e.target.value)}>
            {BUNDESLAENDER.flatMap(([k, n]) =>
              // Mariä Himmelfahrt ist in Bayern nur in überwiegend katholischen Gemeinden Feiertag.
              k === "BY"
                ? [
                    <option key="BY" value="BY">
                      Bayern, mit 15. August (kath. Gemeinden)
                    </option>,
                    <option key="BY-ohne" value="BY-ohne">
                      Bayern, ohne 15. August (übrige Gemeinden)
                    </option>,
                  ]
                : [
                    <option key={k} value={k}>
                      {n}
                    </option>,
                  ],
            )}
          </select>
        </label>
        <fieldset className="breit wahl">
          <label>
            <input type="radio" checked={beginn === "ereignis"} onChange={() => setBeginn("ereignis")} /> Ereignisfrist:
            der Tag des Ereignisses zählt nicht mit (§ 187 Abs. 1 BGB, z. B. Zustellung)
          </label>
          <label>
            <input type="radio" checked={beginn === "tagesbeginn"} onChange={() => setBeginn("tagesbeginn")} /> Beginn
            eines Tages: der Tag zählt mit (§ 187 Abs. 2 BGB, z. B. Lebensalter, Vertragsbeginn)
          </label>
          <label>
            <input type="checkbox" checked={p193} onChange={(e) => setP193(e.target.checked)} /> Fristende an Samstag,
            Sonntag oder Feiertag auf den nächsten Werktag verschieben (§ 193 BGB, § 222 Abs. 2 ZPO)
          </label>
        </fieldset>
      </form>
      {fehler && <p className="fehler">{fehler}</p>}
      {ergebnis && <FristAusgabe e={ergebnis} />}
    </section>
  );
}

/** Ergebnis des Fristenrechners; auch im KI-Chat, dort ohne Drucken. */
export function FristAusgabe({ e, mitDruck = true }: { e: FristErgebnis; mitDruck?: boolean }) {
  return (
    <div className="rechner-ergebnis">
      <div className="kopf">
        <h2>
          Fristende: {e.wochentag}, {datumDe(e.ende)}
        </h2>
        {mitDruck && (
          <button className="zweitrangig nicht-drucken" onClick={() => void drucken()}>
            Drucken …
          </button>
        )}
      </div>
      <dl className="summen">
        <dt>Ereignis</dt>
        <dd>
          {e.wochentag_bezugstag}, {datumDe(e.bezugstag)}
        </dd>
        <dt>Fristbeginn</dt>
        <dd>
          {e.wochentag_fristbeginn}, {datumDe(e.fristbeginn)}
        </dd>
        <dt>Rechnerisches Ende</dt>
        <dd>
          {e.wochentag_rechnerisch}, {datumDe(e.rechnerisches_ende)}
        </dd>
        {e.verschoben && (
          <>
            <dt>Verschoben wegen</dt>
            <dd>{e.grund}</dd>
          </>
        )}
      </dl>
      {e.hinweise.map((h) => (
        <p key={h} className="hinweis">
          {h}
        </p>
      ))}
      <p className="grundlagen">
        Grundlage: {e.grundlagen.join(", ")}. Feiertage: {e.land}, ohne örtliche Sonderfeiertage wie
        das Augsburger Friedensfest (Stand {e.feiertage_stand}). Rückwärtsfristen (z. B. Ladungsfristen)
        rechnet dieses Werkzeug nicht. Ohne Gewähr.
      </p>
    </div>
  );
}
