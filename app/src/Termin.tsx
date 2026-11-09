import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFremdeAenderung } from "./aenderungen";
import { SprungZiel, springTreffer } from "./arbeitsfensterLogik";
import Dialog from "./Dialog";
import {
  PUNKT_AMPEL_TEXT,
  Akte,
  AktenDokument,
  Ampel,
  FristVorschlag,
  KiWidersprueche,
  NormEintrag,
  Notiz,
  PunktArt,
  PunktBeleg,
  Sitzung,
  SitzungsAbschluss,
  SitzungsPunkt,
  TERMIN_NOTIZ_ARTEN,
  TerminHeute,
  TerminNotizArt,
  ZeitEinstellungen,
  betragAnzeige,
  datumDe,
  dokumentName,
  istDesktop,
  kern,
  laufzeit,
  uhrzeitVon,
  fristenLand,
  type FristBerechnung,
  type AktenOptionen,
} from "./kern";
import { useKiAn } from "./kiSchalter";
import { useBearbeitung } from "./ungespeichert";

/** Öffnet ein Dokument in einer passenden Spalte des Arbeitsfensters (an Abschnitt oder Randnummer). */
export type DokumentOeffnen = (dokumentId: number, ziel?: { abschnitt?: number | null; rn?: number | null }) => void;

// --------------------------------------------------------------------------- Laufende Sitzung

/** Laufende Sitzung der Akte; lädt neu, wenn ein anderes Fenster etwas daran ändert. */
export function useSitzung(akteId: number) {
  const [sitzung, setSitzung] = useState<Sitzung | null>(null);
  const [geladen, setGeladen] = useState(false);
  const laden = useCallback(async () => {
    if (!istDesktop) return;
    try {
      setSitzung(await kern<Sitzung | null>("sitzung.aktiv", { akte_id: akteId }));
    } finally {
      setGeladen(true);
    }
  }, [akteId]);
  useEffect(() => {
    void laden();
  }, [laden]);
  useFremdeAenderung(["sitzung"], () => void laden());
  return { sitzung, setSitzung, geladen, laden };
}

/** Uhr des laufenden Termins, sekündlich. */
export function TerminUhr({ beginn }: { beginn: string }) {
  const [jetzt, setJetzt] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setJetzt(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const ms = jetzt - new Date(beginn).getTime();
  return (
    <span className="af-uhr" role="timer" aria-label={`Termin läuft seit ${uhrzeitVon(beginn)} Uhr`}>
      <span aria-hidden>⏱</span> {laufzeit(ms)}
    </span>
  );
}

// --------------------------------------------------------------------------- Termin beginnen

export function TerminBeginnen({
  akteId,
  sachbearbeiterId,
  onBegonnen,
  onAbbrechen,
}: {
  akteId: number;
  /** Vorauswahl für „Termin nimmt wahr“: der Sachbearbeiter der Akte. */
  sachbearbeiterId: number | null;
  onBegonnen: (s: Sitzung) => void;
  onAbbrechen: () => void;
}) {
  const [termine, setTermine] = useState<TerminHeute[] | null>(null);
  const [wahl, setWahl] = useState<string>("");
  const [titel, setTitel] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [personen, setPersonen] = useState<{ id: number; name: string }[]>([]);
  const [person, setPerson] = useState(sachbearbeiterId == null ? "" : String(sachbearbeiterId));
  useEffect(() => {
    kern<AktenOptionen>("akten.optionen").then(
      (o) => setPersonen(o.sachbearbeiter),
      () => setPersonen([]),
    );
  }, []);
  useEffect(() => {
    kern<TerminHeute[]>("sitzung.termine_heute", { akte_id: akteId }).then(
      (t) => {
        setTermine(t);
        if (t.length) setWahl(String(t[0].id));
      },
      () => setTermine([]),
    );
  }, [akteId]);

  async function beginnen(e: FormEvent) {
    e.preventDefault();
    try {
      onBegonnen(
        await kern<Sitzung>("sitzung.beginnen", {
          akte_id: akteId,
          kalender_id: wahl ? Number(wahl) : null,
          titel,
          person_id: person ? Number(person) : null,
        }),
      );
    } catch (x) {
      setFehler(String(x));
    }
  }

  return (
    <div className="timer-hinweis-hintergrund">
      <Dialog className="rueckfrage timer-hinweis af-dialog" label="Termin beginnen" onSchliessen={onAbbrechen}>
        <form onSubmit={beginnen}>
          <strong>Termin beginnen</strong>
          <p>
            Das Arbeitsfenster zeigt dann Sitzungsblatt, ein Dokument und die Terminsnotizen. Notizen bekommen die
            Uhrzeit, zu der du sie speicherst. Die vorherige Anordnung kommt nach dem Termin zurück.
          </p>
          {termine && termine.length > 0 && (
            <label className="feld">
              Termin aus dem Kalender
              <select value={wahl} onChange={(e) => setWahl(e.target.value)}>
                {termine.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.uhrzeit ? `${t.uhrzeit} Uhr · ` : ""}
                    {t.titel}
                    {t.ort ? ` · ${t.ort}` : ""}
                  </option>
                ))}
                <option value="">ohne Kalendertermin</option>
              </select>
            </label>
          )}
          {(!wahl || (termine && termine.length === 0)) && (
            <label className="feld">
              Bezeichnung (wahlweise)
              <input value={titel} onChange={(e) => setTitel(e.target.value)} placeholder="z. B. LG Freiburg, Saal 2.14" />
            </label>
          )}
          <label className="feld">
            Termin nimmt wahr
            <select value={person} onChange={(e) => setPerson(e.target.value)}>
              {person && !personen.some((p) => String(p.id) === person) && <option value={person}>Sachbearbeiter der Akte</option>}
              {personen.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.id === sachbearbeiterId ? " (Sachbearbeiter der Akte)" : ""}
                </option>
              ))}
              <option value="">ohne Angabe</option>
            </select>
            {personen.length === 0 && (
              <span className="leise klein">Personen legst du unter Einstellungen › Eigene Daten an.</span>
            )}
          </label>
          {fehler && <p className="fehler">{fehler}</p>}
          <div className="aktionen">
            <button type="submit" autoFocus>
              Termin beginnen
            </button>
            <button type="button" className="zweitrangig" onClick={onAbbrechen}>
              Abbrechen
            </button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

