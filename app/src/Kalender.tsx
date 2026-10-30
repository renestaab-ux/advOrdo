import { useCallback, useEffect, useMemo, useState } from "react";
import AktenWahl from "./AktenWahl";
import Fristenbuch from "./Fristenbuch";
import {
  ABSCHLUSS_TEXT,
  EINHEITEN,
  EintragFormular,
  Folge,
  FolgeFormular,
  fundText,
  leer,
  zeitText,
} from "./Fristen";
import {
  Ansicht,
  FILTER_START,
  KalenderFilter,
  KalenderPosten,
  POSTEN_TEXT,
  PostenTyp,
  ausIso,
  blaettern,
  isoTag,
  plusTage,
  posten,
  postenKlasse,
  zeitraumTitel,
  zeitraumVon,
} from "./kalenderLogik";
import { Akte, KalenderEintrag, TerminZustand, Verfahren, abstandText, datumLang, fristenLand, kern } from "./kern";
import { LeerHinweis } from "./Symbole";

const ANSICHTEN: { id: Ansicht; titel: string }[] = [
  { id: "monat", titel: "Monat" },
  { id: "woche", titel: "Woche" },
  { id: "liste", titel: "Liste" },
];
const WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
const ANSICHT_SCHLUESSEL = "kalender.ansicht";
const FILTER_SCHLUESSEL = "kalender.filter";

function gelesen<T>(schluessel: string, vorgabe: T): T {
  try {
    const roh = localStorage.getItem(schluessel);
    return roh ? { ...vorgabe, ...JSON.parse(roh) } : vorgabe;
  } catch {
    return vorgabe;
  }
}

function gespeichert(schluessel: string, wert: unknown) {
  try {
    localStorage.setItem(schluessel, JSON.stringify(wert));
  } catch {
    // Ohne Speicher gilt die Wahl bis zum Neustart.
  }
}

/** Kurzbezeichnung der Akte: Aktenzeichen, sonst Name. */
const akteKurz = (e: KalenderEintrag) => e.aktenzeichen || e.akte || "";

/**
 * Bereich „Kalender“: alle Fristen (mit Vorfristen), Termine und Wiedervorlagen aller Akten als Monat, Woche oder
 * Liste, mit Filtern. Einträge lassen sich hier anlegen (mit Akte) und wie in der Akte erledigen, verlängern,
 * verlegen oder aufheben.
 */
