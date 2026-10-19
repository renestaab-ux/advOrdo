import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  AMPEL_TEXT,
  AkteStammdaten as Stammdaten,
  AktenOptionen,
  Beteiligter,
  Beteiligung,
  Kollisionspruefung,
  kern,
} from "./kern";

/** Felder der Akte, die im Formular bearbeitet werden. */
const AKTE_FELDER = ["name", "gegenstand", "sachgebiet", "eigene_rolle", "status", "sachbearbeiter_id", "mandat_seit",
  "gegenstandswert", "notiz"] as const;

type Entwurf = Record<(typeof AKTE_FELDER)[number], string>;

function entwurfAus(s: Stammdaten): Entwurf {
  const e = {} as Entwurf;
  for (const k of AKTE_FELDER) e[k] = s[k] == null ? "" : String(s[k]);
  return e;
}

/**
 * Stammdaten einer Akte: Aktenzeichen, Gegenstand, Status, die Beteiligten mit ihrer Rolle und die
 * Kollisionsprüfung. Beteiligte kommen aus dem Beteiligtenverzeichnis und werden dort nur einmal angelegt.
 */
export default function AkteStammdaten({ akteId, onGeaendert }: { akteId: number; onGeaendert: () => void }) {
  const [daten, setDaten] = useState<Stammdaten | null>(null);
  const [optionen, setOptionen] = useState<AktenOptionen | null>(null);
  const [entwurf, setEntwurf] = useState<Entwurf | null>(null);
  const [vorschlag, setVorschlag] = useState("");
  const [azEingabe, setAzEingabe] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);

  const ausfuehren = useCallback(async <T,>(f: () => Promise<T>) => {
    setLaeuft(true);
    setFehler(null);
    setMeldung(null);
    try {
      return await f();
    } catch (e) {
      setFehler(String(e));
      return undefined;
    } finally {
      setLaeuft(false);
    }
  }, []);

  const uebernehmen = useCallback((s: Stammdaten) => {
    setDaten(s);
    setEntwurf(entwurfAus(s));
  }, []);

  useEffect(() => {
    void ausfuehren(async () => {
      setOptionen(await kern<AktenOptionen>("akten.optionen"));
      const s = await kern<Stammdaten>("akten.stammdaten", { akte_id: akteId });
      uebernehmen(s);
      if (!s.aktenzeichen) setVorschlag((await kern<{ aktenzeichen: string }>("akten.aktenzeichen_vorschlag")).aktenzeichen);
    });
  }, [akteId, ausfuehren, uebernehmen]);

  async function geaendert(s: Stammdaten | undefined, text?: string) {
    if (!s) return;
    uebernehmen(s);
    if (text) setMeldung(text);
    onGeaendert();
  }

  async function speichern(e: FormEvent) {
    e.preventDefault();
    if (!entwurf) return;
    const werte: Record<string, unknown> = { ...entwurf };
    werte.sachbearbeiter_id = entwurf.sachbearbeiter_id ? Number(entwurf.sachbearbeiter_id) : null;
    await geaendert(
      await ausfuehren(() => kern<Stammdaten>("akten.stammdaten_speichern", { akte_id: akteId, daten: werte })),
      "Gespeichert.",
    );
  }

  async function vergeben() {
    await geaendert(
      await ausfuehren(() =>
        kern<Stammdaten>("akten.aktenzeichen_vergeben", { akte_id: akteId, aktenzeichen: azEingabe.trim() || null }),
      ),
    );
  }

  if (!daten || !entwurf || !optionen) {
    return <section className="karte stammdaten">{fehler ? <p className="fehler">{fehler}</p> : <p className="status">Lade Stammdaten …</p>}</section>;
  }
  const feld = (k: keyof Entwurf) => ({
    value: entwurf[k],
    onChange: (ev: { target: { value: string } }) => setEntwurf({ ...entwurf, [k]: ev.target.value }),
  });

  return (
    <section className="karte stammdaten">
      <div className="kopf">
        <h2>Stammdaten und Beteiligte</h2>
        <span className="leise">{daten.dokumente} Dokumente</span>
      </div>

      <div className="az-zeile">
        <strong>Aktenzeichen:</strong>
        {daten.aktenzeichen ? (
          <span className="az">{daten.aktenzeichen}</span>
        ) : (
          <>
            <span className="hinweis">fehlt</span>
            <input
              value={azEingabe}
              onChange={(e) => setAzEingabe(e.target.value)}
              placeholder={vorschlag ? `Vorschlag: ${vorschlag}` : "Nummer/Jahr"}
              aria-label="Aktenzeichen"
              size={14}
            />
            <button className="zweitrangig" onClick={vergeben} disabled={laeuft}>
              {azEingabe.trim() ? "Vergeben" : `${vorschlag || "Nächstes"} vergeben`}
            </button>
            <span className="leise">Ein vergebenes Aktenzeichen bleibt vergeben, auch wenn die Akte gelöscht wird.</span>
          </>
        )}
      </div>

      <form onSubmit={speichern}>
        <div className="formular-raster">
          <label className="feld">
            Kurzbezeichnung
            <input {...feld("name")} placeholder="z. B. Brückner ./. Autohaus Rehnfeld" />
          </label>
          <label className="feld">
            Gegenstand
            <input {...feld("gegenstand")} placeholder="z. B. Rückabwicklung Gebrauchtwagenkauf" />
          </label>
          <label className="feld">
            Sachgebiet
            <select {...feld("sachgebiet")}>
              <option value="">–</option>
              {optionen.sachgebiete.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="feld">
            Eigene Rolle
            <select {...feld("eigene_rolle")}>
              <option value="">–</option>
              {optionen.eigene_rollen.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="feld">
            Status
            <select {...feld("status")}>
              {Object.entries(optionen.status).map(([k, t]) => (
                <option key={k} value={k}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="feld">
            Sachbearbeiter
            <select {...feld("sachbearbeiter_id")}>
              <option value="">–</option>
              {optionen.sachbearbeiter.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            {optionen.sachbearbeiter.length === 0 && (
              <span className="feld-hinweis">Berufsträger werden unter „Eigene Daten“ erfasst.</span>
            )}
          </label>
          <label className="feld">
            Mandat seit
            <input type="date" {...feld("mandat_seit")} />
          </label>
          <label className="feld">
            Gegenstandswert
            <input {...feld("gegenstandswert")} placeholder="z. B. 18.450,00 €" />
          </label>
          <label className="feld feld-breit">
            Notiz
            <textarea rows={2} {...feld("notiz")} />
          </label>
        </div>
        <div className="aktionen">
          <button type="submit" disabled={laeuft}>
            Speichern
          </button>
        </div>
      </form>

      <BeteiligteDerAkte
        akteId={akteId}
        daten={daten}
        optionen={optionen}
        laeuft={laeuft}
        ausfuehren={ausfuehren}
        onGeaendert={(s) => void geaendert(s)}
      />

      <KollisionsAnzeige
        akteId={akteId}
        pruefung={daten.kollision}
        optionen={optionen}
        laeuft={laeuft}
        ausfuehren={ausfuehren}
        onGeaendert={(k) => uebernehmen({ ...daten, kollision: k })}
      />

      {laeuft && <p className="status">Einen Moment …</p>}
      {meldung && !laeuft && <p className="meldung">{meldung}</p>}
      {fehler && <p className="fehler">{fehler}</p>}
    </section>
  );
}

type Ausfuehren = <T>(f: () => Promise<T>) => Promise<T | undefined>;

const SEITEN_REIHE = ["eigene", "gegen", "neutral"] as const;

function BeteiligteDerAkte({
  akteId,
  daten,
  optionen,
  laeuft,
  ausfuehren,
  onGeaendert,
}: {
  akteId: number;
  daten: Stammdaten;
  optionen: AktenOptionen;
  laeuft: boolean;
  ausfuehren: Ausfuehren;
  onGeaendert: (s: Stammdaten | undefined) => void;
}) {
  const [rolle, setRolle] = useState("mandant");
  const [suche, setSuche] = useState("");
  const [treffer, setTreffer] = useState<Beteiligter[]>([]);
  const [azZusatz, setAzZusatz] = useState("");
  const [formular, setFormular] = useState<{ art: "person" | "organisation"; eintrag?: Beteiligter } | null>(null);

  const eigeneWahl =
    (rolle === "mandant" && optionen.form === "rechtsabteilung" && optionen.konzerngesellschaften.length > 0) ||
    rolle === "vertretender_anwalt";

  useEffect(() => {
    if (eigeneWahl) return;
    let aktuell = true;
    const t = setTimeout(() => {
      void kern<Beteiligter[]>("beteiligte.liste", { suche }).then((l) => {
        // Wer schon in der Akte steht, wird nicht noch einmal angeboten.
        const schon = new Set(daten.beteiligte.map((b) => b.beteiligter_id));
        if (aktuell) setTreffer(l.filter((t) => !schon.has(t.id)).slice(0, 8));
      });
    }, 200);
    return () => {
      aktuell = false;
      clearTimeout(t);
    };
  }, [suche, eigeneWahl, daten]);

  async function hinzufuegen(verweis: Record<string, number>) {
    const s = await ausfuehren(() =>
      kern<Stammdaten>("akten.beteiligung_hinzufuegen", { akte_id: akteId, rolle, aktenzeichen: azZusatz, ...verweis }),
    );
    if (s) {
      setSuche("");
      setAzZusatz("");
    }
    onGeaendert(s);
  }

  async function entfernen(b: Beteiligung) {
    onGeaendert(await ausfuehren(() => kern<Stammdaten>("akten.beteiligung_entfernen", { beteiligung_id: b.id })));
  }

  async function eintragOeffnen(id: number) {
    const e = await ausfuehren(() => kern<Beteiligter>("beteiligte.eintrag", { beteiligter_id: id }));
    if (e) setFormular({ art: e.art, eintrag: e });
  }

  return (
    <div className="beteiligte-akte">
      <h3>Beteiligte</h3>
      {daten.beteiligte.length === 0 && <p className="leer">Noch keine Beteiligten. Beginne mit Mandant und Gegner.</p>}
      {SEITEN_REIHE.map((seite) => {
        const liste = daten.beteiligte.filter((b) => b.seite === seite);
        if (liste.length === 0) return null;
        return (
          <div key={seite} className={`seite seite-${seite}`}>
            <div className="leise">{optionen.seiten[seite]}</div>
            <ul className="eintraege">
              {liste.map((b) => (
                <li key={b.id}>
                  <span>
                    {b.beteiligter_id != null ? (
                      <button className="link" onClick={() => void eintragOeffnen(b.beteiligter_id!)}>
                        {b.name}
                      </button>
                    ) : (
                      <strong>{b.name}</strong>
                    )}{" "}
                    <span className="leise">
                      {b.rolle_text}
                      {b.aktenzeichen && ` · Az. ${b.aktenzeichen}`}
                      {b.quelle !== "verzeichnis" && " · aus Eigene Daten"}
                    </span>
                  </span>
                  <button className="link gefahr" onClick={() => void entfernen(b)} disabled={laeuft}>
                    Entfernen
                  </button>
                </li>
              ))}
            </ul>
          </div>
        );
      })}

      <div className="eintrag-formular">
        <div className="beteiligte-neu">
          <label className="feld">
            Rolle
            <select value={rolle} onChange={(e) => setRolle(e.target.value)}>
              {Object.entries(optionen.rollen).map(([k, r]) => (
                <option key={k} value={k}>
                  {r.text}
                </option>
              ))}
            </select>
          </label>
          {(rolle === "gericht" || rolle === "bevollmaechtigter_gegner" || rolle === "versicherer_gegner") && (
            <label className="feld">
              {rolle === "gericht" ? "Gerichtliches Aktenzeichen" : "Deren Aktenzeichen"}
              <input value={azZusatz} onChange={(e) => setAzZusatz(e.target.value)} placeholder="z. B. 3 O 412/25" />
            </label>
          )}
          {!eigeneWahl && (
            <label className="feld feld-breit">
              Im Beteiligtenverzeichnis suchen
              <input value={suche} onChange={(e) => setSuche(e.target.value)} placeholder="Name, auch früherer Name" />
            </label>
          )}
        </div>
        {eigeneWahl && rolle === "mandant" && (
          <ul className="eintraege">
            {optionen.konzerngesellschaften.map((o) => (
              <li key={o.id}>
                <span>
                  {o.name} <span className="leise">Konzerngesellschaft</span>
                </span>
                <button className="zweitrangig" onClick={() => void hinzufuegen({ eigene_organisation_id: o.id })} disabled={laeuft}>
                  Als Mandant eintragen
                </button>
              </li>
            ))}
          </ul>
        )}
        {eigeneWahl && rolle === "vertretender_anwalt" && (
          <ul className="eintraege">
            {optionen.anwaelte.length === 0 && (
              <li className="leer">Beauftragte Kanzleien und ihre Anwälte werden unter „Eigene Daten“ erfasst.</li>
            )}
            {optionen.anwaelte.map((p) => (
              <li key={p.id}>
                <span>
                  {p.name} <span className="leise">{p.kanzlei}</span>
                </span>
                <button className="zweitrangig" onClick={() => void hinzufuegen({ eigene_person_id: p.id })} disabled={laeuft}>
                  Eintragen
                </button>
              </li>
            ))}
          </ul>
        )}
        {!eigeneWahl && (
          <>
            <ul className="eintraege">
              {treffer.map((t) => (
                <li key={t.id}>
                  <span>
                    {t.name} <span className="leise">{t.art === "person" ? "Person" : (t.daten.kategorie as string) || "Organisation"}</span>
                  </span>
                  <button className="zweitrangig" onClick={() => void hinzufuegen({ beteiligter_id: t.id })} disabled={laeuft}>
                    Als {optionen.rollen[rolle].text} eintragen
                  </button>
                </li>
              ))}
              {treffer.length === 0 && suche.trim() && <li className="leer">Kein Eintrag gefunden.</li>}
            </ul>
            <div className="aktionen">
              <button className="zweitrangig" onClick={() => setFormular({ art: "person" })}>
                Neue Person …
              </button>
              <button className="zweitrangig" onClick={() => setFormular({ art: "organisation" })}>
                Neue Organisation …
              </button>
            </div>
          </>
        )}
      </div>

      {formular && (
        <BeteiligterFormular
          art={formular.art}
          eintrag={formular.eintrag}
          vorbelegung={suche}
          kategorien={optionen.kategorien}
          beziehungen={optionen.beziehungen}
          ausfuehren={ausfuehren}
          onFertig={(neu, uebernehmen) => {
            setFormular(null);
            if (neu && uebernehmen) void hinzufuegen({ beteiligter_id: neu.id });
            else void ausfuehren(() => kern<Stammdaten>("akten.stammdaten", { akte_id: akteId })).then(onGeaendert);
          }}
          rolleText={optionen.rollen[rolle].text}
        />
      )}
    </div>
  );
}

const FELDER_PERSON: [string, string][] = [
  ["anrede", "Anrede"], ["titel", "Titel"], ["vorname", "Vorname"], ["nachname", "Nachname"],
  ["geburtsdatum", "Geburtsdatum"],
];
const FELDER_ORG: [string, string][] = [
  ["name", "Name / Firma"], ["rechtsform", "Rechtsform"], ["registergericht", "Registergericht"],
  ["registernummer", "Registernummer"],
];
const FELDER_GEMEINSAM: [string, string][] = [
  ["strasse", "Straße und Hausnummer"], ["plz", "PLZ"], ["ort", "Ort"], ["land", "Land"], ["telefon", "Telefon"],
  ["email", "E-Mail"], ["safe_id", "beA-/SAFE-ID"],
];

/** Neuer oder bestehender Eintrag im Beteiligtenverzeichnis, mit Hinweis auf mögliche Dubletten. */
function BeteiligterFormular({
  art,
  eintrag,
  vorbelegung,
  kategorien,
  beziehungen,
  ausfuehren,
  onFertig,
  rolleText,
}: {
  art: "person" | "organisation";
  eintrag?: Beteiligter;
  vorbelegung: string;
  kategorien: string[];
  beziehungen: Record<string, string>;
  ausfuehren: Ausfuehren;
  onFertig: (neu: Beteiligter | null, uebernehmen: boolean) => void;
  rolleText: string;
}) {
  const start: Record<string, string> = {};
  if (eintrag) {
    for (const [k, v] of Object.entries(eintrag.daten)) start[k] = Array.isArray(v) ? v.join("\n") : v;
  } else if (vorbelegung.trim()) {
    start[art === "person" ? "nachname" : "name"] = vorbelegung.trim();
  }
  const [werte, setWerte] = useState<Record<string, string>>(start);
  const [dubletten, setDubletten] = useState<Beteiligter[]>([]);
  const [bezSuche, setBezSuche] = useState("");
  const [bezTreffer, setBezTreffer] = useState<Beteiligter[]>([]);
  const [aktuell, setAktuell] = useState<Beteiligter | undefined>(eintrag);
  const felder = art === "person" ? FELDER_PERSON : FELDER_ORG;

  async function pruefeDubletten() {
    const name = art === "person" ? werte.nachname : werte.name;
    if (!name?.trim()) return setDubletten([]);
    const l = await kern<Beteiligter[]>("beteiligte.aehnliche", { art, daten: werte, ausser: aktuell?.id ?? null });
    setDubletten(l);
  }

  useEffect(() => {
    if (!aktuell || !bezSuche.trim()) return setBezTreffer([]);
    const t = setTimeout(() => {
      void kern<Beteiligter[]>("beteiligte.liste", { suche: bezSuche }).then((l) =>
        setBezTreffer(l.filter((b) => b.id !== aktuell.id).slice(0, 6)),
      );
    }, 200);
    return () => clearTimeout(t);
  }, [bezSuche, aktuell]);

  async function speichern(e: FormEvent, uebernehmen: boolean) {
    e.preventDefault();
    const daten = { ...werte, fruehere_namen: (werte.fruehere_namen ?? "").split("\n") };
    const neu = await ausfuehren(() =>
      kern<Beteiligter>("beteiligte.speichern", { art, daten, beteiligter_id: aktuell?.id ?? null }),
    );
    if (neu) onFertig(neu, uebernehmen && !aktuell);
  }

  async function beziehung(anderer: Beteiligter, bezArt: string, vorhanden = true) {
    if (!aktuell) return;
    // Gesetzlicher Vertreter: die Person vertritt die Organisation.
    const [von, zu] = bezArt === "gesetzlicher_vertreter" && aktuell.art === "organisation" ? [anderer.id, aktuell.id] : [aktuell.id, anderer.id];
    const neu = await ausfuehren(() => kern<Beteiligter>("beteiligte.beziehung_setzen", { von, zu, art: bezArt, vorhanden }));
    if (neu) {
      setAktuell(await kern<Beteiligter>("beteiligte.eintrag", { beteiligter_id: aktuell.id }));
      setBezSuche("");
    }
  }

  const feld = (k: string, titel: string, breit = false) => (
    <label key={k} className={breit ? "feld feld-breit" : "feld"}>
      {titel}
      <input
        type={k === "geburtsdatum" ? "date" : "text"}
        value={werte[k] ?? ""}
        onChange={(ev) => setWerte({ ...werte, [k]: ev.target.value })}
        onBlur={k === "name" || k === "nachname" || k === "vorname" ? () => void pruefeDubletten() : undefined}
      />
    </label>
  );

  return (
    <div className="eintrag-formular beteiligter-formular" role="dialog" aria-label="Beteiligter">
      <h3>{aktuell ? aktuell.name : art === "person" ? "Neue Person" : "Neue Organisation"}</h3>
      <form onSubmit={(e) => void speichern(e, true)}>
        <div className="formular-raster">
          {felder.map(([k, t]) => feld(k, t))}
          {art === "organisation" && (
            <label className="feld">
              Kategorie
              <select value={werte.kategorie ?? ""} onChange={(ev) => setWerte({ ...werte, kategorie: ev.target.value })}>
                <option value="">–</option>
                {kategorien.map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            </label>
          )}
          {FELDER_GEMEINSAM.map(([k, t]) => feld(k, t))}
          <label className="feld feld-breit">
            Frühere Namen (einer je Zeile)
            <textarea rows={2} value={werte.fruehere_namen ?? ""} onChange={(ev) => setWerte({ ...werte, fruehere_namen: ev.target.value })} />
            <span className="feld-hinweis">Alte Firma, Geburtsname: Die Kollisionsprüfung findet auch diese.</span>
          </label>
          <label className="feld feld-breit">
            Notiz
            <textarea rows={2} value={werte.notiz ?? ""} onChange={(ev) => setWerte({ ...werte, notiz: ev.target.value })} />
          </label>
        </div>
        {dubletten.length > 0 && (
          <div className="hinweis-box">
            <strong>Diesen Namen gibt es schon:</strong>
            <ul className="eintraege">
              {dubletten.map((d) => (
                <li key={d.id}>
                  <span>
                    {d.name} <span className="leise">{d.stufe === "gleich" ? "gleicher Name" : "ähnlicher Name"}</span>
                  </span>
                  {!aktuell && (
                    <button type="button" className="zweitrangig" onClick={() => onFertig(d, true)}>
                      Vorhandenen nehmen
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="aktionen">
          <button type="submit">{aktuell ? "Speichern" : `Anlegen und als ${rolleText} eintragen`}</button>
          {!aktuell && (
            <button type="button" className="zweitrangig" onClick={(e) => void speichern(e as unknown as FormEvent, false)}>
              Nur anlegen
            </button>
          )}
          <button type="button" className="zweitrangig" onClick={() => onFertig(null, false)}>
            {aktuell ? "Schließen" : "Abbrechen"}
          </button>
        </div>
      </form>

      {aktuell && (
        <div className="beziehungen">
          <h3>Beziehungen</h3>
          <ul className="eintraege">
            {(aktuell.beziehungen ?? []).map((b) => (
              <li key={`${b.von}-${b.zu}-${b.art}`}>
                <span>{b.text}</span>
                <button
                  className="link gefahr"
                  onClick={() => void ausfuehren(() => kern<Beteiligter>("beteiligte.beziehung_setzen", { von: b.von, zu: b.zu, art: b.art, vorhanden: false })).then(async () => setAktuell(await kern<Beteiligter>("beteiligte.eintrag", { beteiligter_id: aktuell.id })))}
                >
                  Entfernen
                </button>
              </li>
            ))}
            {(aktuell.beziehungen ?? []).length === 0 && <li className="leer">Keine.</li>}
          </ul>
          <label className="feld">
            {aktuell.art === "organisation" ? "Gesetzlichen Vertreter oder verbundene Organisation suchen" : "Organisation suchen, die diese Person vertritt"}
            <input value={bezSuche} onChange={(e) => setBezSuche(e.target.value)} placeholder="Name im Beteiligtenverzeichnis" />
          </label>
          <ul className="eintraege">
            {bezTreffer.map((t) => (
              <li key={t.id}>
                <span>{t.name}</span>
                <span className="aktionen">
                  {(aktuell.art === "organisation" ? t.art === "person" : t.art === "organisation") && (
                    <button className="zweitrangig" onClick={() => void beziehung(t, "gesetzlicher_vertreter")}>
                      {beziehungen.gesetzlicher_vertreter}
                    </button>
                  )}
                  {aktuell.art === "organisation" && t.art === "organisation" && (
                    <button className="zweitrangig" onClick={() => void beziehung(t, "verbunden")}>
                      {beziehungen.verbunden}
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
          {(aktuell.akten ?? []).length > 0 && (
            <p className="leise">
              Beteiligt an: {(aktuell.akten ?? []).map((a) => `${a.aktenzeichen ?? a.akte}`).join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Ergebnis der Kollisionsprüfung mit Ampel, Treffern und der dokumentierten Entscheidung. */
function KollisionsAnzeige({
  akteId,
  pruefung,
  optionen,
  laeuft,
  ausfuehren,
  onGeaendert,
}: {
  akteId: number;
  pruefung: Kollisionspruefung | null;
  optionen: AktenOptionen;
  laeuft: boolean;
  ausfuehren: Ausfuehren;
  onGeaendert: (k: Kollisionspruefung) => void;
}) {
  const [begruendung, setBegruendung] = useState("");

  async function pruefen() {
    const k = await ausfuehren(() => kern<Kollisionspruefung>("akten.kollision_pruefen", { akte_id: akteId }));
    if (k) onGeaendert(k);
  }

  async function entscheiden(entscheidung: string) {
    if (!pruefung) return;
    const k = await ausfuehren(() =>
      kern<Kollisionspruefung>("akten.kollision_entscheiden", { pruefung_id: pruefung.id, entscheidung, begruendung }),
    );
    if (k) {
      onGeaendert(k);
      setBegruendung("");
    }
  }

  return (
    <div className="kollision">
      <div className="kopf">
        <h3>Kollisionsprüfung</h3>
        <button className="zweitrangig" onClick={() => void pruefen()} disabled={laeuft}>
          {pruefung ? "Erneut prüfen" : "Jetzt prüfen"}
        </button>
      </div>
      {!pruefung && <p className="leer">Noch nicht geprüft. JuraBox prüft automatisch, sobald Mandant oder Gegner eingetragen werden.</p>}
      {pruefung && (
        <>
          <p className={`ampel ampel-${pruefung.ampel}`}>
            <span className="ampel-punkt" aria-hidden="true" /> {AMPEL_TEXT[pruefung.ampel]}
          </p>
          {pruefung.treffer.length > 0 && (
            <ul className="treffer">
              {pruefung.treffer.map((t, i) => (
                <li key={i} className={`ampel-${t.ampel}`}>
                  {t.text}
                </li>
              ))}
            </ul>
          )}
          <p className="leise">
            Geprüft am {new Date(pruefung.zeitpunkt).toLocaleString("de-DE")} in: {pruefung.umgebungen.join(", ")}.
            Andere Umgebungen werden nur gelesen; ausnehmen lassen sie sich unter „Einstellungen“.
          </p>
          {pruefung.entscheidung ? (
            <p>
              <strong>Entscheidung:</strong> {pruefung.entscheidung_text}
              {pruefung.begruendung && ` – ${pruefung.begruendung}`}{" "}
              <span className="leise">({new Date(pruefung.entschieden_am!).toLocaleString("de-DE")})</span>
            </p>
          ) : (
            pruefung.ampel !== "gruen" && (
              <div className="entscheidung">
                <label className="feld">
                  Begründung
                  <textarea rows={2} value={begruendung} onChange={(e) => setBegruendung(e.target.value)}
                    placeholder="z. B. andere Rechtssache, früheres Mandat beendet" />
                </label>
                <div className="aktionen">
                  <button className="zweitrangig" onClick={() => void entscheiden("kein_konflikt")} disabled={laeuft}>
                    {optionen.entscheidungen.kein_konflikt}
                  </button>
                  <button className="zweitrangig gefahr" onClick={() => void entscheiden("konflikt")} disabled={laeuft}>
                    {optionen.entscheidungen.konflikt}
                  </button>
                </div>
              </div>
            )
          )}
          <p className="leise">
            Ob ein Interessenkonflikt vorliegt (§ 43a Abs. 4 BRAO, § 3 BORA), entscheidest du; JuraBox legt nur die
            Treffer vor und hält Prüfung und Entscheidung fest.
          </p>
        </>
      )}
    </div>
  );
}