// --------------------------------------------------------------------------- Termin beenden

interface FristWahl extends FristVorschlag {
  an: boolean;
  /** Bei offenem Beginn: Tag des Ereignisses (etwa der Zustellung), von Hand eingetragen. */
  ereignistag?: string;
  rechenfehler?: string | null;
}

export function TerminBeenden({
  sitzung,
  onBeendet,
  onAbbrechen,
}: {
  sitzung: Sitzung;
  onBeendet: (s: Sitzung) => void;
  onAbbrechen: () => void;
}) {
  const [abschluss, setAbschluss] = useState<SitzungsAbschluss | null>(null);
  const [zeitE, setZeitE] = useState<ZeitEinstellungen | null>(null);
  const [protokoll, setProtokoll] = useState(true);
  const [zeitAn, setZeitAn] = useState(true);
  const [minuten, setMinuten] = useState("");
  const [taetigkeit, setTaetigkeit] = useState("");
  const [bearbeiter, setBearbeiter] = useState("");
  const [fristen, setFristen] = useState<FristWahl[]>([]);
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);

  useEffect(() => {
    kern<SitzungsAbschluss>("sitzung.abschluss", { sitzung_id: sitzung.id, land: fristenLand() }).then(
      (a) => {
        setAbschluss(a);
        setMinuten(String(a.minuten));
        setTaetigkeit(a.taetigkeit);
        setFristen(a.fristen.map((f) => ({ ...f, an: f.beginn_offen == null })));
        // Zeit für den, der den Termin wahrgenommen hat.
        if (a.bearbeiter_id != null) setBearbeiter(String(a.bearbeiter_id));
      },
      (e) => setFehler(String(e)),
    );
    kern<ZeitEinstellungen>("zeit.einstellungen").then(
      (z) => {
        setZeitE(z);
        const b = z.standard_bearbeiter_id ?? z.bearbeiter.find((x) => !x.archiviert)?.id ?? null;
        setBearbeiter((alt) => alt || (b == null ? "" : String(b)));
        if (b == null) setZeitAn(false);
      },
      () => setZeitAn(false),
    );
  }, [sitzung.id]);

  function aendereFrist(i: number, teil: Partial<FristWahl>) {
    setFristen((alt) => alt.map((x, j) => (j === i ? { ...x, ...teil } : x)));
  }

  /** Offener Beginn: Fristende aus dem eingetragenen Ereignistag über den Fristenrechner. */
  function ereignistagSetzen(i: number, f: FristWahl, tag: string) {
    aendereFrist(i, { ereignistag: tag, rechenfehler: null });
    if (!tag || f.anzahl == null || f.einheit == null) return;
    kern<FristBerechnung>("akten.frist_berechnen", { bezugstag: tag, anzahl: f.anzahl, einheit: f.einheit, land: fristenLand() }).then(
      (r) => aendereFrist(i, { datum: r.ende, bezugstag: tag, verschoben: r.verschoben, grund: r.grund, an: true }),
      (e) => aendereFrist(i, { rechenfehler: String(e) }),
    );
  }

  async function beenden() {
    setFehler(null);
    setLaeuft(true);
    try {
      const s = await kern<Sitzung>("sitzung.beenden", {
        sitzung_id: sitzung.id,
        protokoll,
        zeit: zeitAn ? { minuten: Number(minuten), taetigkeit, bearbeiter_id: bearbeiter ? Number(bearbeiter) : null } : null,
        fristen: fristen.filter((f) => f.an && f.datum).map((f) => ({ titel: f.titel, datum: f.datum, quelle: f.quelle })),
      });
      onBeendet(s);
    } catch (e) {
      setFehler(String(e));
    } finally {
      setLaeuft(false);
    }
  }

  const bearbeiterListe = zeitE?.bearbeiter.filter((b) => !b.archiviert) ?? [];
  return (
    <div className="timer-hinweis-hintergrund">
      <Dialog className="rueckfrage timer-hinweis af-dialog af-beenden" label="Termin beenden" onSchliessen={onAbbrechen}>
        <strong>Termin beenden</strong>
        <p>Wähle, was übernommen wird. Ohne Haken bleibt nur das Terminsprotokoll im Arbeitsfenster gespeichert.</p>
        {!abschluss && !fehler && <p className="leise">Lade …</p>}
        {abschluss && (
          <>
            <label className="af-haken">
              <input type="checkbox" checked={protokoll} onChange={(e) => setProtokoll(e.target.checked)} disabled={sitzung.notizen.length === 0} />
              Terminsnotizen als Aktennotiz übernehmen
              {sitzung.notizen.length === 0 && <span className="leise"> (keine Notizen)</span>}
            </label>
            {protokoll && sitzung.notizen.length > 0 && <pre className="af-protokoll">{abschluss.protokoll}</pre>}

            <label className="af-haken">
              <input type="checkbox" checked={zeitAn} onChange={(e) => setZeitAn(e.target.checked)} disabled={bearbeiterListe.length === 0} />
              Zeit erfassen
              {bearbeiterListe.length === 0 && <span className="leise"> (erst Bearbeiter anlegen: Einstellungen → Zeiterfassung)</span>}
            </label>
            {zeitAn && (
              <div className="af-zeit-felder">
                <label className="feld">
                  Minuten
                  <input type="number" min={1} max={1440} value={minuten} onChange={(e) => setMinuten(e.target.value)} />
                </label>
                <label className="feld">
                  Bearbeiter
                  <select value={bearbeiter} onChange={(e) => setBearbeiter(e.target.value)}>
                    {bearbeiterListe.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="feld af-breit">
                  Tätigkeit
                  <input value={taetigkeit} onChange={(e) => setTaetigkeit(e.target.value)} />
                </label>
              </div>
            )}

            <p className="af-zwischen">
              <strong>Fristen aus den Notizen</strong>
            </p>
            {fristen.length === 0 && <p className="leise">Keine erkannt. Fristen lassen sich jederzeit im Reiter „Fristen“ anlegen.</p>}
            {fristen.map((f, i) => {
              const einheit = f.einheit === "tage" ? "Tage" : f.einheit === "wochen" ? "Wochen" : "Monate";
              return (
                <div key={f.notiz_id} className="af-frist">
                  <label className="af-haken">
                    <input
                      type="checkbox"
                      checked={f.an}
                      disabled={!f.datum}
                      onChange={(e) => aendereFrist(i, { an: e.target.checked })}
                    />
                    Frist anlegen
                  </label>
                  {f.beginn_offen && (
                    <p className="af-frist-offen af-breit" role="note">
                      {f.bezugstag
                        ? `Fristbeginn: ${f.beginn_offen} am ${datumDe(f.bezugstag)}. Das Fristende ist daraus berechnet, bitte prüfen.`
                        : `Fristbeginn offen: ${f.anzahl} ${einheit} ab ${f.beginn_offen}. Das Datum steht noch nicht fest. Trag den Tag ein, sobald er bekannt ist; sonst wird diese Frist nicht angelegt und du legst sie später im Reiter „Fristen“ an.`}
                    </p>
                  )}
                  <label className="feld af-breit">
                    Bezeichnung
                    <input value={f.titel} onChange={(e) => aendereFrist(i, { titel: e.target.value })} />
                  </label>
                  {f.beginn_offen && (
                    <label className="feld">
                      {f.beginn_offen} am
                      <input type="date" value={f.ereignistag ?? ""} onChange={(e) => ereignistagSetzen(i, f, e.target.value)} />
                    </label>
                  )}
                  <label className="feld">
                    Fristende
                    <input type="date" value={f.datum ?? ""} onChange={(e) => aendereFrist(i, { datum: e.target.value || null, an: !!e.target.value })} />
                  </label>
                  {f.rechenfehler && <p className="fehler af-breit">{f.rechenfehler}</p>}
                  <p className="leise af-breit">
                    {f.art === "datum" ? (
                      <>
                        Festes Datum aus der Notiz · {f.quelle}.
                        {f.kein_werktag ? ` Achtung: Der Tag ist ein ${f.kein_werktag}, bitte prüfen (§ 222 Abs. 2 ZPO).` : ""}
                      </>
                    ) : f.beginn_offen ? (
                      <>
                        {f.bezugstag ? `${f.anzahl} ${einheit} ab ${datumDe(f.bezugstag)}` : "Noch kein Fristende"}
                        {f.verschoben && f.grund ? ` · verschoben: ${f.grund}` : ""} · {f.quelle}.
                      </>
                    ) : (
                      <>
                        {f.anzahl} {einheit} ab {f.bezugstag ? datumDe(f.bezugstag) : "?"}
                        {f.verschoben && f.grund ? ` · verschoben: ${f.grund}` : ""} · {f.quelle}. Bitte prüfen, der Beginn kann
                        abweichen (etwa ab Zustellung des Protokolls).
                      </>
                    )}
                  </p>
                </div>
              );
            })}
          </>
        )}
        {fehler && (
          <p className="fehler" role="alert">
            {fehler}
          </p>
        )}
        <div className="aktionen">
          <button onClick={() => void beenden()} disabled={!abschluss || laeuft}>
            Termin beenden
          </button>
          <button className="zweitrangig" onClick={onAbbrechen} autoFocus>
            Zurück zum Termin
          </button>
        </div>
      </Dialog>
    </div>
  );
}