export default function Kalender({ onAkte }: { onAkte: (id: number) => void }) {
  const heute = isoTag(new Date());
  const [ansicht, setAnsicht] = useState<Ansicht>(() => gelesen(ANSICHT_SCHLUESSEL, { a: "monat" as Ansicht }).a);
  const [bezug, setBezug] = useState(heute);
  const [filter, setFilter] = useState<KalenderFilter>(() => gelesen(FILTER_SCHLUESSEL, FILTER_START));
  const [eintraege, setEintraege] = useState<KalenderEintrag[] | null>(null);
  const [ueberfaellig, setUeberfaellig] = useState<KalenderEintrag[]>([]);
  const [feiertage, setFeiertage] = useState<Map<string, string>>(new Map());
  const [akten, setAkten] = useState<Akte[]>([]);
  const [gewaehlt, setGewaehlt] = useState<KalenderPosten | null>(null);
  const [neu, setNeu] = useState<{ tag: string } | null>(null);
  const [folge, setFolge] = useState<Folge | null>(null);
  const [buch, setBuch] = useState(false);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const { von, bis } = zeitraumVon(ansicht, bezug);

  const laden = useCallback(async () => {
    try {
      const [liste, offen, frei] = await Promise.all([
        kern<KalenderEintrag[]>("kalender.zeitraum", { von, bis }),
        kern<KalenderEintrag[]>("akten.kalender_naechste", { tage: 0, limit: 200 }),
        kern<{ datum: string; name: string }[]>("kalender.feiertage", { von, bis, land: fristenLand() }),
      ]);
      setEintraege(liste);
      setUeberfaellig(offen.filter((e) => e.lage === "abgelaufen"));
      setFeiertage(new Map(frei.map((f) => [f.datum, f.name])));
    } catch (e) {
      setFehler(String(e));
    }
  }, [von, bis]);

  useEffect(() => {
    void laden();
  }, [laden]);

  useEffect(() => {
    kern<Akte[]>("akten.liste").then(setAkten, () => setAkten([]));
  }, []);

  function waehleAnsicht(a: Ansicht) {
    setAnsicht(a);
    gespeichert(ANSICHT_SCHLUESSEL, { a });
  }

  function filtern(teil: Partial<KalenderFilter>) {
    const f = { ...filter, ...teil };
    setFilter(f);
    gespeichert(FILTER_SCHLUESSEL, f);
  }

  function art(typ: PostenTyp) {
    filtern({ arten: filter.arten.includes(typ) ? filter.arten.filter((a) => a !== typ) : [...filter.arten, typ] });
  }

  async function ausfuehren(f: () => Promise<unknown>, text: string) {
    setLaeuft(true);
    setFehler(null);
    try {
      await f();
      setMeldung(text);
      setFolge(null);
      setGewaehlt(null);
      await laden();
    } catch (e) {
      setFehler(String(e));
    } finally {
      setLaeuft(false);
    }
  }

  const sichtbar = useMemo(() => posten(eintraege ?? [], filter, von, bis), [eintraege, filter, von, bis]);
  const jeTag = useMemo(() => {
    const m = new Map<string, KalenderPosten[]>();
    for (const p of sichtbar) m.set(p.tag, [...(m.get(p.tag) ?? []), p]);
    return m;
  }, [sichtbar]);
  const gerichte = useMemo(
    () => [...new Set((eintraege ?? []).map((e) => e.gericht).filter((g): g is string => !!g))].sort(),
    [eintraege],
  );
  const filterAktiv =
    filter.arten.length < 4 || filter.zustand !== "alle" || filter.akteId != null || !!filter.gericht || filter.nurAbgelaufen;

  return (
    <div className="kalender">
      <header className="kalender-kopf">
        <h1>Kalender</h1>
        <div className="kalender-steuerung">
          <div className="segment" role="group" aria-label="Ansicht">
            {ANSICHTEN.map((a) => (
              <button
                key={a.id}
                className={a.id === ansicht ? "segment-knopf aktiv" : "segment-knopf"}
                aria-pressed={a.id === ansicht}
                onClick={() => waehleAnsicht(a.id)}
              >
                {a.titel}
              </button>
            ))}
          </div>
          <span className="kalender-blaettern">
            <button className="zweitrangig" onClick={() => setBezug(blaettern(ansicht, bezug, -1))} aria-label="Zurück">
              ‹
            </button>
            <button className="zweitrangig" onClick={() => setBezug(heute)}>
              Heute
            </button>
            <button className="zweitrangig" onClick={() => setBezug(blaettern(ansicht, bezug, 1))} aria-label="Weiter">
              ›
            </button>
          </span>
          <strong className="kalender-zeitraum">{zeitraumTitel(ansicht, bezug)}</strong>
          <button className="zweitrangig" onClick={() => setBuch(!buch)} aria-expanded={buch}>
            Fristenbuch …
          </button>
          <button
            onClick={() => (setNeu({ tag: heute >= von && heute <= bis ? heute : von }), setGewaehlt(null), setMeldung(null))}
          >
            + Neuer Eintrag
          </button>
        </div>
      </header>

      <div className="kalender-filter" role="group" aria-label="Filter">
        {(Object.keys(POSTEN_TEXT) as PostenTyp[]).map((t) => (
          <label key={t} className={`filter-chip ${t}`}>
            <input type="checkbox" checked={filter.arten.includes(t)} onChange={() => art(t)} /> {POSTEN_TEXT[t]}
          </label>
        ))}
        <select
          value={filter.zustand}
          onChange={(e) => filtern({ zustand: e.target.value as KalenderFilter["zustand"] })}
          aria-label="Zustand"
        >
          <option value="alle">Offen und abgeschlossen</option>
          <option value="offen">Nur offen</option>
          <option value="abgeschlossen">Nur erledigt und vergangen</option>
        </select>
        <AktenWahl akten={akten} akteId={filter.akteId} onWahl={(id) => filtern({ akteId: id })} />
        {gerichte.length > 0 && (
          <select value={filter.gericht} onChange={(e) => filtern({ gericht: e.target.value })} aria-label="Gericht">
            <option value="">Alle Gerichte</option>
            {gerichte.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        )}
        <label className="filter-chip">
          <input type="checkbox" checked={filter.nurAbgelaufen} onChange={() => filtern({ nurAbgelaufen: !filter.nurAbgelaufen })} />{" "}
          nur abgelaufene
        </label>
        {filterAktiv && (
          <button className="link klein" onClick={() => filtern(FILTER_START)}>
            Filter zurücksetzen
          </button>
        )}
      </div>

      {ueberfaellig.length > 0 && (
        <details className="kalender-ueberfaellig">
          <summary>
            {ueberfaellig.length === 1
              ? "1 Frist oder Wiedervorlage ist abgelaufen und nicht erledigt"
              : `${ueberfaellig.length} Fristen oder Wiedervorlagen sind abgelaufen und nicht erledigt`}
          </summary>
          <ul>
            {ueberfaellig.map((e) => (
              <li key={e.id}>
                <button className="link" onClick={() => setGewaehlt({ schluessel: `${e.id}`, tag: e.datum, typ: e.art, eintrag: e })}>
                  {datumLang(e.datum)} · {e.titel}
                </button>{" "}
                <span className="leise">
                  {[e.aktenzeichen, e.akte].filter(Boolean).join(" ")} · {abstandText(e)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {fehler && <p className="fehler">{fehler}</p>}
      {meldung && <p className="meldung">{meldung}</p>}

      {buch && (
        // Im Monat gilt der Kalendermonat, nicht das ganze Raster mit den Tagen der Nachbarmonate.
        <Fristenbuch
          key={`${von}-${bis}`}
          von={ansicht === "monat" ? `${bezug.slice(0, 7)}-01` : von}
          bis={ansicht === "monat" ? plusTage(blaettern("monat", bezug, 1).slice(0, 7) + "-01", -1) : bis}
          filter={filter}
          onSchliessen={() => setBuch(false)}
        />
      )}

      {neu && (
        <NeuerEintrag
          akten={akten}
          tag={neu.tag}
          akteVorgabe={filter.akteId}
          onAbbrechen={() => setNeu(null)}
          onGespeichert={(titel) => {
            setNeu(null);
            setMeldung(`„${titel}“ eingetragen.`);
            void laden();
          }}
        />
      )}

      {folge && (
        <FolgeFormular
          key={`${folge.e.id}-${folge.aktion}`}
          folge={folge}
          laeuft={laeuft}
          onAbbrechen={() => setFolge(null)}
          onVerlaengern={(datum, vermerk) =>
            void ausfuehren(
              () => kern("akten.kalender_verlaengern", { eintrag_id: folge.e.id, datum, vermerk }),
              `„${folge.e.titel}“ ${folge.e.art === "wiedervorlage" ? "verschoben" : "geändert"} auf ${datumLang(datum)}.`,
            )
          }
          onTermin={(zustand, vermerk, neuerTermin) =>
            void ausfuehren(
              () => kern("akten.kalender_termin_zustand", { eintrag_id: folge.e.id, zustand, vermerk, neu: neuerTermin ?? null }),
              zustand === "verlegt"
                ? `„${folge.e.titel}“ verlegt auf ${datumLang(String(neuerTermin?.datum))}.`
                : `„${folge.e.titel}“ als aufgehoben vermerkt.`,
            )
          }
        />
      )}

      <div className={gewaehlt ? "kalender-flaeche mit-detail" : "kalender-flaeche"}>
        <div className="kalender-haupt">
          {eintraege == null && !fehler && <p className="status">Lade …</p>}
          {eintraege != null && ansicht === "monat" && (
            <MonatsRaster
              von={von}
              monat={bezug.slice(0, 7)}
              heute={heute}
              jeTag={jeTag}
              feiertage={feiertage}
              gewaehlt={gewaehlt}
              onPosten={(p) => (setGewaehlt(p), setNeu(null))}
              onTag={(tag) => (setNeu({ tag }), setGewaehlt(null), setMeldung(null))}
            />
          )}
          {eintraege != null && ansicht === "woche" && (
            <WochenSpalten
              von={von}
              heute={heute}
              jeTag={jeTag}
              feiertage={feiertage}
              gewaehlt={gewaehlt}
              onPosten={(p) => (setGewaehlt(p), setNeu(null))}
              onTag={(tag) => (setNeu({ tag }), setGewaehlt(null), setMeldung(null))}
            />
          )}
          {eintraege != null && ansicht === "liste" && (
            <TagesListe
              heute={heute}
              jeTag={jeTag}
              feiertage={feiertage}
              gewaehlt={gewaehlt}
              onPosten={(p) => (setGewaehlt(p), setNeu(null))}
            />
          )}
        </div>
        {gewaehlt && (
          <PostenDetail
            p={gewaehlt}
            laeuft={laeuft}
            onSchliessen={() => setGewaehlt(null)}
            onAkte={() => onAkte(gewaehlt.eintrag.akte_id)}
            onErledigen={(erledigt) =>
              void ausfuehren(
                () => kern("akten.kalender_erledigen", { eintrag_id: gewaehlt.eintrag.id, erledigt, vermerk: "" }),
                erledigt ? `„${gewaehlt.eintrag.titel}“ als erledigt markiert.` : `„${gewaehlt.eintrag.titel}“ wieder offen.`,
              )
            }
            onFolge={(aktion) => setFolge({ e: gewaehlt.eintrag, aktion })}
            onTermin={(zustand) =>
              void ausfuehren(
                () => kern("akten.kalender_termin_zustand", { eintrag_id: gewaehlt.eintrag.id, zustand }),
                `„${gewaehlt.eintrag.titel}“ wieder als geplant geführt.`,
              )
            }
          />
        )}
      </div>
    </div>
  );
}

interface AnsichtProps {
  heute: string;
  jeTag: Map<string, KalenderPosten[]>;
  feiertage: Map<string, string>;
  gewaehlt: KalenderPosten | null;
  onPosten: (p: KalenderPosten) => void;
}

function PostenKnopf({ p, gewaehlt, mitAkte, onPosten }: { p: KalenderPosten; gewaehlt: boolean; mitAkte: boolean; onPosten: (p: KalenderPosten) => void }) {
  const e = p.eintrag;
  const titel = p.typ === "vorfrist" ? `${p.nr === 2 ? "2. Vorfrist" : "Vorfrist"}: ${e.titel}` : e.titel;
  return (
    <button
      className={`${postenKlasse(p)}${gewaehlt ? " gewaehlt" : ""}`}
      onClick={(ev) => {
        ev.stopPropagation();
        onPosten(p);
      }}
      title={`${POSTEN_TEXT[p.typ]}: ${titel}${e.akte ? ` · ${[e.aktenzeichen, e.akte].filter(Boolean).join(" ")}` : ""}`}
    >
      {e.uhrzeit && p.typ === "termin" && <span className="posten-zeit">{e.uhrzeit}</span>}
      <span className="posten-titel">{titel}</span>
      {mitAkte && akteKurz(e) && <span className="posten-akte">{akteKurz(e)}</span>}
    </button>
  );
}

function tagKlasse(tag: string, heute: string, feiertage: Map<string, string>, extra = ""): string {
  const wt = ausIso(tag).getDay();
  return ["kalender-tag", extra, tag === heute ? "heute" : "", wt === 0 || wt === 6 || feiertage.has(tag) ? "frei" : ""]
    .filter(Boolean)
    .join(" ");
}

function MonatsRaster({ von, monat, onTag, ...p }: AnsichtProps & { von: string; monat: string; onTag: (tag: string) => void }) {
  const tage = Array.from({ length: 42 }, (_, i) => plusTage(von, i));
  return (
    <div className="monats-raster" role="grid" aria-label="Monat">
      {WOCHENTAGE.map((w) => (
        <div key={w} className="kalender-wochentag" role="columnheader">
          {w}
        </div>
      ))}
      {tage.map((tag) => {
        const liste = p.jeTag.get(tag) ?? [];
        const zuViele = liste.length > 4;
        return (
          <div
            key={tag}
            role="gridcell"
            className={tagKlasse(tag, p.heute, p.feiertage, tag.slice(0, 7) === monat ? "" : "fremd")}
            onClick={() => onTag(tag)}
            title="Klicken, um an diesem Tag etwas einzutragen"
          >
            <span className="tag-kopf">
              <span className="tag-zahl">{Number(tag.slice(8))}</span>
              {p.feiertage.get(tag) && <span className="feiertag">{p.feiertage.get(tag)}</span>}
            </span>
            {(zuViele ? liste.slice(0, 3) : liste).map((x) => (
              <PostenKnopf key={x.schluessel} p={x} gewaehlt={p.gewaehlt?.schluessel === x.schluessel} mitAkte={false} onPosten={p.onPosten} />
            ))}
            {zuViele && <span className="leise klein">+ {liste.length - 3} weitere (Woche oder Liste)</span>}
          </div>
        );
      })}
    </div>
  );
}

function WochenSpalten({ von, onTag, ...p }: AnsichtProps & { von: string; onTag: (tag: string) => void }) {
  const tage = Array.from({ length: 7 }, (_, i) => plusTage(von, i));
  return (
    <div className="wochen-spalten">
      {tage.map((tag, i) => (
        <div key={tag} className={tagKlasse(tag, p.heute, p.feiertage)} onClick={() => onTag(tag)}>
          <span className="tag-kopf">
            <strong>
              {WOCHENTAGE[i]}, {tag.slice(8, 10)}.{tag.slice(5, 7)}.
            </strong>
            {p.feiertage.get(tag) && <span className="feiertag">{p.feiertage.get(tag)}</span>}
          </span>
          {(p.jeTag.get(tag) ?? []).map((x) => (
            <PostenKnopf key={x.schluessel} p={x} gewaehlt={p.gewaehlt?.schluessel === x.schluessel} mitAkte onPosten={p.onPosten} />
          ))}
        </div>
      ))}
    </div>
  );
}

function TagesListe(p: AnsichtProps) {
  const tage = [...p.jeTag.keys()];
  if (tage.length === 0) return <LeerHinweis symbol="fristen">Keine Einträge in diesem Zeitraum (bei den gewählten Filtern).</LeerHinweis>;
  return (
    <ol className="tages-liste">
      {tage.map((tag) => (
        <li key={tag} className={tag === p.heute ? "heute" : undefined}>
          <h3>
            {datumLang(tag)}
            {tag === p.heute && <span className="leise"> · heute</span>}
            {p.feiertage.get(tag) && <span className="feiertag"> · {p.feiertage.get(tag)}</span>}
          </h3>
          <ul>
            {(p.jeTag.get(tag) ?? []).map((x) => {
              const e = x.eintrag;
              return (
                <li key={x.schluessel}>
                  <button className={`listen-posten ${postenKlasse(x)}${p.gewaehlt?.schluessel === x.schluessel ? " gewaehlt" : ""}`} onClick={() => p.onPosten(x)}>
                    <span className="posten-zeit">{x.typ === "termin" ? zeitText(e) ?? "" : ""}</span>
                    <span className={`art-marke ${x.typ === "vorfrist" ? "frist" : x.typ}`}>
                      {x.typ === "vorfrist" ? (x.nr === 2 ? "2. Vorfrist" : "Vorfrist") : POSTEN_TEXT[x.typ]}
                    </span>
                    <strong className="posten-titel">{e.titel}</strong>
                    <span className="leise">{[e.aktenzeichen, e.akte].filter(Boolean).join(" ")}</span>
                    {e.ort && <span className="leise">{e.ort}</span>}
                    <span className={`lage-marke ${e.lage}`}>{x.typ === "vorfrist" ? `Frist ${datumLang(e.datum)}` : abstandText(e)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </li>
      ))}
    </ol>
  );
}

function PostenDetail({
  p,
  laeuft,
  onSchliessen,
  onAkte,
  onErledigen,
  onFolge,
  onTermin,
}: {
  p: KalenderPosten;
  laeuft: boolean;
  onSchliessen: () => void;
  onAkte: () => void;
  onErledigen: (erledigt: boolean) => void;
  onFolge: (aktion: Folge["aktion"]) => void;
  onTermin: (zustand: TerminZustand) => void;
}) {
  const e = p.eintrag;
  const b = e.berechnung;
  const termin = e.art === "termin";
  return (
    <aside className="karte kalender-detail" aria-label="Eintrag">
      <div className="vorschlaege-kopf">
        <span className={`art-marke ${e.art}`}>{e.art_text}</span>
        <button className="link klein" onClick={onSchliessen}>
          Schließen
        </button>
      </div>
      <h3 className={e.zustand === "aufgehoben" || e.zustand === "verlegt" ? "kalender-titel durchgestrichen" : "kalender-titel"}>{e.titel}</h3>
      {p.typ === "vorfrist" && (
        <p className="hinweis-text">
          {p.nr === 2 ? "2. Vorfrist" : "Vorfrist"} am {datumLang(p.tag)}
        </p>
      )}
      <p>
        <strong>
          {e.art === "frist" ? "Fristende" : termin ? "Termin" : "Wiedervorlage"}: {datumLang(e.datum)}
        </strong>
        {zeitText(e) && `, ${zeitText(e)}`}
        {e.ort && `, ${e.ort}`}
        <br />
        <span className={`lage-marke ${e.lage}`}>{abstandText(e)}</span>
      </p>
      <p className="klein">
        <button className="link" onClick={onAkte}>
          {[e.aktenzeichen, e.akte].filter(Boolean).join(" · ")}
        </button>
        {e.gericht && (
          <span className="leise">
            <br />
            {e.gericht}
            {e.gericht_aktenzeichen && `, ${e.gericht_aktenzeichen}`}
          </span>
        )}
      </p>
      {b && (
        <p className="leise klein">
          {b.anzahl} {EINHEITEN[b.einheit]} ab {datumLang(b.bezugstag)} ({b.grundlagen.join(", ")}
          {b.verschoben && `; verschoben wegen ${b.grund}`})
        </p>
      )}
      {(e.vorfrist || e.vorfrist2) && (
        <p className="leise klein">Vorfristen: {[e.vorfrist, e.vorfrist2].filter(Boolean).map((v) => datumLang(v)).join(" und ")}</p>
      )}
      {e.verlauf.map((v) => (
        <p key={v.am} className="leise klein">
          {v.was === "verschoben" ? "Verschoben" : v.was === "verlängert" ? "Verlängert" : "Verkürzt"} vom {datumLang(v.alt)} auf{" "}
          {datumLang(v.neu)}
          {v.vermerk && ` (${v.vermerk})`}
        </p>
      ))}
      {e.verlegt_von_termin && <p className="leise klein">Verlegt vom {datumLang(e.verlegt_von_termin.datum)}</p>}
      {e.verlegt_auf && <p className="leise klein">Verlegt auf {datumLang(e.verlegt_auf.datum)}</p>}
      {e.dokument && (
        <p className="leise klein" title={e.fundstelle?.text}>
          Beleg: {e.dokument}
          {e.fundstelle && `, ${fundText(e.fundstelle)}`}
        </p>
      )}
      {e.notiz && <p className="klein">{e.notiz}</p>}
      {e.erledigt_am && (
        <p className="leise klein">
          {ABSCHLUSS_TEXT[e.zustand ?? "erledigt"]} am {datumLang(e.erledigt_am.slice(0, 10))}
          {e.erledigt_vermerk && `: ${e.erledigt_vermerk}`}
        </p>
      )}
      <span className="aktionen">
        {!termin && (
          <button className="zweitrangig" onClick={() => onErledigen(!e.erledigt_am)} disabled={laeuft}>
            {e.erledigt_am ? "Wieder öffnen" : "Erledigt"}
          </button>
        )}
        {!termin && !e.erledigt_am && (
          <button className="zweitrangig" onClick={() => onFolge("verlaengern")} disabled={laeuft}>
            {e.art === "frist" ? "Verlängern …" : "Verschieben …"}
          </button>
        )}
        {termin && !e.abgeschlossen && (
          <>
            <button className="zweitrangig" onClick={() => onFolge("verlegen")} disabled={laeuft}>
              Verlegen …
            </button>
            <button className="zweitrangig" onClick={() => onFolge("aufheben")} disabled={laeuft}>
              Aufgehoben …
            </button>
          </>
        )}
        {termin && (e.zustand === "aufgehoben" || e.zustand === "verlegt") && (
          <button className="zweitrangig" onClick={() => onTermin("geplant")} disabled={laeuft}>
            Wieder geplant
          </button>
        )}
        <button className="link" onClick={onAkte}>
          Zur Akte
        </button>
      </span>
    </aside>
  );
}

/** Neuer Eintrag aus dem Kalender: erst die Akte (Pflicht), dann dasselbe Formular wie im Reiter Fristen der Akte. */
function NeuerEintrag({
  akten,
  tag,
  akteVorgabe,
  onAbbrechen,
  onGespeichert,
}: {
  akten: Akte[];
  tag: string;
  akteVorgabe: number | null;
  onAbbrechen: () => void;
  onGespeichert: (titel: string) => void;
}) {
  const [akteId, setAkteId] = useState<number | null>(akteVorgabe);
  const [verfahren, setVerfahren] = useState<Verfahren[] | null>(null);
  const akte = akten.find((a) => a.id === akteId);

  useEffect(() => {
    setVerfahren(null);
    if (akteId != null) kern<Verfahren[]>("akten.verfahren", { akte_id: akteId }).then(setVerfahren, () => setVerfahren([]));
  }, [akteId]);

  return (
    <section className="karte kalender-neu" aria-label="Neuer Eintrag">
      <div className="vorschlaege-kopf">
        <h3>Neuer Eintrag am {datumLang(tag)}</h3>
        <button className="link klein" onClick={onAbbrechen}>
          Abbrechen
        </button>
      </div>
      <div className="kalender-neu-wahl">
        <span>Akte:</span>
        <AktenWahl akten={akten} akteId={akteId} onWahl={setAkteId} knopf={akte ? undefined : "Akte wählen …"} />
      </div>
      {akteId == null && <p className="leise">Jeder Eintrag gehört zu einer Akte; bitte zuerst die Akte wählen.</p>}
      {akteId != null && verfahren && (
        <EintragFormular
          key={`${akteId}-${tag}`}
          akteId={akteId}
          start={{ ...leer("termin", verfahren), modus: "datum", datum: tag }}
          verfahren={verfahren}
          onAbbrechen={onAbbrechen}
          onGespeichert={(_, e) => onGespeichert(e.titel)}
        />
      )}
    </section>
  );
}
