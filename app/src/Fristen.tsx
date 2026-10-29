import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  FristBerechnung,
  KalenderArt,
  KalenderEintrag,
  KalenderVorschlag,
  TerminZustand,
  Verfahren,
  abstandText,
  datumLang,
  fristenLand,
  kern,
} from "./kern";
import { LeerHinweis } from "./Symbole";

const ART_TEXT: Record<KalenderArt, string> = { frist: "Frist", termin: "Termin", wiedervorlage: "Wiedervorlage" };
const EINHEITEN: Record<FristBerechnung["einheit"], string> = { tage: "Tage", wochen: "Wochen", monate: "Monate", jahre: "Jahre" };
const TITEL_VORSCHLAEGE: Record<KalenderArt, string[]> = {
  frist: [
    "Klageerwiderung",
    "Anzeige der Verteidigungsbereitschaft",
    "Replik",
    "Stellungnahme",
    "Berufungsfrist",
    "Berufungsbegründungsfrist",
    "Einspruchsfrist",
    "Widerspruchsfrist (Mahnbescheid)",
  ],
  termin: ["Güteverhandlung und früher erster Termin", "Mündliche Verhandlung", "Haupttermin", "Beweisaufnahme", "Verkündungstermin"],
  wiedervorlage: ["Wiedervorlage", "Sachstand beim Gericht erfragen", "Zahlungseingang prüfen"],
};

/** Formularzustand; leer bzw. aus einem vorhandenen Eintrag oder einem Vorschlag. */
interface Entwurf {
  id: number | null;
  art: KalenderArt;
  titel: string;
  modus: "datum" | "berechnen";
  datum: string;
  bezugstag: string;
  anzahl: string;
  einheit: FristBerechnung["einheit"];
  uhrzeit: string;
  bis_uhrzeit: string;
  ort: string;
  vorfrist: string;
  vorfrist2: string;
  verfahren_id: string;
  notiz: string;
  dokument_id: number | null;
  fundstelle: KalenderVorschlag["fundstelle"] | null;
  /** Quelle, falls aus einem Vorschlag: Dateiname für die Anzeige. */
  dateiname: string | null;
  vorschlag: KalenderVorschlag | null;
}

function leer(art: KalenderArt, verfahren: Verfahren[]): Entwurf {
  return {
    id: null,
    art,
    titel: art === "wiedervorlage" ? "Wiedervorlage" : "",
    modus: art === "frist" ? "berechnen" : "datum",
    datum: "",
    bezugstag: "",
    anzahl: "2",
    einheit: "wochen",
    uhrzeit: "",
    bis_uhrzeit: "",
    ort: "",
    vorfrist: "",
    vorfrist2: "",
    verfahren_id: String(verfahren.find((v) => v.aktuell)?.id ?? ""),
    notiz: "",
    dokument_id: null,
    fundstelle: null,
    dateiname: null,
    vorschlag: null,
  };
}

function ausEintrag(e: KalenderEintrag): Entwurf {
  return {
    id: e.id,
    art: e.art,
    titel: e.titel,
    modus: e.berechnung ? "berechnen" : "datum",
    datum: e.datum,
    bezugstag: e.berechnung?.bezugstag ?? "",
    anzahl: String(e.berechnung?.anzahl ?? 2),
    einheit: e.berechnung?.einheit ?? "wochen",
    uhrzeit: e.uhrzeit ?? "",
    bis_uhrzeit: e.bis_uhrzeit ?? "",
    ort: e.ort ?? "",
    vorfrist: e.vorfrist ?? "",
    vorfrist2: e.vorfrist2 ?? "",
    verfahren_id: String(e.verfahren_id ?? ""),
    notiz: e.notiz ?? "",
    dokument_id: e.dokument_id,
    fundstelle: e.fundstelle ? { ...e.fundstelle, text: e.fundstelle.text ?? "" } : null,
    dateiname: e.dokument,
    vorschlag: null,
  };
}

function ausVorschlag(v: KalenderVorschlag, verfahren: Verfahren[]): Entwurf {
  const art = v.art === "zustand" ? "termin" : v.art;
  const e = leer(art, verfahren);
  const dauer = v.berechnung ?? v.dauer;
  return {
    ...e,
    titel: v.titel,
    modus: art === "frist" && dauer ? "berechnen" : "datum",
    datum: v.datum ?? "",
    bezugstag: v.berechnung?.bezugstag ?? "",
    anzahl: String(dauer?.anzahl ?? 2),
    einheit: dauer?.einheit ?? "wochen",
    uhrzeit: v.uhrzeit ?? "",
    ort: v.ort ?? "",
    vorfrist: v.vorfrist ?? "",
    dokument_id: v.dokument_id,
    fundstelle: v.fundstelle,
    dateiname: v.dateiname,
    vorschlag: v,
  };
}

