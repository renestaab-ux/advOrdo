import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  AMPEL_TEXT,
  AkteStammdaten as Stammdaten,
  AktenOptionen,
  Beteiligter,
  Beteiligung,
  KollisionVorab,
  Kollisionspruefung,
  betragAnzeige,
  betragNormalisieren,
  kern,
} from "./kern";

/** Felder der Akte, die im Formular bearbeitet werden. */
const AKTE_FELDER = ["name", "gegenstand", "sachgebiet", "eigene_rolle", "status", "sachbearbeiter_id", "mandat_seit",
  "gegenstandswert", "notiz"] as const;

type Entwurf = Record<(typeof AKTE_FELDER)[number], string>;

function entwurfAus(s: Stammdaten): Entwurf {
  const e = {} as Entwurf;
  for (const k of AKTE_FELDER) e[k] = s[k] == null ? "" : String(s[k]);
  e.gegenstandswert = betragAnzeige(e.gegenstandswert);
  return e;
}

function entwurfWerte(entwurf: Entwurf): Record<string, unknown> {
  return { ...entwurf, sachbearbeiter_id: entwurf.sachbearbeiter_id ? Number(entwurf.sachbearbeiter_id) : null };
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

  /** Neue Daten aus dem Kern; ungespeicherte Eingaben im Formular bleiben dabei stehen. */
  function geaendert(s: Stammdaten | undefined) {
    if (!s) return;
    setDaten(s);
    onGeaendert();
  }

  const ungespeichert = !!(daten && entwurf) && JSON.stringify(entwurf) !== JSON.stringify(entwurfAus(daten));

  /** Speichert die Stammdaten, falls im Formular etwas geändert wurde; false, wenn das Speichern scheitert. */
  async function sichern(text?: string): Promise<boolean> {
    if (!entwurf || (!ungespeichert && !text)) return true;
    const s = await ausfuehren(() =>
      kern<Stammdaten>("akten.stammdaten_speichern", { akte_id: akteId, daten: entwurfWerte(entwurf) }),
    );
    if (!s) return false;
    uebernehmen(s);
    if (text) setMeldung(text);
    onGeaendert();
    return true;
  }

  async function speichern(e: FormEvent) {
    e.preventDefault();
    await sichern("Gespeichert.");
  }

  async function vergeben() {
    geaendert(
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
            Gegenstandswert in €
            <input
              {...feld("gegenstandswert")}
              inputMode="decimal"
              className="betrag"
              placeholder="z. B. 18.450,00"
              onBlur={() => setEntwurf({ ...entwurf, gegenstandswert: betragNormalisieren(entwurf.gegenstandswert) })}
            />
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
          {ungespeichert && <span className="leise">Ungespeicherte Änderungen; sie werden beim Eintragen eines Beteiligten mitgespeichert.</span>}
        </div>
      </form>

      <BeteiligteDerAkte
        akteId={akteId}
        daten={daten}
        optionen={optionen}
        laeuft={laeuft}
        ausfuehren={ausfuehren}
        vorher={() => sichern()}
        onGeaendert={geaendert}
      />

      <KollisionsAnzeige
        akteId={akteId}
        pruefung={daten.kollision}
        optionen={optionen}
        laeuft={laeuft}
        ausfuehren={ausfuehren}
        onGeaendert={(k) => setDaten({ ...daten, kollision: k })}
      />

      {laeuft && <p className="status">Einen Moment …</p>}
      {meldung && !laeuft && <p className="meldung">{meldung}</p>}
      {fehler && <p className="fehler">{fehler}</p>}
    </section>
  );
}

type Ausfuehren = <T>(f: () => Promise<T>) => Promise<T | undefined>;

const GRUPPEN_REIHE = ["eigene", "gegen", "gericht", "neutral"] as const;
const PARTEIROLLEN = ["mandant", "gegner"];

const gleicherName = (a: string, b: string) => a.trim().toLocaleLowerCase("de") === b.trim().toLocaleLowerCase("de");

function BeteiligteDerAkte({
  akteId,
  daten,
  optionen,
  laeuft,
  ausfuehren,
  vorher,
  onGeaendert,
}: {
  akteId: number;
  daten: Stammdaten;
  optionen: AktenOptionen;
  laeuft: boolean;
  ausfuehren: Ausfuehren;
  /** Läuft vor jeder Änderung an den Beteiligten: speichert offene Stammdaten. */
  vorher: () => Promise<boolean>;
  onGeaendert: (s: Stammdaten | undefined) => void;
}) {
  const [rolle, setRolle] = useState("mandant");
  const [suche, setSuche] = useState("");
  const [treffer, setTreffer] = useState<Beteiligter[]>([]);
  const [azZusatz, setAzZusatz] = useState("");
  const [vorab, setVorab] = useState<KollisionVorab>({});
  // nr: jedes Öffnen ist ein neues Formular, auch wenn eines offen war.
  const [formular, setFormular] = useState<{ art: "person" | "organisation"; eintrag?: Beteiligter; nr: number } | null>(null);
  const oeffnen = (art: "person" | "organisation", eintrag?: Beteiligter) => setFormular({ art, eintrag, nr: Date.now() });

  const eigeneWahl =
    (rolle === "mandant" && optionen.form === "rechtsabteilung" && optionen.konzerngesellschaften.length > 0) ||
    rolle === "vertretender_anwalt";

  useEffect(() => {
    if (eigeneWahl || !suche.trim()) {
      setTreffer([]);
      return;
    }
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

  // Möglichen Konflikt schon an den Suchtreffern zeigen, bevor jemand Mandant oder Gegner wird.
  useEffect(() => {
    if (!PARTEIROLLEN.includes(rolle) || treffer.length === 0) {
      setVorab({});
      return;
    }
    let aktuell = true;
    void kern<KollisionVorab>("akten.kollision_vorab", { akte_id: akteId, rolle, beteiligter_ids: treffer.map((t) => t.id) })
      .then((v) => aktuell && setVorab(v))
      .catch(() => aktuell && setVorab({}));
    return () => {
      aktuell = false;
    };
  }, [treffer, rolle, akteId]);

  async function hinzufuegen(verweis: Record<string, number>) {
    if (!(await vorher())) return;
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
    if (!(await vorher())) return;
    onGeaendert(await ausfuehren(() => kern<Stammdaten>("akten.beteiligung_entfernen", { beteiligung_id: b.id })));
  }

  async function eintragOeffnen(id: number) {
    const e = await ausfuehren(() => kern<Beteiligter>("beteiligte.eintrag", { beteiligter_id: id }));
    if (e) oeffnen(e.art, e);
  }

  return (
    <div className="beteiligte-akte">
      <h3>Beteiligte</h3>
      {daten.beteiligte.length === 0 && <p className="leer">Noch keine Beteiligten. Beginne mit Mandant und Gegner.</p>}
      {GRUPPEN_REIHE.map((gruppe) => {
        const liste = daten.beteiligte.filter((b) => (b.gruppe ?? b.seite) === gruppe);
        if (liste.length === 0) return null;
        return (
          <div key={gruppe} className={`seite seite-${gruppe}`}>
            <div className="leise">{optionen.gruppen?.[gruppe] ?? optionen.seiten[gruppe]}</div>
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

      <div className="eintrag-formular beteiligte-hinzufuegen">
        <h4>Beteiligten hinzufügen</h4>
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
              {treffer.map((t) => {
                const k = vorab[String(t.id)];
                const namensgleich = daten.beteiligte.find((b) => gleicherName(b.name, t.name));
                return (
                  <li key={t.id} className={k ? `vorab vorab-${k.ampel}` : undefined}>
                    <span>
                      {t.name}{" "}
                      <span className="leise">
                        {t.art === "person" ? "Person" : `Organisation${t.daten.kategorie ? ` · ${t.daten.kategorie}` : ""}`}
                      </span>
                      {namensgleich && (
                        <span className="hinweis-zeile">
                          Gleicher Name wie {namensgleich.rolle_text} dieser Akte; vielleicht doppelt im Verzeichnis.
                        </span>
                      )}
                      {k && (
                        <span className="hinweis-zeile">
                          <span className={`ampel-punkt ampel-${k.ampel}`} aria-hidden="true" /> Möglicher Konflikt:{" "}
                          {k.texte.join(" ")}
                        </span>
                      )}
                    </span>
                    <button className="zweitrangig" onClick={() => void hinzufuegen({ beteiligter_id: t.id })} disabled={laeuft}>
                      Als {optionen.rollen[rolle].text} eintragen
                    </button>
                  </li>
                );
              })}
              {treffer.length === 0 && suche.trim() && <li className="leer">Kein Eintrag gefunden.</li>}
            </ul>
            <div className="aktionen">
              <button className="zweitrangig" onClick={() => oeffnen("person")}>
                Neue Person …
              </button>
              <button className="zweitrangig" onClick={() => oeffnen("organisation")}>
                Neue Organisation …
              </button>
            </div>
          </>
        )}
      </div>

      {formular && (
        <BeteiligterFormular
          key={formular.nr}
          art={formular.art}
          eintrag={formular.eintrag}
          vorbelegung={suche}
          kategorien={optionen.kategorien}
          beziehungen={optionen.beziehungen}
          funktionen={optionen.funktionen ?? []}
          ausfuehren={ausfuehren}
          onFertig={(neu, uebernehmen) => {
            setFormular(null);
            if (neu && uebernehmen) void hinzufuegen({ beteiligter_id: neu.id });
            else void ausfuehren(() => kern<Stammdaten>("akten.stammdaten", { akte_id: akteId })).then((s) => s && onGeaendert(s));
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
export function BeteiligterFormular({
  art,
  eintrag,
  vorbelegung,
  kategorien,
  beziehungen,
  funktionen,
  ausfuehren,
  onFertig,
  rolleText,
  ohneAkte = false,
}: {
  art: "person" | "organisation";
  eintrag?: Beteiligter;
  vorbelegung: string;
  kategorien: string[];
  beziehungen: Record<string, string>;
  funktionen: string[];
  ausfuehren: Ausfuehren;
  onFertig: (neu: Beteiligter | null, uebernehmen: boolean) => void;
  rolleText: string;
  /** Aufruf aus dem Beteiligtenverzeichnis: nur anlegen, nicht in eine Akte eintragen. */
  ohneAkte?: boolean;
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
  // Gesetzliche Vertreter einer neuen Organisation: werden beim Speichern mit angelegt und verknüpft.
  const [vertreter, setVertreter] = useState<VertreterEntwurf[]>([]);
  const felder = art === "person" ? FELDER_PERSON : FELDER_ORG;
  const vertreterBereich = art === "organisation";

  async function pruefeDubletten() {
    const name = art === "person" ? werte.nachname : werte.name;
    if (!name?.trim()) return setDubletten([]);
    const l = await kern<Beteiligter[]>("beteiligte.aehnliche", { art, daten: werte, ausser: aktuell?.id ?? null });
    setDubletten(l);
  }

  useEffect(() => {
    if ((!aktuell && !vertreterBereich) || !bezSuche.trim()) return setBezTreffer([]);
    const t = setTimeout(() => {
      void kern<Beteiligter[]>("beteiligte.liste", { suche: bezSuche }).then((l) =>
        setBezTreffer(l.filter((b) => b.id !== aktuell?.id && (aktuell || b.art === "person")).slice(0, 6)),
      );
    }, 200);
    return () => clearTimeout(t);
  }, [bezSuche, aktuell, vertreterBereich]);

  async function speichern(e: FormEvent, uebernehmen: boolean) {
    e.preventDefault();
    const daten = { ...werte, fruehere_namen: (werte.fruehere_namen ?? "").split("\n") };
    const neu = await ausfuehren(() =>
      kern<Beteiligter>("beteiligte.speichern", {
        art,
        daten,
        beteiligter_id: aktuell?.id ?? null,
        vertreter: vertreter.map((v) =>
          "beteiligter_id" in v ? { beteiligter_id: v.beteiligter_id, funktion: v.funktion } : { ...v.daten, funktion: v.funktion },
        ),
      }),
    );
    if (neu) onFertig(neu, uebernehmen && !aktuell);
  }

  /** Neue Person als gesetzlichen Vertreter: bei einer bestehenden Organisation sofort, sonst beim Speichern. */
  async function vertreterNeu(eingabe: Record<string, string>) {
    const { funktion, ...v } = eingabe;
    if (!aktuell) {
      const name = [v.anrede, v.titel, v.vorname, v.nachname].filter(Boolean).join(" ");
      setVertreter([...vertreter, { daten: v, name, funktion }]);
      return true;
    }
    const p = await ausfuehren(() => kern<Beteiligter>("beteiligte.speichern", { art: "person", daten: v }));
    if (!p) return false;
    await beziehung(p, "gesetzlicher_vertreter", true, funktion);
    return true;
  }

  async function beziehung(anderer: Beteiligter, bezArt: string, vorhanden = true, funktion?: string) {
    if (!aktuell) {
      if (bezArt === "gesetzlicher_vertreter" && !vertreter.some((v) => "beteiligter_id" in v && v.beteiligter_id === anderer.id)) {
        setVertreter([...vertreter, { beteiligter_id: anderer.id, name: anderer.name, funktion: "" }]);
      }
      setBezSuche("");
      return;
    }
    // Gesetzlicher Vertreter: die Person vertritt die Organisation.
    const [von, zu] = bezArt === "gesetzlicher_vertreter" && aktuell.art === "organisation" ? [anderer.id, aktuell.id] : [aktuell.id, anderer.id];
    const neu = await ausfuehren(() =>
      kern<Beteiligter>("beteiligte.beziehung_setzen", { von, zu, art: bezArt, vorhanden, funktion: funktion ?? null }),
    );
    if (neu) {
      setAktuell(await kern<Beteiligter>("beteiligte.eintrag", { beteiligter_id: aktuell.id }));
      setBezSuche("");
    }
  }

  const feld = (k: string, titel: string, breit = false) => (
    <label key={k} className={breit ? "feld feld-breit" : "feld"}>
      {titel}
      {k === "anrede" ? (
        <select value={werte[k] ?? ""} onChange={(ev) => setWerte({ ...werte, [k]: ev.target.value })}>
          <option value="">–</option>
          {["Frau", "Herr", ...(werte[k] && !["Frau", "Herr"].includes(werte[k]) ? [werte[k]] : [])].map((a) => (
            <option key={a}>{a}</option>
          ))}
        </select>
      ) : (
      <input
        type={k === "geburtsdatum" ? "date" : "text"}
        value={werte[k] ?? ""}
        onChange={(ev) => setWerte({ ...werte, [k]: ev.target.value })}
        onBlur={k === "name" || k === "nachname" || k === "vorname" ? () => void pruefeDubletten() : undefined}
      />
      )}
    </label>
  );

  return (
    <div className="eintrag-formular beteiligter-formular" role="dialog" aria-label="Beteiligter">
      <datalist id="vertreter-funktionen">
        {funktionen.map((f) => (
          <option key={f} value={f} />
        ))}
      </datalist>
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
        {vertreterBereich && !aktuell && (
          <div className="beziehungen">
            <h4>Gesetzliche Vertreter (z. B. Geschäftsführer)</h4>
            <ul className="eintraege">
              {vertreter.map((v, i) => (
                <li key={i}>
                  <span>
                    {v.name} <span className="leise">{"beteiligter_id" in v ? "aus dem Verzeichnis" : "wird neu angelegt"}</span>
                  </span>
                  <input
                    className="funktion"
                    list="vertreter-funktionen"
                    aria-label={`Funktion von ${v.name}`}
                    placeholder="Funktion, z. B. Geschäftsführerin"
                    value={v.funktion}
                    onChange={(e) => setVertreter(vertreter.map((w, j) => (j === i ? { ...w, funktion: e.target.value } : w)))}
                  />
                  <button type="button" className="link gefahr" onClick={() => setVertreter(vertreter.filter((_, j) => j !== i))}>
                    Entfernen
                  </button>
                </li>
              ))}
              {vertreter.length === 0 && <li className="leer">Noch keiner.</li>}
            </ul>
            <label className="feld">
              Im Beteiligtenverzeichnis suchen
              <input value={bezSuche} onChange={(e) => setBezSuche(e.target.value)} placeholder="Name der Person" />
            </label>
            <ul className="eintraege">
              {bezTreffer.map((t) => (
                <li key={t.id}>
                  <span>{t.name}</span>
                  <button type="button" className="zweitrangig" onClick={() => void beziehung(t, "gesetzlicher_vertreter")}>
                    Als Vertreter
                  </button>
                </li>
              ))}
            </ul>
            <NeuerVertreter onHinzu={vertreterNeu} />
          </div>
        )}
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
                      {ohneAkte ? "Vorhandenen öffnen" : "Vorhandenen nehmen"}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="aktionen">
          <button type="submit">{aktuell ? "Speichern" : ohneAkte ? "Anlegen" : `Anlegen und als ${rolleText} eintragen`}</button>
          {!aktuell && !ohneAkte && (
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
                {b.art === "gesetzlicher_vertreter" && (
                  <FunktionFeld
                    wert={b.funktion ?? ""}
                    onSpeichern={(f) =>
                      void ausfuehren(() => kern<Beteiligter>("beteiligte.beziehung_setzen", { von: b.von, zu: b.zu, art: b.art, funktion: f })).then(
                        async () => setAktuell(await kern<Beteiligter>("beteiligte.eintrag", { beteiligter_id: aktuell.id })),
                      )
                    }
                  />
                )}
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
          {aktuell.art === "organisation" && <NeuerVertreter onHinzu={vertreterNeu} />}
          {!ohneAkte && (aktuell.akten ?? []).length > 0 && (
            <p className="leise">
              Beteiligt an: {(aktuell.akten ?? []).map((a) => `${a.aktenzeichen ?? a.akte}`).join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

type VertreterEntwurf =
  | { beteiligter_id: number; name: string; funktion: string }
  | { daten: Record<string, string>; name: string; funktion: string };

/** Eine Person direkt als gesetzlichen Vertreter anlegen, mit Hinweis, falls es sie schon gibt. */
function NeuerVertreter({ onHinzu }: { onHinzu: (daten: Record<string, string>) => Promise<boolean> }) {
  const leer = { anrede: "", titel: "", vorname: "", nachname: "", funktion: "" };
  const [v, setV] = useState(leer);
  const [vorhanden, setVorhanden] = useState<Beteiligter[] | null>(null);

  async function hinzu(trotzdem = false) {
    if (!v.nachname.trim()) return;
    if (!trotzdem) {
      const l = await kern<Beteiligter[]>("beteiligte.aehnliche", { art: "person", daten: v });
      if (l.length > 0) return setVorhanden(l);
    }
    if (await onHinzu(v)) {
      setV(leer);
      setVorhanden(null);
    }
  }

  return (
    <div className="neuer-vertreter">
      <div className="formular-raster">
        <label className="feld">
          Anrede
          <select value={v.anrede} onChange={(e) => setV({ ...v, anrede: e.target.value })}>
            <option value="">–</option>
            <option>Frau</option>
            <option>Herr</option>
          </select>
        </label>
        <label className="feld">
          Titel
          <input value={v.titel} onChange={(e) => setV({ ...v, titel: e.target.value })} placeholder="z. B. Dr." />
        </label>
        <label className="feld">
          Vorname
          <input value={v.vorname} onChange={(e) => setV({ ...v, vorname: e.target.value })} />
        </label>
        <label className="feld">
          Nachname
          <input value={v.nachname} onChange={(e) => setV({ ...v, nachname: e.target.value })} />
        </label>
        <label className="feld">
          Funktion
          <input list="vertreter-funktionen" value={v.funktion} onChange={(e) => setV({ ...v, funktion: e.target.value })}
            placeholder="z. B. Geschäftsführerin" />
        </label>
      </div>
      <div className="aktionen">
        <button type="button" className="zweitrangig" onClick={() => void hinzu()} disabled={!v.nachname.trim()}>
          Neue Person als Vertreter
        </button>
      </div>
      {vorhanden && (
        <div className="hinweis-box">
          <strong>Diesen Namen gibt es schon im Verzeichnis:</strong> {vorhanden.map((p) => p.name).join(", ")}. Über
          die Suche oben lässt sich der vorhandene Eintrag nehmen.{" "}
          <button type="button" className="link" onClick={() => void hinzu(true)}>
            Trotzdem neu anlegen
          </button>
        </div>
      )}
    </div>
  );
}

/** Funktion eines gesetzlichen Vertreters, gespeichert beim Verlassen des Felds. */
function FunktionFeld({ wert, onSpeichern }: { wert: string; onSpeichern: (f: string) => void }) {
  const [f, setF] = useState(wert);
  useEffect(() => setF(wert), [wert]);
  return (
    <input
      className="funktion"
      list="vertreter-funktionen"
      aria-label="Funktion"
      placeholder="Funktion"
      value={f}
      onChange={(e) => setF(e.target.value)}
      onBlur={() => f.trim() !== wert && onSpeichern(f.trim())}
    />
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

  // Nur aufklappen, wenn noch etwas zu entscheiden ist; sonst genügt eine Zeile.
  const offen = !!pruefung && pruefung.ampel !== "gruen" && !pruefung.entscheidung;
  const [details, setDetails] = useState(false);
  const zeigen = offen || details;

  if (!zeigen) {
    return (
      <div className="kollision kollision-kurz">
        {pruefung ? (
          <span className={`ampel ampel-${pruefung.ampel}`}>
            <span className="ampel-punkt" aria-hidden="true" /> Kollisionsprüfung: {AMPEL_TEXT[pruefung.ampel]}
          </span>
        ) : (
          <span className="leise">Kollisionsprüfung: läuft automatisch, sobald Mandant oder Gegner eingetragen sind.</span>
        )}
        {pruefung && (
          <span className="leise">
            {pruefung.entscheidung && ` · ${pruefung.entscheidung_text}`} · geprüft am{" "}
            {new Date(pruefung.zeitpunkt).toLocaleString("de-DE")}
          </span>
        )}
        <button className="link" onClick={() => setDetails(true)}>
          Details
        </button>
        <button className="link" onClick={() => void pruefen()} disabled={laeuft}>
          {pruefung ? "Erneut prüfen" : "Jetzt prüfen"}
        </button>
      </div>
    );
  }

  return (
    <div className="kollision">
      <div className="kopf">
        <h3>Kollisionsprüfung</h3>
        <span className="aktionen">
          {!offen && (
            <button className="link" onClick={() => setDetails(false)}>
              Einklappen
            </button>
          )}
          <button className="zweitrangig" onClick={() => void pruefen()} disabled={laeuft}>
            {pruefung ? "Erneut prüfen" : "Jetzt prüfen"}
          </button>
        </span>
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
