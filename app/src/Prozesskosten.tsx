import { useEffect, useState } from "react";
import { KostenAbrechnung, KostenPosten, ProzesskostenErgebnis, drucken, euro, istDesktop, kern, satzDe } from "./kern";

interface Zug {
  instanz: "erste" | "berufung" | "revision";
  an: boolean;
  ende: string;
  termin: boolean;
}

const ZUEGE: { instanz: Zug["instanz"]; titel: string }[] = [
  { instanz: "erste", titel: "Erste Instanz" },
  { instanz: "berufung", titel: "Berufung" },
  { instanz: "revision", titel: "Revision (BGH)" },
];

const ENDEN: [string, string][] = [
  ["urteil", "endet durch Urteil"],
  ["vergleich", "endet durch Vergleich"],
  ["ruecknahme", "endet durch Rücknahme, Anerkenntnis oder Verzicht"],
];

/** Prozesskostenrechner: Gerichtskosten (GKG) und Anwaltskosten (RVG) aus dem Streitwert. */
export default function Prozesskosten() {
  const [streitwert, setStreitwert] = useState("");
  const [fassung, setFassung] = useState("2025");
  const [ust, setUst] = useState(true);
  const [auftraggeber, setAuftraggeber] = useState(1);
  const [vorgerichtlich, setVorgerichtlich] = useState(false);
  const [geschaeft, setGeschaeft] = useState("1,3");
  const [gegner, setGegner] = useState(true);
  const [zuege, setZuege] = useState<Zug[]>(
    ZUEGE.map((z) => ({ instanz: z.instanz, an: z.instanz === "erste", ende: "urteil", termin: true })),
  );
  const [ergebnis, setErgebnis] = useState<ProzesskostenErgebnis | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const aendern = (i: number, z: Partial<Zug>) => setZuege(zuege.map((x, j) => (j === i ? { ...x, ...z } : x)));
  const bereit = istDesktop && streitwert.trim() !== "" && (!vorgerichtlich || geschaeft.trim() !== "");

  useEffect(() => {
    if (!bereit) {
      setErgebnis(null);
      setFehler(null);
      return;
    }
    let gueltig = true;
    const t = setTimeout(() => {
      kern<ProzesskostenErgebnis>("rechner.prozesskosten", {
        streitwert,
        fassung,
        umsatzsteuer: ust ? 19 : null,
        auftraggeber,
        geschaeftsgebuehr: vorgerichtlich ? geschaeft : null,
        gegner,
        rechtszuege: zuege.filter((z) => z.an).map(({ instanz, ende, termin }) => ({ instanz, ende, termin })),
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
  }, [bereit, streitwert, fassung, ust, auftraggeber, vorgerichtlich, geschaeft, gegner, zuege]);

  return (
    <section className="rechner">
      <form className="rechner-formular" onSubmit={(e) => e.preventDefault()}>
        <label>
          Streitwert (€)
          <input
            inputMode="decimal"
            value={streitwert}
            onChange={(e) => setStreitwert(e.target.value)}
            placeholder="z. B. 10.000,00"
          />
        </label>
        <label>
          Gebührenrecht
          <select value={fassung} onChange={(e) => setFassung(e.target.value)}>
            <option value="2025">seit 01.06.2025 (KostBRÄG 2025)</option>
            <option value="2021">01.01.2021 bis 31.05.2025 (KostRÄG 2021)</option>
          </select>
        </label>
        <label>
          Auftraggeber (eigene Seite)
          <input
            type="number"
            min={1}
            value={auftraggeber}
            onChange={(e) => setAuftraggeber(Math.max(1, Number(e.target.value) || 1))}
          />
        </label>

        <fieldset className="posten breit">
          <legend>Rechtszüge</legend>
          {ZUEGE.map((z, i) => (
            <div className="posten-zeile" key={z.instanz}>
              <label className="rechtszug">
                <input
                  type="checkbox"
                  checked={zuege[i].an}
                  disabled={z.instanz === "erste"}
                  onChange={(e) => aendern(i, { an: e.target.checked })}
                />{" "}
                {z.titel}
              </label>
              {zuege[i].an && (
                <>
                  <select
                    aria-label={`Ende ${z.titel}`}
                    value={zuege[i].ende}
                    onChange={(e) => aendern(i, { ende: e.target.value })}
                  >
                    {ENDEN.map(([w, t]) => (
                      <option key={w} value={w}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <label className="rechtszug">
                    <input
                      type="checkbox"
                      checked={zuege[i].termin}
                      onChange={(e) => aendern(i, { termin: e.target.checked })}
                    />{" "}
                    mit Termin
                  </label>
                </>
              )}
            </div>
          ))}
        </fieldset>

        <fieldset className="breit wahl">
          <label>
            <input type="checkbox" checked={vorgerichtlich} onChange={(e) => setVorgerichtlich(e.target.checked)} />{" "}
            Vorgerichtlich tätig (Geschäftsgebühr Nr. 2300 VV RVG, zur Hälfte angerechnet, höchstens 0,75)
            {vorgerichtlich && (
              <input
                className="satz"
                inputMode="decimal"
                aria-label="Satz der Geschäftsgebühr"
                value={geschaeft}
                onChange={(e) => setGeschaeft(e.target.value)}
              />
            )}
          </label>
          <label>
            <input type="checkbox" checked={gegner} onChange={(e) => setGegner(e.target.checked)} /> Gegnerische
            Anwaltskosten einrechnen (Kostenrisiko bei vollem Unterliegen)
          </label>
          <label>
            <input type="checkbox" checked={ust} onChange={(e) => setUst(e.target.checked)} /> Umsatzsteuer 19 % (Nr.
            7008 VV RVG); ausschalten bei Vorsteuerabzug
          </label>
        </fieldset>
      </form>

      {fehler && <p className="fehler">{fehler}</p>}
      {!ergebnis && !fehler && <p className="leer">Streitwert eingeben; das Ergebnis erscheint sofort.</p>}
      {ergebnis && <KostenAusgabe e={ergebnis} />}
    </section>
  );
}

function KostenAusgabe({ e }: { e: ProzesskostenErgebnis }) {
  return (
    <div className="rechner-ergebnis">
      <div className="kopf">
        <h2>Kostenrisiko: {euro(e.kostenrisiko)}</h2>
        <button className="zweitrangig nicht-drucken" onClick={() => void drucken()}>
          Drucken …
        </button>
      </div>
      <dl className="summen">
        <dt>Streitwert</dt>
        <dd>{euro(e.streitwert)}</dd>
        <dt>Gerichtskosten</dt>
        <dd>{euro(e.summe_gericht)}</dd>
        <dt>Eigene Anwaltskosten</dt>
        <dd>{euro(e.summe_eigene)}</dd>
        {e.gegner.length > 0 && (
          <>
            <dt>Gegnerische Anwaltskosten</dt>
            <dd>{euro(e.summe_gegner)}</dd>
          </>
        )}
        <dt className="gesamt">Summe</dt>
        <dd className="gesamt">{euro(e.kostenrisiko)}</dd>
        <dt>Volle Gebühr (1,0)</dt>
        <dd>
          GKG {euro(e.gebuehr_gkg)} · RVG {euro(e.gebuehr_rvg)}
        </dd>
      </dl>
      {e.hinweise.map((h) => (
        <p key={h} className="hinweis">
          {h}
        </p>
      ))}

      <h3>Gerichtskosten</h3>
      <PostenTabelle posten={e.gericht} summe={e.summe_gericht} />
      <h3>Eigene Anwaltskosten</h3>
      {e.vorgerichtlich && <Abrechnung a={e.vorgerichtlich} />}
      {e.eigene.map((a) => (
        <Abrechnung key={a.titel} a={a} />
      ))}
      {e.gegner.length > 0 && (
        <>
          <h3>Gegnerische Anwaltskosten</h3>
          {e.gegner.map((a) => (
            <Abrechnung key={a.titel} a={a} />
          ))}
        </>
      )}
      <p className="grundlagen">
        Gebührenrecht {e.fassung_titel}. Grundlage: {e.grundlagen.join(", ")}. Maßgeblich ist beim Anwalt der Tag des
        unbedingten Auftrags (§ 60 RVG), bei den Gerichtskosten die Anhängigkeit des Rechtszugs (§ 71 GKG). Jede Gebühr
        ist auf den Cent gerundet, mindestens 15 €. Nicht enthalten: Auslagen des Gerichts (Zeugen, Sachverständige),
        Reisekosten, Mahnverfahren und Beweisverfahren. Ohne Gewähr.
      </p>
    </div>
  );
}

function Abrechnung({ a }: { a: KostenAbrechnung }) {
  return <PostenTabelle titel={a.titel} posten={a.posten} summe={a.summe} />;
}

function PostenTabelle({ titel, posten, summe }: { titel?: string; posten: KostenPosten[]; summe: string }) {
  return (
    <table className="staffel kosten">
      {titel && <caption>{titel}</caption>}
      <thead>
        <tr>
          <th>Nr.</th>
          <th>Gebühr</th>
          <th className="zahl">Satz</th>
          <th className="zahl">Betrag</th>
        </tr>
      </thead>
      <tbody>
        {posten.map((p) => (
          <tr key={p.nr + p.text}>
            <td>{p.nr}</td>
            <td>{p.text}</td>
            <td className="zahl">{p.satz ? satzDe(p.satz) : ""}</td>
            <td className="zahl">{euro(p.betrag)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <td colSpan={3}>Summe</td>
          <td className="zahl">{euro(summe)}</td>
        </tr>
      </tfoot>
    </table>
  );
}
