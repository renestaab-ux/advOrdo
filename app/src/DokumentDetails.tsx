import { FormEvent, useEffect, useState } from "react";
import {
  BETEILIGTE,
  DokumentMetadaten,
  MetaFundstelle,
  MetaVerlaufEintrag,
  datumDe,
  kern,
  sortiereTags,
  tagsAusText,
  zeitpunkt,
} from "./kern";
import Notizen from "./Notizen";

/** Bearbeitungsstand der Felder; gespeichert wird erst mit „Speichern“. */
interface Entwurf {
  titel: string;
  art: string;
  /** "" = nicht angegeben, "eigene" oder die Nummer der Beteiligung als Text. */
  absender: string;
  datum: string;
  schlagworte: string[];
  beteiligte: number[];
}

function ausMeta(m: DokumentMetadaten): Entwurf {
  return {
    titel: m.titel,
    art: m.art,
    absender: m.absender ? String(m.absender.wert) : "",
    datum: m.datum.wert ?? "",
    schlagworte: m.schlagworte.map((t) => t.name),
    beteiligte: m.beteiligte.map((b) => b.id),
  };
}

const gleicheListe = <T,>(a: T[], b: T[]) => a.length === b.length && [...a].sort().every((x, i) => x === [...b].sort()[i]);
const enthaelt = (liste: string[], wert: string) =>
  liste.some((x) => x.toLocaleLowerCase("de") === wert.toLocaleLowerCase("de"));

const DATUM_HERKUNFT: Record<string, string> = {
  dokument: "aus der Datumszeile im Dokument",
  word: "zuletzt gespeichert laut Word",
  datei: "Dateidatum",
  manuell: "von Hand eingetragen",
};

/**
 * Ansicht „Details“ eines Dokuments: Titel, Art, Absender, Datum, Schlagworte, Beteiligte und Notizen, dazu der Verlauf.
 * Was der Kern im Text erkennt, steht als Vorschlag mit Fundstelle daneben und wird nur auf Klick übernommen.
 */
