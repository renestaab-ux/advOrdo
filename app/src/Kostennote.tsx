import { useEffect, useMemo, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import {
  Beteiligung,
  KostenEingabePosten,
  KostennoteEingabe,
  KostennoteEintrag,
  KostennoteErgebnis,
  KostennoteErzeugt,
  KostennoteKatalog,
  KostennoteVorschlag,
  datumDe,
  euro,
  kern,
  satzDe,
} from "./kern";

/** Kernwerte ("1.3") deutsch zum Bearbeiten ("1,3"). */
const de = (t: string) => t.replace(".", ",");

/**
 * Kostennote aus der Akte: Vorschuss (§ 9 RVG) oder Berechnung (§ 10 RVG) mit Gebühren nach VV RVG, Auslagen und
 * Zeitaufwand; Gegenstandswert und Mandant kommen aus der Akte, Briefkopf, Steuernummer und Bankverbindung aus
 * Eigene Daten. Das Ergebnis ist eine Word-Datei in der Akte; die Rechnungsnummer wird dabei vergeben.
 */
export default function Kostennote({
  akteId,
  beteiligte,
  hatVerfahren,
  onGeaendert,
  onDokumente,
  onEigeneDaten,
}: {
  akteId: number;
  beteiligte: Beteiligung[];
  /** Mit Verfahren beginnt die Kostennote mit Verfahrens- und Terminsgebühr, sonst mit der Geschäftsgebühr. */
  hatVerfahren: boolean;
  onGeaendert: () => void;
  onDokumente: () => void;
  onEigeneDaten: () => void;
}) {
  const [katalog, setKatalog] = useState<KostennoteKatalog | null>(null);
  const [vorschlag, setVorschlag] = useState<KostennoteVorschlag | null>(null);
  const [e, setE] = useState<KostennoteEingabe | null>(null);
  const [vorschuesse, setVorschuesse] = useState<string[]>([]);
  const [ergebnis, setErgebnis] = useState<KostennoteErgebnis | null>(null);
  const [rechenfehler, setRechenfehler] = useState<string | null>(null);
  const [erzeugt, setErzeugt] = useState<(KostennoteErzeugt & { geoeffnet: boolean }) | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  async function mit<T>(f: () => Promise<T>): Promise<T | undefined> {
    setFehler(null);
    setLaeuft(true);
    try {
      return await f();
    } catch (x) {
      setFehler(String(x));
      return undefined;
    } finally {
      setLaeuft(false);
    }
  }

  function gebuehr(nr: string, k = katalog): KostenEingabePosten {
    const g = k?.gebuehren.find((x) => x.nr === nr);
    return { typ: "gebuehr", nr, satz: de(g?.satz ?? "1.0") };
  }

  function neu(v: KostennoteVorschlag, k: KostennoteKatalog) {
    setVorschlag(v);
    setVorschuesse(v.offene_vorschuesse.map((o) => o.nummer));
    setE({
      art: "rechnung",
      nummer: v.nummer,
      datum: v.datum,
      auftrag: v.auftrag,
      gegenstandswert: v.gegenstandswert ? de(v.gegenstandswert) : "",
      auftraggeber: 1,
      leistungszeitraum: "",
      empfaenger_id: v.empfaenger_id,
      posten: hatVerfahren ? [gebuehr("3100", k), gebuehr("3104", k)] : [gebuehr("2300", k)],
      anrechnung: null,
      pauschale: true,
      umsatzsteuer: 19,
      abzuege: [],
      zahlungsziel: 14,
    });
  }

  async function laden() {
    const [k, v] = await Promise.all([
      kern<KostennoteKatalog>("kostennote.katalog"),
      kern<KostennoteVorschlag>("kostennote.vorschlag", { akte_id: akteId }),
    ]);
    setKatalog(k);
    neu(v, k);
  }

  useEffect(() => {
    void mit(laden);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [akteId]);

  const mitVerfahrensgebuehr = useMemo(
    () => !!e?.posten.some((p) => p.typ === "gebuehr" && katalog?.anrechnung_auf.includes(p.nr)),
    [e, katalog],
  );

  // Was an den Kern geht: angehakte offene Vorschüsse als Abzug, Anrechnung nur mit Verfahrensgebühr.
  const eingabe = useMemo(() => {
    if (!e || !vorschlag) return null;
    const offen = vorschlag.offene_vorschuesse
      .filter((o) => vorschuesse.includes(o.nummer))
      .map((o) => ({ nummer: o.nummer, text: `Vorschuss Rechnung ${o.nummer} vom ${datumDe(o.datum)}`, betrag: o.betrag }));
    return {
      ...e,
      anrechnung: mitVerfahrensgebuehr ? e.anrechnung : null,
      abzuege: [...offen, ...e.abzuege.filter((a) => a.betrag.trim())],
    };
  }, [e, vorschlag, vorschuesse, mitVerfahrensgebuehr]);

  // Ergebnis sofort mitrechnen.
  useEffect(() => {
    if (!eingabe) return;
    let aktuell = true;
    const t = setTimeout(() => {
      kern<KostennoteErgebnis>("kostennote.berechnen", { eingabe }).then(
        (r) => {
          if (!aktuell) return;
          setErgebnis(r);
          setRechenfehler(null);
        },
        (x) => {
          if (!aktuell) return;
          setErgebnis(null);
          setRechenfehler(String(x));
        },
      );
    }, 250);
    return () => {
      aktuell = false;
      clearTimeout(t);
    };
  }, [eingabe]);

  if (!e || !katalog || !vorschlag) {
    return (
      <section className="karte kostennote">
        <h2>Kostennote</h2>
        {fehler ? <p className="fehler">{fehler}</p> : <p className="leise">Wird geladen …</p>}
      </section>
    );
  }

  const setze = (teil: Partial<KostennoteEingabe>) => setE({ ...e, ...teil });
  const posten = (i: number, p: Partial<KostenEingabePosten>) =>
    setze({ posten: e.posten.map((x, j) => (j === i ? ({ ...x, ...p } as KostenEingabePosten) : x)) });
  const entfernen = (i: number) => setze({ posten: e.posten.filter((_, j) => j !== i) });

  function hinzufuegen(wahl: string) {
    if (!e) return;
    let p: KostenEingabePosten;
    if (wahl === "auslage") p = { typ: "auslage", nr: "7000", text: "", betrag: "", ust: true };
    else if (wahl === "stunden") p = { typ: "stunden", text: "", stunden: "", stundensatz: "" };
    else p = gebuehr(wahl);
    setze({ posten: [...e.posten, p] });
  }

  function anrechnungAn(an: boolean) {
    if (!e) return;
    if (!an) return setze({ anrechnung: null });
    const hier = e.posten.find((p) => p.typ === "gebuehr" && p.nr === "2300");
    const frueher = vorschlag?.geschaeftsgebuehr;
    if (hier && hier.typ === "gebuehr") {
      const plus = Math.min(0.3 * (e.auftraggeber - 1), 2);
      const satz = Number(hier.satz.replace(",", ".")) + plus;
      setze({ anrechnung: { satz: de(String(Math.round(satz * 10) / 10)) } });
    } else if (frueher) {
      setze({ anrechnung: { satz: de(frueher.satz), wert: frueher.wert, nummer: frueher.nummer } });
    } else {
      setze({ anrechnung: { satz: "1,3" } });
    }
  }

  async function inDieAkte() {
    if (!eingabe) return;
    const r = await mit(async () => {
      const x = await kern<KostennoteErzeugt>("kostennote.erzeugen", { akte_id: akteId, eingabe });
      let geoeffnet = false;
      if (x.dokument_id) {
        await kern("akten.extern_bearbeiten", { dokument_id: x.dokument_id });
        geoeffnet = true;
      }
      return { ...x, geoeffnet };
    });
    if (!r) return;
    setErzeugt(r);
    onGeaendert();
    // Nächste Nummer, offene Vorschüsse und Liste neu; die Eingabe bleibt als Ausgangspunkt stehen.
    const v = await kern<KostennoteVorschlag>("kostennote.vorschlag", { akte_id: akteId });
    setVorschlag(v);
    setVorschuesse(v.offene_vorschuesse.map((o) => o.nummer));
    setE((alt) => (alt ? { ...alt, nummer: v.nummer, abzuege: [] } : alt));
  }

  async function alsEntwurf() {
    if (!eingabe) return;
    const ziel = await save({
      title: "Kostennote als Entwurf speichern",
      defaultPath: `Entwurf ${katalog?.arten[e?.art ?? "rechnung"]} ${eingabe.nummer}.docx`.replace(/[\\/:*?"<>|]+/g, " "),
      filters: [{ name: "Word", extensions: ["docx"] }],
    });
    if (!ziel) return;
    const r = await mit(() =>
      kern<KostennoteErzeugt>("kostennote.erzeugen", { akte_id: akteId, eingabe, pfad: ziel, in_akte: false }),
    );
    if (r) setErzeugt({ ...r, geoeffnet: false });
  }

  async function stornieren(k: KostennoteEintrag) {
    if (!window.confirm(`${k.art_text} ${k.nummer} als storniert kennzeichnen? Die Nummer bleibt vergeben.`)) return;
    const r = await mit(() => kern<{ kostennoten: KostennoteEintrag[] }>("kostennote.stornieren", { kostennote_id: k.id }));
    if (!r) return;
    const v = await kern<KostennoteVorschlag>("kostennote.vorschlag", { akte_id: akteId });
    setVorschlag(v);
    setVorschuesse(v.offene_vorschuesse.map((o) => o.nummer));
  }

  async function uebernehmen(k: KostennoteEintrag) {
    const alt = await mit(() => kern<KostennoteEingabe>("kostennote.eingabe", { kostennote_id: k.id }));
    if (!alt || !vorschlag) return;
    setE({ ...alt, nummer: vorschlag.nummer, datum: vorschlag.datum, abzuege: [] });
    setErzeugt(null);
  }

  const gebuehrenNachAngelegenheit = Object.entries(katalog.angelegenheiten).map(([schluessel, titel]) => ({
    titel,
    gebuehren: katalog.gebuehren.filter((g) => g.angelegenheit === schluessel),
  }));
  const anrechnungQuelle = e.posten.some((p) => p.typ === "gebuehr" && p.nr === "2300")
    ? ""
    : e.anrechnung?.nummer
      ? ` aus Rechnung ${e.anrechnung.nummer}`
      : "";

  return (
    <section className="karte kostennote">
      <h2>Kostennote</h2>
      {vorschlag.hinweise.map((h) => (
        <p key={h} className="hinweis">
          {h}{" "}
          {h.includes("Eigene Daten") && (
            <button className="link" onClick={onEigeneDaten}>
              Zu Eigene Daten
            </button>
          )}
        </p>
      ))}

      <div className="schrift-wahl">
        <label className="feld">
          Art
          <select value={e.art} onChange={(x) => setze({ art: x.target.value as KostennoteEingabe["art"] })}>
            <option value="rechnung">Kostennote (Berechnung nach § 10 RVG)</option>
            <option value="vorschuss">Vorschussrechnung (§ 9 RVG)</option>
          </select>
        </label>
        <label className="feld">
          Rechnungsnummer
          <input value={e.nummer} onChange={(x) => setze({ nummer: x.target.value })} />
        </label>
        <label className="feld">
          Rechnungsdatum
          <input type="date" value={e.datum} onChange={(x) => setze({ datum: x.target.value })} />
        </label>
      </div>
      <div className="schrift-wahl">
        <label className="feld">
          Rechnungsempfänger
          <select
            value={e.empfaenger_id ?? ""}
            onChange={(x) => setze({ empfaenger_id: x.target.value ? Number(x.target.value) : null })}
          >
            <option value="">– ohne –</option>
            {beteiligte.map((b) => (
              <option key={b.id} value={b.id}>
                {b.rolle_text}: {b.name}
              </option>
            ))}
          </select>
        </label>
        <label className="feld">
          Auftrag erteilt am
          <input type="date" value={e.auftrag} onChange={(x) => setze({ auftrag: x.target.value })} />
        </label>
        <label className="feld">
          Gegenstandswert (€)
          <input
            inputMode="decimal"
            value={e.gegenstandswert}
            onChange={(x) => setze({ gegenstandswert: x.target.value })}
          />
        </label>
        <label className="feld kurz">
          Auftraggeber
          <input
            type="number"
            min={1}
            value={e.auftraggeber}
            onChange={(x) => setze({ auftraggeber: Math.max(1, Number(x.target.value) || 1) })}
          />
        </label>
      </div>
      <div className="schrift-wahl">
        <label className="feld">
          Leistungszeitraum
          <input
            placeholder="z. B. März bis Oktober 2026"
            value={e.leistungszeitraum}
            onChange={(x) => setze({ leistungszeitraum: x.target.value })}
          />
        </label>
        <label className="feld kurz">
          Zahlungsziel (Tage)
          <input
            type="number"
            min={0}
            value={e.zahlungsziel}
            onChange={(x) => setze({ zahlungsziel: Math.max(0, Number(x.target.value) || 0) })}
          />
        </label>
      </div>

      <h3>Posten</h3>
      <div className="kosten-posten">
        {e.posten.map((p, i) => (
          <div className="kosten-zeile" key={i}>
            {p.typ === "gebuehr" && (
              <>
                <select aria-label="Gebühr" value={p.nr} onChange={(x) => posten(i, { nr: x.target.value })}>
                  {gebuehrenNachAngelegenheit.map((g) => (
                    <optgroup key={g.titel} label={g.titel}>
                      {g.gebuehren.map((x) => (
                        <option key={x.nr} value={x.nr}>
                          Nr. {x.nr} {x.text}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
                <label>
                  Satz
                  <input className="satz" inputMode="decimal" value={p.satz} onChange={(x) => posten(i, { satz: x.target.value })} />
                </label>
                <label>
                  Wert
                  <input
                    className="betrag"
                    inputMode="decimal"
                    placeholder="wie oben"
                    value={p.wert ?? ""}
                    onChange={(x) => posten(i, { wert: x.target.value })}
                  />
                </label>
              </>
            )}
            {p.typ === "auslage" && (
              <>
                <select aria-label="Auslage" value={p.nr} onChange={(x) => posten(i, { nr: x.target.value })}>
                  {katalog.auslagen.map((a) => (
                    <option key={a.nr} value={a.nr}>
                      {a.nr ? `Nr. ${a.nr} ` : ""}
                      {a.text}
                    </option>
                  ))}
                </select>
                <input
                  className="text"
                  placeholder="Bezeichnung (frei)"
                  value={p.text}
                  onChange={(x) => posten(i, { text: x.target.value })}
                />
                <label>
                  Betrag
                  <input className="betrag" inputMode="decimal" value={p.betrag} onChange={(x) => posten(i, { betrag: x.target.value })} />
                </label>
                <label title="Durchlaufender Posten, z. B. verauslagte Gerichtskosten">
                  <input type="checkbox" checked={!p.ust} onChange={(x) => posten(i, { ust: !x.target.checked })} /> ohne USt
                </label>
              </>
            )}
            {p.typ === "stunden" && (
              <>
                <input
                  className="text"
                  placeholder="Tätigkeit, z. B. Besprechung mit Mandantin"
                  value={p.text}
                  onChange={(x) => posten(i, { text: x.target.value })}
                />
                <label>
                  Std.
                  <input className="satz" inputMode="decimal" value={p.stunden} onChange={(x) => posten(i, { stunden: x.target.value })} />
                </label>
                <label>
                  × €/Std.
                  <input
                    className="betrag"
                    inputMode="decimal"
                    value={p.stundensatz}
                    onChange={(x) => posten(i, { stundensatz: x.target.value })}
                  />
                </label>
              </>
            )}
            <button className="link klein gefahr" onClick={() => entfernen(i)} aria-label="Posten entfernen">
              Entfernen
            </button>
          </div>
        ))}
        <select aria-label="Posten hinzufügen" value="" onChange={(x) => x.target.value && hinzufuegen(x.target.value)}>
          <option value="">+ Posten hinzufügen …</option>
          {gebuehrenNachAngelegenheit.map((g) => (
            <optgroup key={g.titel} label={g.titel}>
              {g.gebuehren.map((x) => (
                <option key={x.nr} value={x.nr}>
                  Nr. {x.nr} {x.text}
                </option>
              ))}
            </optgroup>
          ))}
          <optgroup label="Weitere">
            <option value="auslage">Auslage (Nr. 7000 ff. VV RVG oder frei)</option>
            <option value="stunden">Zeitaufwand nach Vergütungsvereinbarung (§ 3a RVG)</option>
          </optgroup>
        </select>
      </div>

      <fieldset className="wahl kosten-wahl">
        {mitVerfahrensgebuehr && (
          <label>
            <input type="checkbox" checked={!!e.anrechnung} onChange={(x) => anrechnungAn(x.target.checked)} /> Geschäftsgebühr
            {anrechnungQuelle} anrechnen (zur Hälfte, höchstens 0,75; Vorbem. 3 Abs. 4 VV RVG), Satz
            {e.anrechnung && (
              <input
                className="satz"
                inputMode="decimal"
                aria-label="Satz der angerechneten Geschäftsgebühr"
                value={e.anrechnung.satz}
                onChange={(x) => setze({ anrechnung: { ...e.anrechnung!, satz: x.target.value } })}
              />
            )}
          </label>
        )}
        <label>
          <input type="checkbox" checked={e.pauschale} onChange={(x) => setze({ pauschale: x.target.checked })} /> Post- und
          Telekommunikationspauschale je Angelegenheit (Nr. 7002 VV RVG)
        </label>
        <label>
          <input
            type="checkbox"
            checked={e.umsatzsteuer > 0}
            onChange={(x) => setze({ umsatzsteuer: x.target.checked ? 19 : 0 })}
          />{" "}
          Umsatzsteuer 19 % (Nr. 7008 VV RVG)
        </label>
        {vorschlag.offene_vorschuesse.map((o) => (
          <label key={o.nummer}>
            <input
              type="checkbox"
              checked={vorschuesse.includes(o.nummer)}
              onChange={(x) =>
                setVorschuesse(x.target.checked ? [...vorschuesse, o.nummer] : vorschuesse.filter((n) => n !== o.nummer))
              }
            />{" "}
            Gezahlten Vorschuss abziehen: Rechnung {o.nummer} vom {datumDe(o.datum)}, {euro(o.betrag)}
          </label>
        ))}
        {e.abzuege.map((a, i) => (
          <div className="kosten-zeile" key={i}>
            <input
              className="text"
              placeholder="Abzug, z. B. Zahlung vom 01.09.2026"
              value={a.text ?? ""}
              onChange={(x) => setze({ abzuege: e.abzuege.map((y, j) => (j === i ? { ...y, text: x.target.value } : y)) })}
            />
            <label>
              Betrag (brutto)
              <input
                className="betrag"
                inputMode="decimal"
                value={a.betrag}
                onChange={(x) => setze({ abzuege: e.abzuege.map((y, j) => (j === i ? { ...y, betrag: x.target.value } : y)) })}
              />
            </label>
            <button className="link klein gefahr" onClick={() => setze({ abzuege: e.abzuege.filter((_, j) => j !== i) })}>
              Entfernen
            </button>
          </div>
        ))}
        <div>
          <button className="link klein" onClick={() => setze({ abzuege: [...e.abzuege, { text: "", betrag: "" }] })}>
            + Weitere Zahlung abziehen
          </button>
        </div>
      </fieldset>

      {rechenfehler && <p className="fehler">{rechenfehler}</p>}
      {ergebnis && <KostenVorschau r={ergebnis} />}

      <div className="aktionen">
        <button disabled={laeuft || !ergebnis || !e.nummer.trim()} onClick={inDieAkte}>
          Erstellen, in die Akte und in Word öffnen
        </button>
        <button className="zweitrangig" disabled={laeuft || !ergebnis} onClick={alsEntwurf}>
          Nur als Entwurf speichern …
        </button>
      </div>
      <p className="leise">
        Beim Erstellen wird die Rechnungsnummer {e.nummer || "–"} vergeben (Muster aus Eigene Daten: {vorschlag.muster}). Ein
        Entwurf vergibt keine Nummer.
      </p>
      {erzeugt && (
        <div className="status schrift-ergebnis">
          {erzeugt.dokument_id ? (
            <>
              „{erzeugt.dateiname}“ liegt jetzt unter Dokumente
              {erzeugt.geoeffnet && " und ist als Arbeitskopie in Word geöffnet"}.{" "}
              <button className="link" onClick={onDokumente}>
                Zu den Dokumenten
              </button>
            </>
          ) : (
            <>Entwurf gespeichert unter {erzeugt.pfad}.</>
          )}
          {erzeugt.leer.length > 0 && <p className="hinweis">Noch leer: {erzeugt.leer.join(", ")}.</p>}
        </div>
      )}
      {fehler && <p className="fehler">{fehler}</p>}

      {vorschlag.kostennoten.length > 0 && (
        <>
          <h3>Rechnungen dieser Akte</h3>
          <ul className="schrift-liste">
            {vorschlag.kostennoten.map((k) => (
              <li key={k.id} className={k.storniert ? "storniert" : undefined}>
                <span>
                  <strong>{k.nummer}</strong> · {k.art_text} vom {datumDe(k.datum)} · {euro(k.brutto)}
                  {k.storniert && " · storniert"}
                </span>
                <span className="aktionen">
                  <button className="link klein" onClick={() => void uebernehmen(k)}>
                    Als Ausgangspunkt
                  </button>
                  {!k.storniert && (
                    <button className="link klein gefahr" onClick={() => void stornieren(k)}>
                      Stornieren
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function KostenVorschau({ r }: { r: KostennoteErgebnis }) {
  const ust = Number(r.umsatzsteuer_satz);
  const zahlen = Number(r.zahlbetrag);
  return (
    <div className="kosten-vorschau">
      {r.hinweise.map((h) => (
        <p key={h} className="hinweis">
          {h}
        </p>
      ))}
      <table className="staffel kosten">
        <thead>
          <tr>
            <th>Nr. VV RVG</th>
            <th>Gebührentatbestand bzw. Auslage</th>
            <th className="zahl">Wert</th>
            <th className="zahl">Satz</th>
            <th className="zahl">Betrag</th>
          </tr>
        </thead>
        {r.abschnitte.map((a) => (
          <tbody key={a.titel}>
            <tr className="abschnitt">
              <td colSpan={5}>{a.titel}</td>
            </tr>
            {a.zeilen.map((z, i) => (
              <tr key={i}>
                <td>{z.nr.replace(/^Nr\. /, "")}</td>
                <td>{z.text}</td>
                <td className="zahl">{z.wert ? euro(z.wert) : ""}</td>
                <td className="zahl">{z.satz ? satzDe(z.satz) : ""}</td>
                <td className="zahl">{euro(z.betrag)}</td>
              </tr>
            ))}
          </tbody>
        ))}
        <tfoot>
          <tr>
            <td colSpan={4}>Summe netto</td>
            <td className="zahl">{euro(r.netto)}</td>
          </tr>
          {ust > 0 && (
            <tr>
              <td colSpan={4}>Umsatzsteuer {r.umsatzsteuer_satz.replace(".", ",")} % (Nr. 7008 VV RVG)</td>
              <td className="zahl">{euro(r.umsatzsteuer)}</td>
            </tr>
          )}
          {r.steuerfrei.map((z, i) => (
            <tr key={i}>
              <td colSpan={4}>{z.text} (ohne Umsatzsteuer)</td>
              <td className="zahl">{euro(z.betrag)}</td>
            </tr>
          ))}
          <tr>
            <td colSpan={4}>Gesamtbetrag</td>
            <td className="zahl">{euro(r.brutto)}</td>
          </tr>
          {r.abzuege.map((a, i) => (
            <tr key={i}>
              <td colSpan={4}>
                abzüglich {a.text}
                {Number(a.ust) ? `, darin USt ${euro(a.ust)}` : ""}
              </td>
              <td className="zahl">{euro(-Number(a.betrag))}</td>
            </tr>
          ))}
          {r.abzuege.length > 0 && (
            <tr>
              <td colSpan={4}>{zahlen >= 0 ? "Noch zu zahlen" : "Zu erstatten"}</td>
              <td className="zahl">{euro(Math.abs(zahlen))}</td>
            </tr>
          )}
        </tfoot>
      </table>
      <p className="grundlagen">
        Gebührentabelle {r.fassung_titel}, maßgeblich ist der Tag des unbedingten Auftrags (§ 60 RVG). Berechnung nach{" "}
        {r.grundlage}.
      </p>
    </div>
  );
}