// --------------------------------------------------------------------------- Sichtschutz

/** Deckt den Inhalt vollständig ab, z. B. wenn Gegenseite oder Publikum auf den Bildschirm sehen können. */
export function Sichtschutz({ onAufheben }: { onAufheben: () => void }) {
  const knopf = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    knopf.current?.focus();
    const titel = document.title;
    document.title = "advOrdo";
    return () => {
      document.title = titel;
    };
  }, []);
  return (
    <div className="af-sichtschutz" role="dialog" aria-modal="true" aria-label="Sichtschutz">
      <button ref={knopf} className="af-sichtschutz-knopf" onClick={onAufheben}>
        Sichtschutz aufheben (F9)
      </button>
    </div>
  );
}

// --------------------------------------------------------------------------- Springen (Strg+K)

export function Springen({
  akteId,
  dokumente,
  offen,
  onZiel,
  onSchliessen,
}: {
  akteId: number;
  dokumente: AktenDokument[];
  /** Dokumente, die gerade in einer Spalte offen sind (für „Rn. 14“). */
  offen: number[];
  onZiel: (z: SprungZiel) => void;
  onSchliessen: () => void;
}) {
  const [eingabe, setEingabe] = useState("");
  const [normen, setNormen] = useState<NormEintrag[]>([]);
  const [aktiv, setAktiv] = useState(0);
  useEffect(() => {
    kern<NormEintrag[]>("akten.normen", { akte_id: akteId, dokument_id: null }).then(setNormen, () => setNormen([]));
  }, [akteId]);
  const treffer = useMemo(
    () =>
      springTreffer(
        eingabe,
        dokumente.map((d) => ({ id: d.id, name: dokumentName(d), tags: d.tags.map((t) => t.name) })),
        normen,
        offen,
      ),
    [eingabe, dokumente, normen, offen],
  );
  useEffect(() => setAktiv(0), [eingabe]);

  function taste(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setAktiv((a) => Math.min(a + 1, treffer.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setAktiv((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && treffer[aktiv]) {
      e.preventDefault();
      onZiel(treffer[aktiv]);
    }
  }

  return (
    <div className="timer-hinweis-hintergrund af-springen-hintergrund">
      <Dialog className="af-springen" label="Springen" onSchliessen={onSchliessen}>
        <input
          autoFocus
          className="af-springen-feld"
          value={eingabe}
          onChange={(e) => setEingabe(e.target.value)}
          onKeyDown={taste}
          placeholder="Springen: „K 2“, „B 1“, „Rn. 14“, „§ 477“ oder Teil des Namens"
          aria-label="Springen zu Anlage, Randnummer, Norm oder Dokument"
          role="combobox"
          aria-expanded={treffer.length > 0}
          aria-controls="af-springen-liste"
          aria-activedescendant={treffer.length ? `af-sprung-${aktiv}` : undefined}
        />
        <ul id="af-springen-liste" role="listbox" className="af-springen-liste">
          {treffer.map((t, i) => (
            <li
              key={`${t.dokumentId}-${t.abschnitt ?? ""}-${t.rn ?? ""}-${i}`}
              id={`af-sprung-${i}`}
              role="option"
              aria-selected={i === aktiv}
              className={i === aktiv ? "aktiv" : undefined}
              onMouseEnter={() => setAktiv(i)}
              onClick={() => onZiel(t)}
            >
              <strong>{t.titel}</strong> <span className="leise">{t.hinweis}</span>
            </li>
          ))}
        </ul>
        {eingabe.trim() && treffer.length === 0 && (
          <p className="leise af-springen-leer">
            Nichts gefunden. Anlagen findet die App über die Tags der Dokumente (z. B. „Anlage K 2“); Randnummern in den
            Dokumenten, die gerade in einer Spalte offen sind.
          </p>
        )}
      </Dialog>
    </div>
  );
}

// --------------------------------------------------------------------------- Sitzungsblatt

interface PunktEntwurf {
  id: number | null;
  art: PunktArt;
  text: string;
  ampel: Ampel | "";
  belege: PunktBeleg[];
  herkunft: "eigen" | "ki";
}

function AmpelMarke({ ampel }: { ampel: Ampel | null }) {
  if (!ampel) return null;
  return (
    <span className={`af-ampel af-ampel-${ampel}`} title={PUNKT_AMPEL_TEXT[ampel]}>
      <span className="nur-vorlesen">{PUNKT_AMPEL_TEXT[ampel]}: </span>
    </span>
  );
}

export function SitzungsblattSpalte({
  akte,
  dokumente,
  onOeffnen,
}: {
  akte: Akte | null;
  dokumente: AktenDokument[];
  onOeffnen: DokumentOeffnen;
}) {
  const akteId = akte?.id;
  const kiAn = useKiAn();
  const [punkte, setPunkte] = useState<SitzungsPunkt[] | null>(null);
  const [angeheftet, setAngeheftet] = useState<Notiz[]>([]);
  const [entwurf, setEntwurf] = useState<PunktEntwurf | null>(null);
  const [vorschlaege, setVorschlaege] = useState<KiWidersprueche["widersprueche"] | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const bearb = useBearbeitung("Punkt im Sitzungsblatt");

  const laden = useCallback(async () => {
    if (akteId == null || !istDesktop) return;
    try {
      const [p, n] = await Promise.all([
        kern<SitzungsPunkt[]>("sitzung.punkte", { akte_id: akteId }),
        kern<Notiz[]>("akten.notizen", { akte_id: akteId }),
      ]);
      setPunkte(p);
      setAngeheftet(n.filter((x) => x.angeheftet));
    } catch (e) {
      setFehler(String(e));
    }
  }, [akteId]);
  useEffect(() => {
    void laden();
  }, [laden]);
  useFremdeAenderung(["sitzung", "notizen"], () => void laden());

  async function aufruf(f: () => Promise<SitzungsPunkt[]>) {
    setFehler(null);
    try {
      setPunkte(await f());
      return true;
    } catch (e) {
      setFehler(String(e));
      return false;
    }
  }

  async function speichern(e: FormEvent) {
    e.preventDefault();
    if (!entwurf || akteId == null) return;
    const ok = await aufruf(() =>
      kern("sitzung.punkt_speichern", {
        akte_id: akteId,
        punkt_id: entwurf.id,
        daten: { art: entwurf.art, text: entwurf.text, ampel: entwurf.ampel || null, belege: entwurf.belege, herkunft: entwurf.herkunft },
      }),
    );
    if (ok) {
      setEntwurf(null);
      bearb.erledigt();
    }
  }

  async function vorschlaegeLaden() {
    if (akteId == null) return;
    try {
      const e = await kern<{ widersprueche: KiWidersprueche | null }>("ki.ergebnisse", { akte_id: akteId });
      setVorschlaege(e.widersprueche?.widersprueche ?? []);
    } catch (x) {
      setFehler(String(x));
    }
  }

  async function vorschlagUebernehmen(w: KiWidersprueche["widersprueche"][number]) {
    if (akteId == null) return;
    const belege = w.angaben.map((a) => ({ dokument_id: a.fundstelle.dokument_id, abschnitt: a.fundstelle.abschnitt, rn: a.fundstelle.rn }));
    const eindeutig = belege.filter((b, i) => belege.findIndex((x) => x.dokument_id === b.dokument_id && x.abschnitt === b.abschnitt) === i);
    const ok = await aufruf(() =>
      kern("sitzung.punkt_speichern", {
        akte_id: akteId,
        daten: { art: "streitpunkt", text: w.thema, ampel: "gelb", belege: eindeutig, herkunft: "ki" },
      }),
    );
    if (ok) setVorschlaege((v) => v?.filter((x) => x !== w) ?? null);
  }

  if (!akte) return <p className="leise">Lade …</p>;
  const gericht = akte.gerichte[0];
  const antraege = punkte?.filter((p) => p.art === "antrag") ?? [];
  const streit = punkte?.filter((p) => p.art === "streitpunkt") ?? [];

  const punktListe = (liste: SitzungsPunkt[]) => (
    <ul className="af-punkte">
      {liste.map((p, i) =>
        entwurf?.id === p.id ? (
          <li key={p.id}>{entwurfFormular()}</li>
        ) : (
          <li key={p.id} className="af-punkt">
            <div className="af-punkt-text">
              <AmpelMarke ampel={p.ampel} />
              <span className="af-punkt-inhalt">
                {p.text}
                {p.herkunft === "ki" && (
                  <>
                    {" "}
                    <span className="af-ki-marke" title="Aus einem Vorschlag der Analyse übernommen">
                      aus Analyse
                    </span>
                  </>
                )}
              </span>
            </div>
            <div className="af-belege">
              {p.belege.length === 0 && p.art === "streitpunkt" && <span className="leise">ohne Fundstelle</span>}
              {p.belege.map((b, j) => (
                <button key={j} className="link" onClick={() => onOeffnen(b.dokument_id, { abschnitt: b.abschnitt, rn: b.rn })}>
                  {b.bezeichnung}
                </button>
              ))}
            </div>
            <div className="af-punkt-aktionen">
              <button className="link" onClick={() => setEntwurf({ id: p.id, art: p.art, text: p.text, ampel: p.ampel ?? "", belege: p.belege, herkunft: p.herkunft })}>
                Bearbeiten
              </button>
              <button className="link" disabled={i === 0} onClick={() => void aufruf(() => kern("sitzung.punkt_verschieben", { punkt_id: p.id, richtung: -1 }))} aria-label={`${p.text} nach oben`}>
                ↑
              </button>
              <button
                className="link"
                disabled={i === liste.length - 1}
                onClick={() => void aufruf(() => kern("sitzung.punkt_verschieben", { punkt_id: p.id, richtung: 1 }))}
                aria-label={`${p.text} nach unten`}
              >
                ↓
              </button>
              <button className="link gefahr" onClick={() => void aufruf(() => kern("sitzung.punkt_loeschen", { punkt_id: p.id }))}>
                Entfernen
              </button>
            </div>
          </li>
        ),
      )}
    </ul>
  );

  function entwurfFormular() {
    if (!entwurf) return null;
    const e = entwurf;
    return (
      <form className="af-punkt-form" onSubmit={speichern} {...bearb.formular}>
        <label className="feld">
          {e.art === "antrag" ? "Antrag" : "Streitpunkt"}
          <textarea autoFocus rows={2} value={e.text} onChange={(x) => setEntwurf({ ...e, text: x.target.value })} />
        </label>
        {e.art === "streitpunkt" && (
          <label className="feld">
            Einschätzung
            <select value={e.ampel} onChange={(x) => setEntwurf({ ...e, ampel: x.target.value as Ampel | "" })}>
              <option value="">keine</option>
              <option value="rot">kritisch (rot)</option>
              <option value="gelb">offen (gelb)</option>
              <option value="gruen">günstig (grün)</option>
            </select>
          </label>
        )}
        <BelegeBearbeiten belege={e.belege} dokumente={dokumente} onAendern={(belege) => setEntwurf({ ...e, belege })} />
        <div className="aktionen">
          <button type="submit">Speichern</button>
          <button
            type="button"
            className="zweitrangig"
            onClick={() => {
              setEntwurf(null);
              bearb.erledigt();
            }}
          >
            Abbrechen
          </button>
        </div>
      </form>
    );
  }

  const neu = (art: PunktArt) => setEntwurf({ id: null, art, text: "", ampel: art === "streitpunkt" ? "gelb" : "", belege: [], herkunft: "eigen" });

  return (
    <div className="af-sitzungsblatt">
      <h4>Verfahren</h4>
      <dl className="af-zeilen">
        {gericht && (
          <>
            <dt>Gericht</dt>
            <dd>
              {gericht.name}
              {gericht.aktenzeichen && ` · ${gericht.aktenzeichen}`}
            </dd>
          </>
        )}
        {akte.verfahren && !gericht && (
          <>
            <dt>Verfahren</dt>
            <dd>{akte.verfahren}</dd>
          </>
        )}
        {akte.mandanten.length > 0 && (
          <>
            <dt>Wir vertreten</dt>
            <dd>
              {akte.mandanten.join(", ")}
              {akte.eigene_rolle && ` (${akte.eigene_rolle})`}
            </dd>
          </>
        )}
        {akte.gegner.length > 0 && (
          <>
            <dt>Gegner</dt>
            <dd>{akte.gegner.join(", ")}</dd>
          </>
        )}
        {akte.gegenstandswert && (
          <>
            <dt>Wert</dt>
            <dd>{betragAnzeige(akte.gegenstandswert)} €</dd>
          </>
        )}
        {akte.gegenstand && (
          <>
            <dt>Gegenstand</dt>
            <dd>{akte.gegenstand}</dd>
          </>
        )}
      </dl>

      <h4>Anträge</h4>
      {punkte && antraege.length === 0 && entwurf?.art !== "antrag" && <p className="leise">Noch keine Anträge eingetragen.</p>}
      {punktListe(antraege)}
      {entwurf && entwurf.id == null && entwurf.art === "antrag" ? entwurfFormular() : (
        <button className="link" onClick={() => neu("antrag")} disabled={!!entwurf}>
          + Antrag
        </button>
      )}

      <h4>Streitpunkte</h4>
      {punkte && streit.length === 0 && entwurf?.art !== "streitpunkt" && <p className="leise">Noch keine Streitpunkte eingetragen.</p>}
      {punktListe(streit)}
      {entwurf && entwurf.id == null && entwurf.art === "streitpunkt" ? entwurfFormular() : (
        <span className="af-knopfzeile">
          <button className="link" onClick={() => neu("streitpunkt")} disabled={!!entwurf}>
            + Streitpunkt
          </button>
          {kiAn && (
            <button className="link" onClick={() => void vorschlaegeLaden()}>
              Vorschläge aus der Analyse
            </button>
          )}
        </span>
      )}
      {vorschlaege && (
        <div className="af-vorschlaege" role="region" aria-label="Vorschläge aus der Analyse">
          {vorschlaege.length === 0 ? (
            <p className="leise">
              Keine Vorschläge. Sie entstehen aus der Analyse „Widersprüche“ im Hauptfenster (Reiter „Analyse“) und werden erst
              nach Prüfung übernommen.
            </p>
          ) : (
            <>
              <p className="leise">Aus der Analyse „Widersprüche“. Bitte vor dem Übernehmen prüfen.</p>
              <ul className="af-punkte">
                {vorschlaege.map((w, i) => (
                  <li key={i} className="af-punkt">
                    <div className="af-punkt-text">
                      <strong>{w.thema}</strong>
                    </div>
                    <div className="leise">{w.erklaerung}</div>
                    <div className="af-belege">
                      {w.angaben.map((a, j) => (
                        <button key={j} className="link" onClick={() => onOeffnen(a.fundstelle.dokument_id, { abschnitt: a.fundstelle.abschnitt })}>
                          {a.fundstelle.dateiname}
                          {a.fundstelle.rn != null ? `, Rn. ${a.fundstelle.rn}` : a.fundstelle.seite != null ? `, S. ${a.fundstelle.seite}` : ""}
                        </button>
                      ))}
                    </div>
                    <button className="link" onClick={() => void vorschlagUebernehmen(w)}>
                      Als Streitpunkt übernehmen
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          <button className="link" onClick={() => setVorschlaege(null)}>
            Vorschläge ausblenden
          </button>
        </div>
      )}

      {angeheftet.length > 0 && (
        <>
          <h4>Angeheftete Notizen</h4>
          {angeheftet.map((n) => (
            <div key={n.id} className="af-notiz-angeheftet">
              {n.text}
              {n.dokument && <div className="leise">zu {n.dokument}</div>}
            </div>
          ))}
        </>
      )}
      {fehler && (
        <p className="fehler" role="alert">
          {fehler}
        </p>
      )}
    </div>
  );
}

/** Belege eines Punkts: Dokument und wahlweise Randnummer. */
function BelegeBearbeiten({
  belege,
  dokumente,
  onAendern,
}: {
  belege: PunktBeleg[];
  dokumente: AktenDokument[];
  onAendern: (b: PunktBeleg[]) => void;
}) {
  const [dok, setDok] = useState("");
  const [rn, setRn] = useState("");
  return (
    <div className="af-belege-bearbeiten">
      <span className="leise">Fundstellen</span>
      {belege.map((b, i) => (
        <span key={i} className="af-beleg">
          {b.bezeichnung}{" "}
          <button type="button" className="link gefahr" onClick={() => onAendern(belege.filter((_, j) => j !== i))} aria-label={`${b.bezeichnung} entfernen`}>
            ✕
          </button>
        </span>
      ))}
      <span className="af-beleg-neu">
        <select value={dok} onChange={(e) => setDok(e.target.value)} aria-label="Dokument der Fundstelle">
          <option value="">Dokument …</option>
          {dokumente.map((d) => (
            <option key={d.id} value={d.id}>
              {dokumentName(d)}
            </option>
          ))}
        </select>
        <input value={rn} onChange={(e) => setRn(e.target.value.replace(/\D/g, ""))} placeholder="Rn." aria-label="Randnummer (wahlweise)" inputMode="numeric" />
        <button
          type="button"
          className="zweitrangig"
          disabled={!dok}
          onClick={() => {
            const d = dokumente.find((x) => x.id === Number(dok));
            if (!d) return;
            const n = rn ? Number(rn) : null;
            onAendern([...belege, { dokument_id: d.id, abschnitt: null, rn: n, bezeichnung: `${dokumentName(d)}${n != null ? `, Rn. ${n}` : ""}` }]);
            setDok("");
            setRn("");
          }}
        >
          Hinzufügen
        </button>
      </span>
    </div>
  );
}

// --------------------------------------------------------------------------- Terminsnotizen

export function TerminsnotizenSpalte({
  akteId,
  sitzung,
  dokumente,
  onSitzung,
  onBeginnen,
  onOeffnen,
}: {
  akteId: number;
  sitzung: Sitzung | null;
  dokumente: AktenDokument[];
  onSitzung: (s: Sitzung) => void;
  onBeginnen: () => void;
  onOeffnen: DokumentOeffnen;
}) {
  const [text, setText] = useState("");
  const [art, setArt] = useState<TerminNotizArt>("notiz");
  const [dokument, setDokument] = useState("");
  const [bearbeitet, setBearbeitet] = useState<{ id: number; text: string } | null>(null);
  const [frueher, setFrueher] = useState<Sitzung[] | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const bearb = useBearbeitung("Terminsnotiz");
  const feld = useRef<HTMLTextAreaElement>(null);
  const liste = useRef<HTMLOListElement>(null);

  useEffect(() => {
    if (sitzung || !istDesktop) return;
    kern<Sitzung[]>("sitzung.liste", { akte_id: akteId }).then(setFrueher, () => setFrueher([]));
  }, [akteId, sitzung]);

  // Neue Notizen stehen unten; die Liste läuft mit.
  const anzahl = sitzung?.notizen.length ?? 0;
  useEffect(() => {
    const l = liste.current;
    if (l) l.lastElementChild?.scrollIntoView({ block: "nearest" });
  }, [anzahl]);

  async function aufruf(f: () => Promise<Sitzung>) {
    setFehler(null);
    try {
      onSitzung(await f());
      return true;
    } catch (e) {
      setFehler(String(e));
      return false;
    }
  }

  async function speichern(e?: FormEvent) {
    e?.preventDefault();
    if (!sitzung || !text.trim()) return;
    const ok = await aufruf(() =>
      kern("sitzung.notiz_anlegen", { sitzung_id: sitzung.id, text, art, dokument_id: dokument ? Number(dokument) : null }),
    );
    if (ok) {
      setText("");
      setArt("notiz");
      setDokument("");
      bearb.erledigt();
      feld.current?.focus();
    }
  }

  function taste(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter speichert, Umschalt+Enter macht eine neue Zeile.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void speichern();
    }
  }

  if (!sitzung) {
    return (
      <div className="af-terminsnotizen">
        <p>Es läuft kein Termin. Beginne einen Termin, um mit Uhrzeit mitzuschreiben.</p>
        <button onClick={onBeginnen}>Termin beginnen</button>
        {frueher && frueher.length > 0 && (
          <>
            <h4>Frühere Termine</h4>
            {frueher.map((s) => (
              <details key={s.id} className="af-frueher">
                <summary>
                  {datumDe(s.beginn.slice(0, 10))}, {uhrzeitVon(s.beginn)}
                  {s.ende && `–${uhrzeitVon(s.ende)}`} Uhr · {s.titel} ({s.notizen.length} Notizen)
                </summary>
                <ol className="af-tn-liste">
                  {s.notizen.map((n) => (
                    <li key={n.id}>
                      <time>{uhrzeitVon(n.zeit)}</time>
                      <div>
                        {n.art !== "notiz" && <strong>{n.art_text}: </strong>}
                        {n.text}
                      </div>
                    </li>
                  ))}
                </ol>
              </details>
            ))}
          </>
        )}
      </div>
    );
  }

  return (
    <div className="af-terminsnotizen">
      <form onSubmit={speichern} {...bearb.formular}>
        <div className="af-tn-arten" role="radiogroup" aria-label="Art der Notiz">
          {TERMIN_NOTIZ_ARTEN.map((a) => (
            <button
              key={a.art}
              type="button"
              role="radio"
              aria-checked={art === a.art}
              className={`af-chip${art === a.art ? " aktiv" : ""}`}
              onClick={() => {
                setArt(a.art);
                feld.current?.focus();
              }}
            >
              {a.titel}
            </button>
          ))}
        </div>
        <label className="unsichtbar" htmlFor="af-tn-text">
          Terminsnotiz
        </label>
        <textarea
          id="af-tn-text"
          ref={feld}
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={taste}
          placeholder={`${TERMIN_NOTIZ_ARTEN.find((a) => a.art === art)!.titel} … Enter speichert mit Uhrzeit, Umschalt+Enter: neue Zeile`}
        />
        <div className="af-tn-zeile">
          <select value={dokument} onChange={(e) => setDokument(e.target.value)} aria-label="Bezug zu einem Dokument (wahlweise)">
            <option value="">ohne Bezug zu einem Dokument</option>
            {dokumente.map((d) => (
              <option key={d.id} value={d.id}>
                zu {dokumentName(d)}
              </option>
            ))}
          </select>
          <button type="submit" disabled={!text.trim()}>
            Speichern
          </button>
        </div>
      </form>
      {fehler && (
        <p className="fehler" role="alert">
          {fehler}
        </p>
      )}
      <ol className="af-tn-liste" ref={liste} aria-label="Notizen dieses Termins">
        {sitzung.notizen.map((n) => (
          <li key={n.id}>
            <time dateTime={n.zeit}>{uhrzeitVon(n.zeit)}</time>
            {bearbeitet?.id === n.id ? (
              <form
                className="af-tn-bearbeiten"
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (await aufruf(() => kern("sitzung.notiz_aendern", { notiz_id: n.id, text: bearbeitet.text }))) setBearbeitet(null);
                }}
              >
                <textarea autoFocus rows={2} value={bearbeitet.text} onChange={(e) => setBearbeitet({ id: n.id, text: e.target.value })} aria-label="Notiz bearbeiten" />
                <button type="submit">Speichern</button>{" "}
                <button type="button" className="zweitrangig" onClick={() => setBearbeitet(null)}>
                  Abbrechen
                </button>
              </form>
            ) : (
              <div>
                {n.art !== "notiz" && <strong>{n.art_text}: </strong>}
                {n.text}
                {n.dokument_id != null && (
                  <>
                    {" "}
                    <button className="link" onClick={() => onOeffnen(n.dokument_id!)}>
                      ↳ {n.dokument}
                    </button>
                  </>
                )}
                <span className="af-tn-aktionen">
                  <button className="link" onClick={() => setBearbeitet({ id: n.id, text: n.text })}>
                    Bearbeiten
                  </button>
                  <button className="link gefahr" onClick={() => void aufruf(() => kern("sitzung.notiz_loeschen", { notiz_id: n.id }))}>
                    Löschen
                  </button>
                </span>
              </div>
            )}
          </li>
        ))}
      </ol>
      {sitzung.notizen.length === 0 && <p className="leise">Noch keine Notizen in diesem Termin.</p>}
    </div>
  );
}