/** Vorfristen: Tage vor dem Fristende. */
function minusTage(iso: string, tage: number): string {
  const [j, m, t] = iso.split("-").map(Number);
  const d = new Date(j, m - 1, t - tage);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Schlüssel eines Vorschlags, damit ein verworfener beim Neuladen verworfen bleibt. */
const vorschlagSchluessel = (v: KalenderVorschlag) => `${v.dokument_id}-${v.fundstelle.abschnitt}-${v.art}-${v.datum ?? ""}`;

function fundText(f: { abschnitt: number; seite: number | null }): string {
  return [f.seite ? `S. ${f.seite}` : null, `Abschnitt ${f.abschnitt}`].filter(Boolean).join(", ");
}

/** Uhrzeit eines Termins, mit Ende: „10:00–11:30 Uhr“. */
function zeitText(e: { uhrzeit: string | null; bis_uhrzeit?: string | null }): string | null {
  if (!e.uhrzeit) return null;
  return `${e.uhrzeit}${e.bis_uhrzeit ? `–${e.bis_uhrzeit}` : ""} Uhr`;
}

const ABSCHLUSS_TEXT: Record<NonNullable<KalenderEintrag["zustand"]>, string> = {
  erledigt: "Erledigt",
  stattgefunden: "Als stattgefunden vermerkt",
  aufgehoben: "Aufgehoben",
  verlegt: "Verlegt",
};

/** Eine Folgeaktion an einem Eintrag: Frist verlängern, Wiedervorlage verschieben, Termin verlegen oder aufheben. */
interface Folge {
  e: KalenderEintrag;
  aktion: "verlaengern" | "verlegen" | "aufheben";
  /** Aus einem Vorschlag: Beleg und Vorbelegung. */
  vorschlag?: KalenderVorschlag;
}

/**
 * Reiter „Fristen“ einer Akte: Fristen (mit Fristenrechner), Termine und Wiedervorlagen. Vorschläge aus den
 * Dokumenten werden erst nach Prüfung eingetragen.
 */
export default function Fristen({ akteId, onGeaendert }: { akteId: number; onGeaendert: () => void }) {
  const [eintraege, setEintraege] = useState<KalenderEintrag[] | null>(null);
  const [verfahren, setVerfahren] = useState<Verfahren[]>([]);
  const [entwurf, setEntwurf] = useState<Entwurf | null>(null);
  const [vorschlaege, setVorschlaege] = useState<KalenderVorschlag[] | null>(null);
  const [verworfen, setVerworfen] = useState<Set<string>>(new Set());
  const [loeschfrage, setLoeschfrage] = useState<KalenderEintrag | null>(null);
  const [folge, setFolge] = useState<Folge | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);

  const laden = useCallback(async () => {
    try {
      const [k, v] = await Promise.all([
        kern<KalenderEintrag[]>("akten.kalender", { akte_id: akteId }),
        kern<Verfahren[]>("akten.verfahren", { akte_id: akteId }),
      ]);
      setEintraege(k);
      setVerfahren(v);
    } catch (e) {
      setFehler(String(e));
    }
  }, [akteId]);

  useEffect(() => {
    void laden();
  }, [laden]);

  async function ausfuehren<T>(f: () => Promise<T>): Promise<T | undefined> {
    setLaeuft(true);
    setFehler(null);
    try {
      return await f();
    } catch (e) {
      setFehler(String(e));
      return undefined;
    } finally {
      setLaeuft(false);
    }
  }

  function aktualisiert(liste: KalenderEintrag[] | undefined, text: string) {
    if (!liste) return;
    setEintraege(liste);
    setMeldung(text);
    onGeaendert();
  }

  async function erledigen(e: KalenderEintrag, erledigt: boolean, vermerk = "") {
    const liste = await ausfuehren(() =>
      kern<KalenderEintrag[]>("akten.kalender_erledigen", { eintrag_id: e.id, erledigt, vermerk }),
    );
    aktualisiert(liste, erledigt ? `„${e.titel}“ als erledigt markiert.` : `„${e.titel}“ wieder offen.`);
  }

  async function loeschen(e: KalenderEintrag) {
    setLoeschfrage(null);
    const liste = await ausfuehren(() => kern<KalenderEintrag[]>("akten.kalender_loeschen", { eintrag_id: e.id }));
    aktualisiert(liste, `„${e.titel}“ gelöscht.`);
  }

  async function vorschlaegeLaden() {
    const v = await ausfuehren(() =>
      kern<KalenderVorschlag[]>("akten.kalender_vorschlaege", { akte_id: akteId, land: fristenLand() }),
    );
    if (v) setVorschlaege(v);
  }

  function vorschlagWeg(v: KalenderVorschlag) {
    setVerworfen((alt) => new Set(alt).add(vorschlagSchluessel(v)));
  }

  async function terminZustand(e: KalenderEintrag, zustand: TerminZustand, vermerk = "", neu?: Record<string, unknown>) {
    const liste = await ausfuehren(() =>
      kern<KalenderEintrag[]>("akten.kalender_termin_zustand", { eintrag_id: e.id, zustand, vermerk, neu: neu ?? null }),
    );
    const text =
      zustand === "geplant"
        ? `„${e.titel}“ wieder als geplant geführt.`
        : zustand === "verlegt"
          ? `„${e.titel}“ verlegt auf ${datumLang(String(neu?.datum))}; der neue Termin ist eingetragen.`
          : `„${e.titel}“ am ${datumLang(e.datum)} als aufgehoben vermerkt.`;
    aktualisiert(liste, text);
    return liste;
  }

  /** Vorschlag „Termin aufgehoben/verlegt“: mit neuem Termin aus dem Dokument gleich übernehmen. */
  async function vorschlagZustand(v: KalenderVorschlag) {
    const e = eintraege?.find((x) => x.id === v.eintrag_id);
    if (!e) return;
    if (v.zustand === "verlegt" && !v.neu) {
      setFolge({ e, aktion: "verlegen", vorschlag: v });
      return;
    }
    const vermerk = `${v.vermerk ?? v.zustand} (${v.dateiname})`;
    const neu = v.neu && {
      datum: v.neu.datum,
      uhrzeit: v.neu.uhrzeit,
      ort: v.neu.ort,
      dokument_id: v.dokument_id,
      fundstelle: v.neu.fundstelle,
    };
    const liste = await terminZustand(e, v.neu ? "verlegt" : "aufgehoben", vermerk, neu);
    if (liste) vorschlagWeg(v);
  }

  const sichtbareVorschlaege = vorschlaege?.filter((v) => !verworfen.has(vorschlagSchluessel(v))) ?? null;
  const offen = (eintraege ?? []).filter((e) => !e.abgeschlossen);
  const erledigt = (eintraege ?? []).filter((e) => e.abgeschlossen);
  const verfahrenName = (id: number | null) => verfahren.find((v) => v.id === id)?.bezeichnung;

  return (
    <div className="fristen">
      <header className="fristen-kopf">
        <h2>Fristen, Termine und Wiedervorlagen</h2>
        <span className="aktionen">
          {(Object.keys(ART_TEXT) as KalenderArt[]).map((art) => (
            <button
              key={art}
              className="zweitrangig"
              onClick={() => {
                setMeldung(null);
                setEntwurf(leer(art, verfahren));
              }}
              disabled={laeuft}
            >
              + {ART_TEXT[art]}
            </button>
          ))}
          <button onClick={vorschlaegeLaden} disabled={laeuft} title="Sucht in allen Dokumenten der Akte nach Fristen und Terminen">
            Vorschläge aus Dokumenten
          </button>
        </span>
      </header>

      {fehler && <p className="fehler">{fehler}</p>}
      {meldung && <p className="meldung">{meldung}</p>}

      {entwurf && (
        <EintragFormular
          key={`${entwurf.id ?? "neu"}-${entwurf.art}-${entwurf.vorschlag?.fundstelle.abschnitt ?? ""}`}
          akteId={akteId}
          start={entwurf}
          verfahren={verfahren}
          onAbbrechen={() => setEntwurf(null)}
          onGespeichert={(liste, e) => {
            setEntwurf(null);
            aktualisiert(liste, e.id ? `„${e.titel}“ geändert.` : `„${e.titel}“ eingetragen.`);
            // Neu laden: ein eingetragener Termin kann z. B. eine spätere Terminsaufhebung erst zuordenbar machen.
            if (e.vorschlag) void vorschlaegeLaden();
          }}
        />
      )}

      {sichtbareVorschlaege && (
        <section className="karte vorschlaege" aria-label="Vorschläge aus Dokumenten">
          <div className="vorschlaege-kopf">
            <h3>Vorschläge aus Dokumenten</h3>
            <button className="link klein" onClick={() => setVorschlaege(null)}>
              Schließen
            </button>
          </div>
          <p className="erklaerung">
            JuraBox hat diese Stellen gefunden. Bitte jede prüfen, bevor sie eingetragen wird; Vorschläge ersetzen nicht
            die eigene Fristenkontrolle.
          </p>
          {sichtbareVorschlaege.length === 0 && <p className="leer">Keine neuen Fristen oder Termine in den Dokumenten gefunden.</p>}
          <ul className="vorschlag-liste">
            {sichtbareVorschlaege.map((v, i) => (
              <li key={`${v.dokument_id}-${v.fundstelle.abschnitt}-${v.art}-${i}`} className="vorschlag">
                <div className="vorschlag-zeile">
                  <span className={`art-marke ${v.art === "zustand" ? "termin" : v.art}`}>
                    {v.art === "zustand" ? (v.zustand === "verlegt" ? "Verlegung" : "Aufhebung") : ART_TEXT[v.art]}
                  </span>
                  <strong>{v.titel}</strong>
                  <span>
                    {v.datum ? datumLang(v.datum) : <em className="hinweis-text">Bezugstag fehlt</em>}
                    {v.uhrzeit && `, ${v.uhrzeit} Uhr`}
                    {v.ort && `, ${v.ort}`}
                    {v.neu && (
                      <>
                        {" → "}
                        {datumLang(v.neu.datum)}
                        {v.neu.uhrzeit && `, ${v.neu.uhrzeit} Uhr`}
                        {v.neu.ort && `, ${v.neu.ort}`}
                      </>
                    )}
                  </span>
                </div>
                <blockquote className="beleg">
                  „{v.fundstelle.text}“
                  <cite>
                    {v.dateiname}, {fundText(v.fundstelle)}
                  </cite>
                </blockquote>
                {v.berechnung && (
                  <p className="leise klein">
                    {v.berechnung.anzahl} {EINHEITEN[v.berechnung.einheit]} ab {datumLang(v.berechnung.bezugstag)}
                    {v.bezug_fundstelle && ` (${v.bezug_fundstelle.text}, ${fundText(v.bezug_fundstelle)})`}
                    {" · "}
                    {v.berechnung.grundlagen.join(", ")}
                    {v.berechnung.verschoben && ` · verschoben wegen ${v.berechnung.grund}`}
                  </p>
                )}
                {v.neu && v.neu.fundstelle.abschnitt !== v.fundstelle.abschnitt && (
                  <blockquote className="beleg">
                    „{v.neu.fundstelle.text}“
                    <cite>
                      {v.dateiname}, {fundText(v.neu.fundstelle)}
                    </cite>
                  </blockquote>
                )}
                {v.hinweis && <p className="hinweis-text klein">{v.hinweis}</p>}
                <span className="aktionen">
                  {v.art === "zustand" ? (
                    <button onClick={() => vorschlagZustand(v)} disabled={laeuft}>
                      {v.zustand === "verlegt"
                        ? v.neu
                          ? "Als verlegt übernehmen und neuen Termin eintragen"
                          : "Als verlegt übernehmen …"
                        : "Termin als aufgehoben übernehmen"}
                    </button>
                  ) : (
                    <button onClick={() => setEntwurf(ausVorschlag(v, verfahren))} disabled={laeuft}>
                      Prüfen und eintragen …
                    </button>
                  )}
                  <button className="zweitrangig" onClick={() => vorschlagWeg(v)}>
                    Verwerfen
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {loeschfrage && (
        <div className="rueckfrage" role="alertdialog" aria-label="Eintrag löschen?">
          <strong>„{loeschfrage.titel}“ am {datumLang(loeschfrage.datum)} löschen?</strong>
          <p>
            {loeschfrage.art === "termin"
              ? "Statt zu löschen lässt sich ein Termin auch als aufgehoben oder verlegt führen; dann bleibt er nachvollziehbar."
              : "Statt zu löschen lässt sich ein Eintrag auch als erledigt markieren; dann bleibt er nachvollziehbar."}
          </p>
          <div className="aktionen">
            <button className="gefahr-voll" onClick={() => loeschen(loeschfrage)}>
              Löschen
            </button>
            <button className="zweitrangig" onClick={() => setLoeschfrage(null)} autoFocus>
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {folge && (
        <FolgeFormular
          key={`${folge.e.id}-${folge.aktion}`}
          folge={folge}
          laeuft={laeuft}
          onAbbrechen={() => setFolge(null)}
          onVerlaengern={async (datum, vermerk) => {
            const liste = await ausfuehren(() =>
              kern<KalenderEintrag[]>("akten.kalender_verlaengern", { eintrag_id: folge.e.id, datum, vermerk }),
            );
            if (liste) {
              setFolge(null);
              const wort = folge.e.art === "wiedervorlage" ? "verschoben" : datum > folge.e.datum ? "verlängert" : "verkürzt";
              aktualisiert(liste, `„${folge.e.titel}“ ${wort} auf ${datumLang(datum)}.`);
            }
          }}
          onTermin={async (zustand, vermerk, neu) => {
            const v = folge.vorschlag;
            if (v && neu) Object.assign(neu, { dokument_id: v.dokument_id, fundstelle: v.fundstelle });
            const liste = await terminZustand(folge.e, zustand, v ? `${vermerk || v.vermerk} (${v.dateiname})` : vermerk, neu);
            if (liste) {
              setFolge(null);
              if (v) vorschlagWeg(v);
            }
          }}
        />
      )}

      {eintraege == null && !fehler && <p className="status">Lade …</p>}
      {eintraege != null && offen.length === 0 && (
        <LeerHinweis symbol="fristen">Keine offenen Fristen, Termine oder Wiedervorlagen.</LeerHinweis>
      )}
      {offen.length > 0 && (
        <ul className="kalender-liste">
          {offen.map((e) => (
            <EintragZeile
              key={e.id}
              e={e}
              verfahren={verfahrenName(e.verfahren_id)}
              laeuft={laeuft}
              onErledigen={() => erledigen(e, true)}
              onFolge={(aktion) => setFolge({ e, aktion })}
              onTermin={(zustand) => terminZustand(e, zustand)}
              onBearbeiten={() => setEntwurf(ausEintrag(e))}
              onLoeschen={() => setLoeschfrage(e)}
            />
          ))}
        </ul>
      )}
      {erledigt.length > 0 && (
        <details className="erledigt-liste">
          <summary>Erledigt und vergangen ({erledigt.length})</summary>
          <ul className="kalender-liste">
            {erledigt.map((e) => (
              <EintragZeile
                key={e.id}
                e={e}
                verfahren={verfahrenName(e.verfahren_id)}
                laeuft={laeuft}
                onErledigen={() => erledigen(e, false)}
                onFolge={(aktion) => setFolge({ e, aktion })}
                onTermin={(zustand) => terminZustand(e, zustand)}
                onBearbeiten={() => setEntwurf(ausEintrag(e))}
                onLoeschen={() => setLoeschfrage(e)}
              />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function EintragZeile({
  e,
  verfahren,
  laeuft,
  onErledigen,
  onFolge,
  onTermin,
  onBearbeiten,
  onLoeschen,
}: {
  e: KalenderEintrag;
  verfahren: string | undefined;
  laeuft: boolean;
  onErledigen: () => void;
  onFolge: (aktion: Folge["aktion"]) => void;
  onTermin: (zustand: TerminZustand) => void;
  onBearbeiten: () => void;
  onLoeschen: () => void;
}) {
  const b = e.berechnung;
  const termin = e.art === "termin";
  const vorfristen = [e.vorfrist, e.vorfrist2].filter((v): v is string => !!v);
  const marke =
    e.lage === "vorfrist" ? (e.vorfrist_erreicht === 2 ? "2. Vorfrist erreicht" : "Vorfrist erreicht") : abstandText(e);
  return (
    <li className={`kalender-eintrag ${e.lage}`}>
      <div className="kalender-datum">
        <strong>{datumLang(e.datum)}</strong>
        {zeitText(e) && <span>{zeitText(e)}</span>}
        <span className={`lage-marke ${e.lage}`}>{marke}</span>
      </div>
      <div className="kalender-inhalt">
        <div>
          <span className={`art-marke ${e.art}`}>{e.art_text}</span> <strong className="kalender-titel">{e.titel}</strong>
          {e.ort && <span className="leise"> · {e.ort}</span>}
        </div>
        {b && (
          <p className="leise klein" title={b.hinweise.join("\n") || undefined}>
            {b.anzahl} {EINHEITEN[b.einheit]} ab {datumLang(b.bezugstag)} ({b.grundlagen.join(", ")}
            {b.verschoben && `; verschoben wegen ${b.grund}`}; Feiertage {b.land})
          </p>
        )}
        {vorfristen.length > 0 && !e.abgeschlossen && (
          <p className="leise klein">
            {vorfristen.length === 1 ? "Vorfrist" : "Vorfristen"}: {vorfristen.map((v) => datumLang(v)).join(" und ")}
          </p>
        )}
        {e.verlauf.map((v) => (
          <p key={v.am} className="leise klein" title={v.fundstelle?.text}>
            {v.was === "verschoben" ? "Verschoben" : v.was === "verlängert" ? "Verlängert" : "Verkürzt"} am{" "}
            {datumLang(v.am.slice(0, 10))}: vom {datumLang(v.alt)} auf {datumLang(v.neu)}
            {v.vermerk && ` (${v.vermerk})`}
          </p>
        ))}
        {e.verlegt_von_termin && (
          <p className="leise klein">
            Verlegt vom {datumLang(e.verlegt_von_termin.datum)}
            {e.verlegt_von_termin.uhrzeit && `, ${e.verlegt_von_termin.uhrzeit} Uhr`}
          </p>
        )}
        {verfahren && <p className="leise klein">{verfahren}</p>}
        {e.dokument && (
          <p className="leise klein" title={e.fundstelle?.text}>
            Beleg: {e.dokument}
            {e.fundstelle && `, ${fundText(e.fundstelle)}`}
          </p>
        )}
        {e.notiz && <p className="klein">{e.notiz}</p>}
        {e.erledigt_am && (
          <p className="leise klein">
            {e.verlegt_auf ? (
              <>
                Verlegt auf {datumLang(e.verlegt_auf.datum)}
                {e.verlegt_auf.uhrzeit && `, ${e.verlegt_auf.uhrzeit} Uhr`} (vermerkt am {datumLang(e.erledigt_am.slice(0, 10))})
              </>
            ) : (
              <>
                {ABSCHLUSS_TEXT[e.zustand ?? "erledigt"]} am {datumLang(e.erledigt_am.slice(0, 10))}
              </>
            )}
            {e.erledigt_vermerk && `: ${e.erledigt_vermerk}`}
          </p>
        )}
      </div>
      <span className="kalender-aktionen">
        {!termin && (
          <button className="zweitrangig" onClick={onErledigen} disabled={laeuft}>
            {e.erledigt_am ? "Wieder öffnen" : "Erledigt"}
          </button>
        )}
        {!termin && !e.erledigt_am && (
          <button className="link klein" onClick={() => onFolge("verlaengern")} disabled={laeuft}>
            {e.art === "frist" ? "Verlängern …" : "Verschieben …"}
          </button>
        )}
        {termin && !e.abgeschlossen && (
          <>
            <button className="zweitrangig" onClick={() => onFolge("verlegen")} disabled={laeuft}>
              Verlegen …
            </button>
            <button className="link klein" onClick={() => onFolge("aufheben")} disabled={laeuft}>
              Aufgehoben …
            </button>
          </>
        )}
        {termin && (e.zustand === "aufgehoben" || e.zustand === "verlegt") && (
          <button
            className="zweitrangig"
            onClick={() => onTermin("geplant")}
            disabled={laeuft}
            title={e.verlegt_auf ? "Der neue Termin bleibt eingetragen; bei Bedarf dort löschen." : undefined}
          >
            Wieder geplant
          </button>
        )}
        <button className="link klein" onClick={onBearbeiten} disabled={laeuft}>
          Bearbeiten
        </button>
        <button className="link klein gefahr" onClick={onLoeschen} disabled={laeuft}>
          Löschen
        </button>
      </span>
    </li>
  );
}

/** Frist verlängern, Wiedervorlage verschieben, Termin verlegen oder aufheben; mit Vermerk. */
function FolgeFormular({
  folge,
  laeuft,
  onAbbrechen,
  onVerlaengern,
  onTermin,
}: {
  folge: Folge;
  laeuft: boolean;
  onAbbrechen: () => void;
  onVerlaengern: (datum: string, vermerk: string) => void;
  onTermin: (zustand: TerminZustand, vermerk: string, neu?: Record<string, unknown>) => void;
}) {
  const { e, aktion, vorschlag } = folge;
  const [datum, setDatum] = useState(aktion === "verlegen" ? "" : e.datum);
  const [uhrzeit, setUhrzeit] = useState(e.uhrzeit ?? "");
  const [bis, setBis] = useState(e.bis_uhrzeit ?? "");
  const [ort, setOrt] = useState(e.ort ?? "");
  const [vermerk, setVermerk] = useState("");
  const ueberschrift =
    aktion === "verlegen"
      ? "Termin verlegen"
      : aktion === "aufheben"
        ? "Termin aufgehoben"
        : e.art === "frist"
          ? "Frist verlängern"
          : "Wiedervorlage verschieben";

  function absenden(ev: FormEvent) {
    ev.preventDefault();
    if (aktion === "verlaengern") onVerlaengern(datum, vermerk);
    else if (aktion === "aufheben") onTermin("aufgehoben", vermerk);
    else onTermin("verlegt", vermerk, { datum, uhrzeit, bis_uhrzeit: bis, ort });
  }

  return (
    <form className="karte kalender-formular" onSubmit={absenden}>
      <h3>
        {ueberschrift}: {e.titel} <span className="leise">({datumLang(e.datum)}{e.uhrzeit && `, ${e.uhrzeit} Uhr`})</span>
      </h3>
      {vorschlag && (
        <blockquote className="beleg">
          „{vorschlag.fundstelle.text}“
          <cite>
            {vorschlag.dateiname}, {fundText(vorschlag.fundstelle)}
          </cite>
        </blockquote>
      )}
      {aktion === "verlaengern" && e.art === "frist" && (
        <p className="erklaerung">
          Das bisherige Fristende bleibt im Verlauf sichtbar. Die Vorfristen rücken um denselben Abstand mit.
        </p>
      )}
      {aktion === "verlegen" && (
        <p className="erklaerung">Der alte Termin bleibt als „verlegt“ stehen; der neue wird mit Verweis darauf eingetragen.</p>
      )}
      <div className="formular-raster">
        {aktion !== "aufheben" && (
          <label className="feld">
            {aktion === "verlegen" ? "Neuer Termin am" : e.art === "frist" ? "Neues Fristende" : "Neuer Tag"}
            <input type="date" autoFocus value={datum} onChange={(x) => setDatum(x.target.value)} />
          </label>
        )}
        {aktion === "verlegen" && (
          <>
            <label className="feld">
              Uhrzeit
              <span className="dauer">
                <input type="time" value={uhrzeit} onChange={(x) => setUhrzeit(x.target.value)} aria-label="Beginn" />
                bis
                <input type="time" value={bis} onChange={(x) => setBis(x.target.value)} aria-label="Ende (optional)" />
              </span>
            </label>
            <label className="feld">
              Ort
              <input value={ort} onChange={(x) => setOrt(x.target.value)} placeholder="z. B. Saal 104" />
            </label>
          </>
        )}
        <label className="feld feld-breit">
          Vermerk (optional)
          <input
            autoFocus={aktion === "aufheben"}
            value={vermerk}
            onChange={(x) => setVermerk(x.target.value)}
            placeholder={
              aktion === "verlaengern"
                ? "z. B. Verlängerung gewährt mit Verfügung vom …"
                : aktion === "aufheben"
                  ? "z. B. Vergleich geschlossen"
                  : "z. B. auf Antrag des Beklagten"
            }
          />
        </label>
      </div>
      <span className="aktionen">
        <button type="submit" disabled={laeuft || (aktion !== "aufheben" && (!datum || (aktion === "verlaengern" && datum === e.datum)))}>
          {aktion === "verlegen" ? "Verlegen" : aktion === "aufheben" ? "Als aufgehoben vermerken" : "Übernehmen"}
        </button>
        <button type="button" className="zweitrangig" onClick={onAbbrechen}>
          Abbrechen
        </button>
      </span>
    </form>
  );
}

function EintragFormular({
  akteId,
  start,
  verfahren,
  onAbbrechen,
  onGespeichert,
}: {
  akteId: number;
  start: Entwurf;
  verfahren: Verfahren[];
  onAbbrechen: () => void;
  onGespeichert: (liste: KalenderEintrag[], e: Entwurf) => void;
}) {
  const [e, setE] = useState<Entwurf>(start);
  const [ergebnis, setErgebnis] = useState<FristBerechnung | null>(null);
  const [rechenfehler, setRechenfehler] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const setze = (teil: Partial<Entwurf>) => setE((alt) => ({ ...alt, ...teil }));
  const berechnen = e.art === "frist" && e.modus === "berechnen";
  const land = fristenLand();

  // Fristende live über den Fristenrechner des Kerns (§§ 187, 188, 193 BGB).
  useEffect(() => {
    if (!berechnen || !e.bezugstag || !Number(e.anzahl)) {
      setErgebnis(null);
      setRechenfehler(null);
      return;
    }
    let aktuell = true;
    kern<FristBerechnung>("akten.frist_berechnen", {
      bezugstag: e.bezugstag,
      anzahl: Number(e.anzahl),
      einheit: e.einheit,
      land,
    }).then(
      (r) => {
        if (!aktuell) return;
        setErgebnis(r);
        setRechenfehler(null);
      },
      (f) => aktuell && (setErgebnis(null), setRechenfehler(String(f))),
    );
    return () => {
      aktuell = false;
    };
  }, [berechnen, e.bezugstag, e.anzahl, e.einheit, land]);

  async function speichern(ev: FormEvent) {
    ev.preventDefault();
    setLaeuft(true);
    setFehler(null);
    const daten: Record<string, unknown> = {
      art: e.art,
      titel: e.titel,
      uhrzeit: e.art === "termin" ? e.uhrzeit : "",
      bis_uhrzeit: e.art === "termin" ? e.bis_uhrzeit : "",
      ort: e.art === "termin" ? e.ort : "",
      vorfrist: e.art === "frist" ? e.vorfrist : "",
      vorfrist2: e.art === "frist" ? e.vorfrist2 : "",
      verfahren_id: e.verfahren_id || null,
      notiz: e.notiz,
      dokument_id: e.dokument_id,
      fundstelle: e.fundstelle,
    };
    if (berechnen) {
      daten.berechnung = { bezugstag: e.bezugstag, anzahl: Number(e.anzahl), einheit: e.einheit, land };
    } else {
      daten.berechnung = null;
      daten.datum = e.datum;
    }
    try {
      const liste = await kern<KalenderEintrag[]>("akten.kalender_speichern", {
        akte_id: akteId,
        daten,
        eintrag_id: e.id,
      });
      onGespeichert(liste, e);
    } catch (f) {
      setFehler(String(f));
      setLaeuft(false);
    }
  }

  const ende = berechnen ? ergebnis?.ende : e.datum;

  return (
    <form className="karte kalender-formular" onSubmit={speichern}>
      <h3>
        {e.id ? `${ART_TEXT[e.art]} bearbeiten` : `${ART_TEXT[e.art]} eintragen`}
        {e.vorschlag && <span className="leise"> (Vorschlag aus {e.dateiname})</span>}
      </h3>
      {e.fundstelle && (
        <blockquote className="beleg">
          „{e.fundstelle.text}“
          <cite>
            {e.dateiname}, {fundText(e.fundstelle)}
          </cite>
        </blockquote>
      )}
      <div className="formular-raster">
        {!e.id && (
          <label className="feld">
            Art
            <select value={e.art} onChange={(ev) => setze({ art: ev.target.value as KalenderArt })}>
              {(Object.keys(ART_TEXT) as KalenderArt[]).map((a) => (
                <option key={a} value={a}>
                  {ART_TEXT[a]}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="feld feld-breit">
          Worum geht es?
          <input
            autoFocus
            list={`titel-${e.art}`}
            value={e.titel}
            onChange={(ev) => setze({ titel: ev.target.value })}
            placeholder={TITEL_VORSCHLAEGE[e.art][0]}
          />
          <datalist id={`titel-${e.art}`}>
            {TITEL_VORSCHLAEGE[e.art].map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </label>

        {e.art === "frist" && (
          <fieldset className="feld feld-breit modus-wahl">
            <legend>Fristende</legend>
            <label>
              <input type="radio" checked={e.modus === "berechnen"} onChange={() => setze({ modus: "berechnen" })} />{" "}
              mit dem Fristenrechner berechnen
            </label>
            <label>
              <input type="radio" checked={e.modus === "datum"} onChange={() => setze({ modus: "datum" })} /> Datum
              eingeben
            </label>
          </fieldset>
        )}

        {berechnen ? (
          <>
            <label className="feld">
              Bezugstag (z. B. Zustellung)
              <input type="date" value={e.bezugstag} onChange={(ev) => setze({ bezugstag: ev.target.value })} />
            </label>
            <label className="feld">
              Dauer
              <span className="dauer">
                <input
                  type="number"
                  min={1}
                  value={e.anzahl}
                  onChange={(ev) => setze({ anzahl: ev.target.value })}
                  aria-label="Anzahl"
                />
                <select
                  value={e.einheit}
                  onChange={(ev) => setze({ einheit: ev.target.value as FristBerechnung["einheit"] })}
                  aria-label="Einheit"
                >
                  {Object.entries(EINHEITEN).map(([k, t]) => (
                    <option key={k} value={k}>
                      {t}
                    </option>
                  ))}
                </select>
              </span>
            </label>
            <div className="feld feld-breit frist-ergebnis" aria-live="polite">
              {ergebnis ? (
                <>
                  <strong>Fristende: {datumLang(ergebnis.ende)}</strong>
                  <span className="leise">
                    {ergebnis.grundlagen.join(", ")}
                    {ergebnis.verschoben && `; verschoben wegen ${ergebnis.grund}`} · Feiertage {ergebnis.land} (wie im
                    Fristenrechner der Toolbox)
                  </span>
                  {ergebnis.hinweise.map((h) => (
                    <span key={h} className="hinweis-text">
                      {h}
                    </span>
                  ))}
                </>
              ) : (
                <span className="leise">{rechenfehler ?? "Bezugstag und Dauer eingeben, dann rechnet JuraBox das Fristende."}</span>
              )}
            </div>
          </>
        ) : (
          <label className="feld">
            {e.art === "frist" ? "Fristende" : e.art === "termin" ? "Termin am" : "Wiedervorlage am"}
            <input type="date" value={e.datum} onChange={(ev) => setze({ datum: ev.target.value })} />
          </label>
        )}

        {e.art === "termin" && (
          <>
            <label className="feld">
              Uhrzeit
              <span className="dauer">
                <input
                  type="time"
                  value={e.uhrzeit}
                  onChange={(ev) => setze({ uhrzeit: ev.target.value })}
                  aria-label="Beginn"
                />
                bis
                <input
                  type="time"
                  value={e.bis_uhrzeit}
                  onChange={(ev) => setze({ bis_uhrzeit: ev.target.value })}
                  aria-label="Ende (optional)"
                  title="Ende (optional)"
                />
              </span>
            </label>
            <label className="feld">
              Ort
              <input value={e.ort} onChange={(ev) => setze({ ort: ev.target.value })} placeholder="z. B. Saal 104" />
            </label>
          </>
        )}
        {e.art === "frist" && (
          <div className="feld feld-breit">
            Vorfristen (optional)
            <span className="dauer">
              <input
                type="date"
                value={e.vorfrist}
                onChange={(ev) => setze({ vorfrist: ev.target.value })}
                aria-label="Erste Vorfrist"
              />
              <input
                type="date"
                value={e.vorfrist2}
                onChange={(ev) => setze({ vorfrist2: ev.target.value })}
                aria-label="Zweite Vorfrist"
              />
              {ende && (
                <button
                  type="button"
                  className="link klein"
                  onClick={() => setze({ vorfrist: minusTage(ende, 7), vorfrist2: minusTage(ende, 2) })}
                >
                  1 Woche und 2 Tage vorher
                </button>
              )}
            </span>
          </div>
        )}
        {verfahren.length > 0 && (
          <label className="feld feld-breit">
            Verfahren
            <select value={e.verfahren_id} onChange={(ev) => setze({ verfahren_id: ev.target.value })}>
              <option value="">(ohne)</option>
              {verfahren.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.bezeichnung}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="feld feld-breit">
          Notiz (optional)
          <textarea rows={2} value={e.notiz} onChange={(ev) => setze({ notiz: ev.target.value })} />
        </label>
      </div>
      <span className="aktionen">
        <button type="submit" disabled={laeuft || !e.titel.trim() || (berechnen ? !ergebnis : !e.datum)}>
          {e.id ? "Speichern" : "Eintragen"}
        </button>
        <button type="button" className="zweitrangig" onClick={onAbbrechen}>
          Abbrechen
        </button>
      </span>
      {fehler && <p className="fehler">{fehler}</p>}
    </form>
  );
}