export default function DokumentDetails({
  akteId,
  dokumentId,
  onGespeichert,
  onFundstelle,
}: {
  akteId: number;
  dokumentId: number;
  /** Nach dem Speichern: Dokumentliste und Kopf neu laden (Titel, Datum, Tags). */
  onGespeichert: () => void;
  /** Öffnet den Text des Dokuments an der Fundstelle eines Vorschlags. */
  onFundstelle: (abschnitt: number) => void;
}) {
  const [meta, setMeta] = useState<DokumentMetadaten | null>(null);
  const [entwurf, setEntwurf] = useState<Entwurf | null>(null);
  const [neuesWort, setNeuesWort] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [gespeichert, setGespeichert] = useState(false);

  useEffect(() => {
    setMeta(null);
    setEntwurf(null);
    setFehler(null);
    setGespeichert(false);
    kern<DokumentMetadaten>("akten.metadaten", { dokument_id: dokumentId }).then(
      (m) => {
        setMeta(m);
        setEntwurf(ausMeta(m));
      },
      (e) => setFehler(String(e)),
    );
  }, [dokumentId]);

  if (!meta || !entwurf) return fehler ? <p className="fehler">{fehler}</p> : <p className="leer">Lade Details …</p>;

  const bisher = ausMeta(meta);
  const geaendert = {
    titel: entwurf.titel.trim() !== bisher.titel,
    art: entwurf.art.trim() !== bisher.art,
    absender: entwurf.absender !== bisher.absender,
    datum: entwurf.datum !== bisher.datum,
    schlagworte: !gleicheListe(entwurf.schlagworte, bisher.schlagworte),
    beteiligte: !gleicheListe(entwurf.beteiligte, bisher.beteiligte),
  };
  const offen = Object.values(geaendert).some(Boolean);
  const aendere = (teil: Partial<Entwurf>) => {
    setEntwurf({ ...entwurf, ...teil });
    setGespeichert(false);
  };

  async function speichern(e?: FormEvent) {
    e?.preventDefault();
    if (!entwurf || !meta) return;
    const erkannt = meta.datum.erkannt?.datum;
    const params: Record<string, unknown> = { dokument_id: dokumentId };
    if (geaendert.titel) params.titel = entwurf.titel.trim();
    if (geaendert.art) params.art = entwurf.art.trim();
    if (geaendert.absender)
      params.absender = entwurf.absender === "" || entwurf.absender === "eigene" ? entwurf.absender : Number(entwurf.absender);
    // Wer das erkannte Datum wieder wählt, kehrt zur Erkennung zurück (auch nach einer neuen Fassung).
    if (geaendert.datum) params.datum = erkannt && entwurf.datum === erkannt ? "" : entwurf.datum;
    if (geaendert.schlagworte) params.schlagworte = entwurf.schlagworte;
    if (geaendert.beteiligte) params.beteiligte = entwurf.beteiligte;
    setLaeuft(true);
    setFehler(null);
    try {
      const m = await kern<DokumentMetadaten>("akten.metadaten_speichern", params);
      setMeta(m);
      setEntwurf(ausMeta(m));
      setGespeichert(true);
      onGespeichert();
    } catch (fehler) {
      setFehler(String(fehler));
    } finally {
      setLaeuft(false);
    }
  }

  function wortHinzufuegen(text: string) {
    const neu = tagsAusText(text).filter((w) => !enthaelt(entwurf!.schlagworte, w));
    if (neu.length) aendere({ schlagworte: [...entwurf!.schlagworte, ...neu] });
    setNeuesWort("");
  }

  const v = meta.vorschlaege;
  const titelVorschlaege = v.titel.filter((t) => t.wert !== entwurf.titel.trim());
  const wortVorschlaege = v.schlagworte.filter((t) => !enthaelt(entwurf.schlagworte, t.wert));
  const vorgeschlagen = new Map(v.beteiligte.map((b) => [b.beteiligung_id, b]));
  const datumVorschlag = v.datum && v.datum.wert !== entwurf.datum ? v.datum : null;
  const artVorschlag = v.art && v.art.wert !== entwurf.art.trim() ? v.art : null;
  const absenderVorschlag = v.absender && String(v.absender.wert) !== entwurf.absender ? v.absender : null;

  return (
    <div className="dok-details">
      <form className="karte dok-details-felder" onSubmit={speichern}>
        <div className="feld">
          <label htmlFor="meta-titel">Titel</label>
          <input
            id="meta-titel"
            value={entwurf.titel}
            onChange={(e) => aendere({ titel: e.target.value })}
            placeholder={meta.dateiname}
            maxLength={200}
          />
          <span className="feld-hinweis">
            Steht in der Dokumentliste vor dem Dateinamen. Leer lassen, um den Dateinamen ({meta.dateiname}) zu zeigen.
          </span>
          {titelVorschlaege.map((t) => (
            <Vorschlag
              key={t.wert}
              wert={t.wert}
              grund={t.grund}
              fundstelle={t.fundstelle}
              onFundstelle={onFundstelle}
              onUebernehmen={() => aendere({ titel: t.wert })}
            />
          ))}
        </div>

        <div className="meta-zeile">
          <div className="feld">
            <label htmlFor="meta-art">Art</label>
            <input
              id="meta-art"
              list="meta-arten"
              value={entwurf.art}
              onChange={(e) => aendere({ art: e.target.value })}
              placeholder="z. B. Schriftsatz"
              maxLength={60}
            />
            <datalist id="meta-arten">
              {meta.arten.map((a) => (
                <option key={a} value={a} />
              ))}
            </datalist>
            {artVorschlag && (
              <Vorschlag
                wert={artVorschlag.wert}
                grund={artVorschlag.grund}
                fundstelle={artVorschlag.fundstelle}
                onFundstelle={onFundstelle}
                onUebernehmen={() => aendere({ art: artVorschlag.wert })}
              />
            )}
          </div>
          <div className="feld">
            <label htmlFor="meta-absender">Absender (wer hat es erstellt?)</label>
            <select id="meta-absender" value={entwurf.absender} onChange={(e) => aendere({ absender: e.target.value })}>
              <option value="">(nicht angegeben)</option>
              <option value="eigene">Wir (eigene Seite)</option>
              {meta.akte_beteiligte.map((b) => (
                <option key={b.id} value={String(b.id)}>
                  {b.name} · {b.rolle_text}
                </option>
              ))}
            </select>
            {absenderVorschlag && (
              <Vorschlag
                wert={absenderVorschlag.rolle_text ? `${absenderVorschlag.name} (${absenderVorschlag.rolle_text})` : absenderVorschlag.name}
                grund={absenderVorschlag.grund}
                fundstelle={absenderVorschlag.fundstelle}
                onFundstelle={onFundstelle}
                onUebernehmen={() => aendere({ absender: String(absenderVorschlag.wert) })}
              />
            )}
          </div>
        </div>

        <div className="feld">
          <label htmlFor="meta-datum">Datum</label>
          <input
            id="meta-datum"
            type="date"
            value={entwurf.datum}
            onChange={(e) => aendere({ datum: e.target.value })}
            className="meta-datum"
          />
          <span className="feld-hinweis">
            {meta.datum.wert ? (
              <>
                {DATUM_HERKUNFT[meta.datum.quelle ?? ""] ?? "erkannt"}
                {meta.datum.quelle === "dokument" && meta.datum.text && (
                  <>
                    {": "}
                    {meta.datum.abschnitt != null ? (
                      <button type="button" className="link klein" onClick={() => onFundstelle(meta.datum.abschnitt!)}>
                        „{meta.datum.text}“{meta.datum.seite != null && `, S. ${meta.datum.seite}`}
                      </button>
                    ) : (
                      `„${meta.datum.text}“`
                    )}
                  </>
                )}
                .
              </>
            ) : (
              "Im Dokument wurde kein Datum erkannt."
            )}
          </span>
          {datumVorschlag && (
            <Vorschlag
              wert={datumDe(datumVorschlag.wert)}
              grund={`erkannt: ${datumVorschlag.grund}`}
              fundstelle={datumVorschlag.fundstelle}
              onFundstelle={onFundstelle}
              onUebernehmen={() => aendere({ datum: datumVorschlag.wert })}
              text="erkanntes Datum verwenden"
            />
          )}
        </div>

        <div className="feld">
          <span>Schlagworte</span>
          <div className="tags">
            {sortiereTags(entwurf.schlagworte.map((name) => ({ name }))).map(({ name }) => (
              <span key={name} className="tag">
                {name}{" "}
                <button
                  type="button"
                  className="tag-weg"
                  aria-label={`Schlagwort ${name} entfernen`}
                  title="Entfernen"
                  onClick={() => aendere({ schlagworte: entwurf.schlagworte.filter((w) => w !== name) })}
                >
                  ×
                </button>
              </span>
            ))}
            {entwurf.schlagworte.length === 0 && <span className="leise klein">noch keine</span>}
          </div>
          <div className="meta-wort-neu">
            <input
              className="tag-eingabe"
              value={neuesWort}
              onChange={(e) => setNeuesWort(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  wortHinzufuegen(neuesWort);
                }
              }}
              placeholder="z. B. Anlage K 1, Gutachten"
              aria-label="Neues Schlagwort, mehrere mit Komma getrennt"
            />
            <button type="button" className="zweitrangig" onClick={() => wortHinzufuegen(neuesWort)} disabled={!neuesWort.trim()}>
              Hinzufügen
            </button>
          </div>
          <div className="tags">
            {BETEILIGTE.filter((b) => !enthaelt(entwurf.schlagworte, b)).map((b) => (
              <button key={b} type="button" className="tag-wahl" onClick={() => wortHinzufuegen(b)}>
                + {b}
              </button>
            ))}
          </div>
          {wortVorschlaege.map((t) => (
            <Vorschlag
              key={t.wert}
              wert={t.wert}
              grund={t.grund}
              fundstelle={t.fundstelle}
              onFundstelle={onFundstelle}
              onUebernehmen={() => wortHinzufuegen(t.wert)}
            />
          ))}
        </div>

        <div className="feld">
          <span>Weitere Beteiligte</span>
          <span className="feld-hinweis">Wen das Dokument außerdem betrifft, z. B. Empfänger oder Parteien.</span>
          {meta.akte_beteiligte.length === 0 ? (
            <span className="feld-hinweis">
              In der Akte sind noch keine Beteiligten eingetragen. Das geht im Reiter „Beteiligte“.
            </span>
          ) : (
            <ul className="meta-beteiligte">
              {meta.akte_beteiligte.map((b) => {
                const gewaehlt = entwurf.beteiligte.includes(b.id);
                // Wer als Absender gewählt oder vorgeschlagen ist, wird hier nicht noch einmal vorgeschlagen.
                const istAbsender = String(b.id) === entwurf.absender || b.id === absenderVorschlag?.wert;
                const vorschlag = !gewaehlt && !istAbsender ? vorgeschlagen.get(b.id) : undefined;
                return (
                  <li key={b.id} className={vorschlag ? "vorgeschlagen" : undefined}>
                    <label>
                      <input
                        type="checkbox"
                        checked={gewaehlt}
                        onChange={(e) =>
                          aendere({
                            beteiligte: e.target.checked
                              ? [...entwurf.beteiligte, b.id]
                              : entwurf.beteiligte.filter((i) => i !== b.id),
                          })
                        }
                      />{" "}
                      {b.name} <span className="leise klein">· {b.rolle_text}</span>
                    </label>
                    {vorschlag && (
                      <span className="meta-vorschlag-kurz">
                        <span className="leise klein">Vorschlag: {vorschlag.grund}</span>
                        {vorschlag.fundstelle && (
                          <button type="button" className="link klein" onClick={() => onFundstelle(vorschlag.fundstelle!.abschnitt)}>
                            {fundstelleText(vorschlag.fundstelle)}
                          </button>
                        )}
                        <button
                          type="button"
                          className="link klein"
                          onClick={() => aendere({ beteiligte: [...entwurf.beteiligte, b.id] })}
                        >
                          übernehmen
                        </button>
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {fehler && <p className="fehler">{fehler}</p>}
        <div className="aktionen meta-aktionen">
          <button type="submit" disabled={!offen || laeuft}>
            {laeuft ? "Speichere …" : "Speichern"}
          </button>
          <button type="button" className="zweitrangig" disabled={!offen || laeuft} onClick={() => setEntwurf(bisher)}>
            Verwerfen
          </button>
          {offen && <span className="leise klein">Nicht gespeicherte Änderungen</span>}
          {!offen && gespeichert && <span className="leise klein">Gespeichert.</span>}
        </div>
      </form>

      <section className="dok-details-abschnitt">
        <h3>Notizen zum Dokument</h3>
        <Notizen akteId={akteId} dokumentId={dokumentId} />
      </section>

      <section className="dok-details-abschnitt">
        <h3>Verlauf</h3>
        <ul className="meta-verlauf">
          {meta.verlauf.map((e) => (
            <li key={e.art === "fassung" ? `f${e.nr}` : `a${e.id}`}>
              <span className="leise klein">{zeitpunkt(e.zeitpunkt)}</span> <VerlaufText e={e} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function fundstelleText(f: MetaFundstelle): string {
  return f.seite != null ? `S. ${f.seite}, Abs. ${f.abschnitt}` : `Abs. ${f.abschnitt}`;
}

function Vorschlag({
  wert,
  grund,
  fundstelle,
  onFundstelle,
  onUebernehmen,
  text = "übernehmen",
}: {
  wert: string;
  grund: string;
  fundstelle: MetaFundstelle | null;
  onFundstelle: (abschnitt: number) => void;
  onUebernehmen: () => void;
  text?: string;
}) {
  return (
    <div className="meta-vorschlag">
      <span className="leise klein">Vorschlag:</span> <span className="meta-vorschlag-wert">{wert}</span>{" "}
      <span className="leise klein">
        ({grund}
        {fundstelle && (
          <>
            {", "}
            <button
              type="button"
              className="link klein"
              title={fundstelle.text ?? undefined}
              onClick={() => onFundstelle(fundstelle.abschnitt)}
            >
              {fundstelleText(fundstelle)}
            </button>
          </>
        )}
        )
      </span>{" "}
      <button type="button" className="link klein" onClick={onUebernehmen}>
        {text}
      </button>
    </div>
  );
}

function wertText(feld: string, wert: string | null): string {
  if (!wert) return "(leer)";
  return feld === "datum" ? datumDe(wert) : `„${wert}“`;
}

function VerlaufText({ e }: { e: MetaVerlaufEintrag }) {
  if (e.art === "fassung") {
    return e.quelle === "import" ? (
      <>Eingelesen als {e.dateiname} (Fassung 1)</>
    ) : (
      <>
        Fassung {e.nr} übernommen ({e.dateiname})
      </>
    );
  }
  return (
    <>
      {e.feld_text}: {wertText(e.feld, e.alt)} → {wertText(e.feld, e.neu)}
    </>
  );
}
