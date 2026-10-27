import { FormEvent, forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
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

/** Was die Akte über ungespeicherte Eingaben wissen muss, bevor sie das Dokument oder die Ansicht wechselt. */
export interface DetailsGriff {
  /** Ob es ungespeicherte Änderungen gibt. */
  offen: () => boolean;
  /** Speichert sie; false, wenn das Speichern scheitert. */
  speichern: () => Promise<boolean>;
  /** Verwirft sie, damit sie auch beim Verlassen nicht gespeichert werden. */
  verwerfen: () => void;
}

/** Parameter für akten.metadaten_speichern mit allen geänderten Feldern; null, wenn nichts geändert ist. */
function aenderungen(meta: DokumentMetadaten, entwurf: Entwurf): Record<string, unknown> | null {
  const bisher = ausMeta(meta);
  const params: Record<string, unknown> = { dokument_id: meta.dokument_id };
  if (entwurf.titel.trim() !== bisher.titel) params.titel = entwurf.titel.trim();
  if (entwurf.art.trim() !== bisher.art) params.art = entwurf.art.trim();
  if (entwurf.absender !== bisher.absender)
    params.absender = entwurf.absender === "" || entwurf.absender === "eigene" ? entwurf.absender : Number(entwurf.absender);
  // Wer das erkannte Datum wieder wählt, kehrt zur Erkennung zurück (auch nach einer neuen Fassung).
  const erkannt = meta.datum.erkannt?.datum;
  if (entwurf.datum !== bisher.datum) params.datum = erkannt && entwurf.datum === erkannt ? "" : entwurf.datum;
  if (!gleicheListe(entwurf.schlagworte, bisher.schlagworte)) params.schlagworte = entwurf.schlagworte;
  if (!gleicheListe(entwurf.beteiligte, bisher.beteiligte)) params.beteiligte = entwurf.beteiligte;
  return Object.keys(params).length > 1 ? params : null;
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
 * Die Fundstellen sind bewusst kein Link: Ein Sprung in den Text würde nicht gespeicherte Eingaben verwerfen.
 * Vor einem Wechsel innerhalb der Akte fragt die Akte nach (DetailsGriff); wer die Akte oder den Reiter verlässt,
 * dessen Eingaben werden gespeichert, wie bei den Stammdaten.
 */
const DokumentDetails = forwardRef<
  DetailsGriff,
  {
    akteId: number;
    dokumentId: number;
    /** Nach dem Speichern: Dokumentliste und Kopf neu laden (Titel, Datum, Tags). */
    onGespeichert: () => void;
  }
>(function DokumentDetails({ akteId, dokumentId, onGespeichert }, griff) {
  const [meta, setMeta] = useState<DokumentMetadaten | null>(null);
  const [entwurf, setEntwurf] = useState<Entwurf | null>(null);
  const [neuesWort, setNeuesWort] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [gespeichert, setGespeichert] = useState(false);
  // Stand für den Griff und fürs Speichern beim Verlassen (nach dem letzten Rendern).
  const stand = useRef<{ meta: DokumentMetadaten | null; entwurf: Entwurf | null }>({ meta: null, entwurf: null });
  stand.current = { meta, entwurf };
  const gespeichertRef = useRef(onGespeichert);
  gespeichertRef.current = onGespeichert;

  useImperativeHandle(griff, () => ({
    offen: () => !!(stand.current.meta && stand.current.entwurf && aenderungen(stand.current.meta, stand.current.entwurf)),
    speichern: () => speichern(),
    verwerfen: () => {
      const m = stand.current.meta;
      if (m) {
        stand.current.entwurf = ausMeta(m);
        setEntwurf(ausMeta(m));
      }
    },
  }));

  useEffect(
    () => () => {
      const { meta: m, entwurf: e } = stand.current;
      const params = m && e ? aenderungen(m, e) : null;
      if (params)
        void kern("akten.metadaten_speichern", params).then(
          () => gespeichertRef.current(),
          () => undefined,
        );
    },
    [],
  );

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

  async function speichern(e?: FormEvent): Promise<boolean> {
    e?.preventDefault();
    const { meta: m0, entwurf: e0 } = stand.current;
    const params = m0 && e0 ? aenderungen(m0, e0) : null;
    if (!params) return true;
    setLaeuft(true);
    setFehler(null);
    try {
      const m = await kern<DokumentMetadaten>("akten.metadaten_speichern", params);
      stand.current = { meta: m, entwurf: ausMeta(m) };
      setMeta(m);
      setEntwurf(ausMeta(m));
      setGespeichert(true);
      gespeichertRef.current();
      return true;
    } catch (fehler) {
      setFehler(String(fehler));
      return false;
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
                    „{meta.datum.text}“{meta.datum.seite != null && `, S. ${meta.datum.seite}`}
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
                          <span className="leise klein" title={vorschlag.fundstelle.text ?? undefined}>
                            {fundstelleText(vorschlag.fundstelle)}
                          </span>
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
});

export default DokumentDetails;

function fundstelleText(f: MetaFundstelle): string {
  return f.seite != null ? `S. ${f.seite}, Abs. ${f.abschnitt}` : `Abs. ${f.abschnitt}`;
}

function Vorschlag({
  wert,
  grund,
  fundstelle,
  onUebernehmen,
  text = "übernehmen",
}: {
  wert: string;
  grund: string;
  fundstelle: MetaFundstelle | null;
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
            <span title={fundstelle.text ?? undefined}>{fundstelleText(fundstelle)}</span>
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
