import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import { open, save } from "@tauri-apps/plugin-dialog";
import { Rueckfrage } from "./Akte";
import SuchAuswahl, { SUCHE_AB } from "./SuchAuswahl";
import {
  EigeneAenderung,
  EigeneDaten as Stand,
  EigeneFelder,
  EigeneOrganisation,
  EigenePerson,
  FeldDef,
  Organisationsform,
  Werte,
  feldText,
  istDesktop,
  kern,
  personName,
  startwerte,
  zeitpunktDe,
} from "./kern";

// Karten der Organisationsformen, Wortlaut nach dem Konzept „Eigene Daten“ (Abschnitt 4).
const FORMKARTEN: { form: Organisationsform; titel: string; text: string }[] = [
  {
    form: "einzelanwalt",
    titel: "Einzelanwalt",
    text: "Sie führen Ihre Kanzlei allein, auch mit Mitarbeitenden oder in einer Bürogemeinschaft.",
  },
  {
    form: "kanzlei",
    titel: "Kanzlei",
    text: "Mehrere Berufsträger in einer Sozietät oder Berufsausübungsgesellschaft (z. B. PartG mbB, GmbH).",
  },
  {
    form: "rechtsabteilung",
    titel: "Rechtsabteilung",
    text: "Sie arbeiten als Syndikusrechtsanwalt oder Unternehmensjurist für ein Unternehmen und gegebenenfalls für dessen Konzerngesellschaften.",
  },
];

type Schritt = "form" | "einzel" | "organisation" | "inhaber" | "berufstraeger" | "einheiten" | "zusammenfassung";

const SCHRITTE: Record<Organisationsform, Schritt[]> = {
  einzelanwalt: ["form", "einzel", "zusammenfassung"],
  kanzlei: ["form", "organisation", "inhaber", "berufstraeger", "zusammenfassung"],
  rechtsabteilung: ["form", "organisation", "inhaber", "einheiten", "zusammenfassung"],
};

const VERWENDUNG = {
  organisation: "Wird beim Anlegen einer Akte als eigene Seite verwendet und später für den Briefkopf.",
  inhaber: "Sie sind der Profilinhaber; beim Anlegen einer Akte werden Sie als Bearbeiter vorgeschlagen.",
  berufstraeger: "Beim Anlegen einer Akte als Sachbearbeiter wählbar; später für den Briefbogen (§ 10 BORA).",
  konzerngesellschaft: "Tritt beim Anlegen einer Akte an die Stelle des Mandanten.",
  beauftragte_kanzlei: "In der Akte wird daraus der vertretende Anwalt der eigenen Seite gewählt.",
};

function orgTitel(form: Organisationsform | null): string {
  return form === "rechtsabteilung" ? "Unternehmen und Rechtsabteilung" : "Kanzlei";
}

/** Bereich „Eigene Daten“: Assistent beim ersten Mal, danach eine Übersicht zum Pflegen. */
export default function EigeneDaten({ onZurueck }: { onZurueck: () => void }) {
  const [felder, setFelder] = useState<EigeneFelder | null>(null);
  const [stand, setStand] = useState<Stand | null>(null);
  const [schritt, setSchritt] = useState<Schritt | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [importFrage, setImportFrage] = useState<string | null>(null);

  const ausfuehren = useCallback(async <T,>(arbeit: () => Promise<T>): Promise<T | null> => {
    setLaeuft(true);
    setFehler(null);
    try {
      return await arbeit();
    } catch (e) {
      setFehler(String(e));
      return null;
    } finally {
      setLaeuft(false);
    }
  }, []);

  useEffect(() => {
    if (!istDesktop) return;
    void ausfuehren(async () => {
      const [f, s] = await Promise.all([kern<EigeneFelder>("eigene.felder"), kern<Stand>("eigene.stand")]);
      setFelder(f);
      setStand(s);
      if (!s.profil.assistent_fertig) setSchritt(s.profil.form ? SCHRITTE[s.profil.form][1] : "form");
    });
  }, [ausfuehren]);

  async function aufruf(methode: string, params: Record<string, unknown> = {}): Promise<Stand | null> {
    setMeldung(null);
    const s = await ausfuehren(() => kern<Stand>(methode, params));
    if (s) setStand(s);
    return s;
  }

  async function aufrufMitStand(methode: string, params: Record<string, unknown>): Promise<boolean> {
    setMeldung(null);
    const r = await ausfuehren(() => kern<{ id: number; stand: Stand }>(methode, params));
    if (r) setStand(r.stand);
    return r !== null;
  }

  async function importieren(ersetzen: boolean, pfad?: string) {
    const gewaehlt =
      pfad ??
      (await open({
        title: "Eigene Daten importieren",
        multiple: false,
        filters: [{ name: "Eigene Daten (JSON)", extensions: ["json"] }],
      }));
    if (typeof gewaehlt !== "string") return;
    setMeldung(null);
    setLaeuft(true);
    setFehler(null);
    try {
      const s = await kern<Stand>("eigene.importieren", { pfad: gewaehlt, ersetzen });
      setStand(s);
      setSchritt(null);
      setMeldung("Die Eigenen Daten wurden importiert.");
    } catch (e) {
      if (!ersetzen && String(e).includes("ersetzt")) setImportFrage(gewaehlt);
      else setFehler(String(e));
    } finally {
      setLaeuft(false);
    }
  }

  async function exportieren() {
    const ziel = await save({
      title: "Eigene Daten exportieren",
      defaultPath: "eigene-daten.json",
      filters: [{ name: "Eigene Daten (JSON)", extensions: ["json"] }],
    });
    if (!ziel) return;
    const r = await ausfuehren(() => kern<{ pfad: string }>("eigene.exportieren", { pfad: ziel }));
    if (r) setMeldung(`Gespeichert unter ${r.pfad}`);
  }

  if (!istDesktop) {
    return (
      <section className="hinweis-box">
        Die Oberfläche läuft gerade im Browser. Eigene Daten gibt es nur in der Desktop-App: <code>npm run tauri dev</code>
      </section>
    );
  }
  if (!felder || !stand) {
    return <p className="status">{fehler ?? "Lade Eigene Daten …"}</p>;
  }

  const meldungen = (
    <>
      {meldung && <p className="status">{meldung}</p>}
      {fehler && <p className="fehler">{fehler}</p>}
      {importFrage && (
        <Rueckfrage
          frage="Vorhandene Eigene Daten ersetzen?"
          erklaerung="In dieser Umgebung gibt es schon Eigene Daten. Der Import ersetzt sie vollständig. Akten und Gesetze bleiben unverändert."
          ja="Ersetzen"
          onJa={() => {
            const p = importFrage;
            setImportFrage(null);
            void importieren(true, p);
          }}
          onNein={() => setImportFrage(null)}
        />
      )}
    </>
  );

  if (schritt) {
    return (
      <div className="eigene">
        <Assistent
          felder={felder}
          stand={stand}
          schritt={schritt}
          setSchritt={setSchritt}
          aufruf={aufruf}
          aufrufMitStand={aufrufMitStand}
          laeuft={laeuft}
          onSpaeter={onZurueck}
          onImport={() => void importieren(false)}
        />
        {meldungen}
      </div>
    );
  }

  return (
    <div className="eigene">
      <Uebersicht
        felder={felder}
        stand={stand}
        aufruf={aufruf}
        aufrufMitStand={aufrufMitStand}
        laeuft={laeuft}
        onAssistent={() => setSchritt("form")}
        onImport={() => void importieren(false)}
        onExport={() => void exportieren()}
        meldungen={meldungen}
      />
    </div>
  );
}

type Aufruf = (methode: string, params?: Record<string, unknown>) => Promise<Stand | null>;
type AufrufMitStand = (methode: string, params: Record<string, unknown>) => Promise<boolean>;

// ---------------------------------------------------------------- Assistent

function Assistent({
  felder,
  stand,
  schritt,
  setSchritt,
  aufruf,
  aufrufMitStand,
  laeuft,
  onSpaeter,
  onImport,
}: {
  felder: EigeneFelder;
  stand: Stand;
  schritt: Schritt;
  setSchritt: (s: Schritt | null) => void;
  aufruf: Aufruf;
  aufrufMitStand: AufrufMitStand;
  laeuft: boolean;
  onSpaeter: () => void;
  onImport: () => void;
}) {
  const form = stand.profil.form;
  const schritte = form ? SCHRITTE[form] : (["form"] as Schritt[]);
  const nr = schritte.indexOf(schritt) + 1;
  const orgFelder = felder.felder[stand.organisation_felder];
  const inhaberFelder = felder.felder[stand.inhaber_felder];
  const [org, setOrg] = useState<Werte>(() => startwerte(orgFelder, stand.organisation?.daten));
  const [ich, setIch] = useState<Werte>(() => startwerte(inhaberFelder, stand.inhaber?.daten));
  const [mitglied, setMitglied] = useState<Werte>(() =>
    startwerte(felder.felder.mitgliedschaft, stand.berufstraeger.find((b) => b.id === stand.profil.person_id)?.mitgliedschaft),
  );

  // Nach einem Formwechsel gelten andere Felder; die Formulare übernehmen den gespeicherten Stand.
  useEffect(() => {
    setOrg(startwerte(felder.felder[stand.organisation_felder], stand.organisation?.daten));
    setIch(startwerte(felder.felder[stand.inhaber_felder], stand.inhaber?.daten));
  }, [stand.profil.form]);

  async function speichereSchritt(): Promise<boolean> {
    if (schritt === "einzel") {
      return (await aufruf("eigene.inhaber_speichern", { daten: ich })) !== null &&
        (await aufruf("eigene.organisation_speichern", { daten: org })) !== null;
    }
    if (schritt === "organisation") return (await aufruf("eigene.organisation_speichern", { daten: org })) !== null;
    if (schritt === "inhaber") {
      const params = form === "kanzlei" ? { daten: ich, mitgliedschaft: mitglied } : { daten: ich };
      return (await aufruf("eigene.inhaber_speichern", params)) !== null;
    }
    return true;
  }

  async function weiter(e?: FormEvent) {
    e?.preventDefault();
    if (!(await speichereSchritt())) return;
    if (form) setSchritt(schritte[nr] ?? "zusammenfassung");
  }

  async function zurueck() {
    if (!(await speichereSchritt())) return;
    setSchritt(schritte[nr - 2] ?? "form");
  }

  async function waehle(neu: Organisationsform) {
    const s = await aufruf("eigene.form_setzen", { form: neu });
    if (s) setSchritt(SCHRITTE[neu][1]);
  }

  async function fertig() {
    const s = await aufruf("eigene.assistent_fertig", { fertig: true });
    if (s) setSchritt(null);
  }

  return (
    <>
      <header className="kopf">
        <h1>Eigene Daten</h1>
        {form && (
          <span className="leise">
            Schritt {nr} von {schritte.length}
          </span>
        )}
      </header>

      {schritt === "form" && (
        <>
          <p className="frage-gross">In welchem Rahmen arbeiten Sie mit JuraBox?</p>
          <div className="formkarten">
            {FORMKARTEN.map((k) => (
              <button
                key={k.form}
                className={k.form === form ? "formkarte gewaehlt" : "formkarte"}
                disabled={laeuft}
                onClick={() => void waehle(k.form)}
              >
                <strong>{k.titel}</strong>
                <span>{k.text}</span>
              </button>
            ))}
          </div>
          <div className="aktionen">
            <button className="zweitrangig" onClick={onSpaeter}>
              Später ausfüllen
            </button>
            <button className="zweitrangig" onClick={onImport} disabled={laeuft}>
              Profil importieren
            </button>
          </div>
        </>
      )}

      {schritt === "einzel" && (
        <form onSubmit={(e) => void weiter(e)}>
          <section className="karte">
            <h2>Ihre Person</h2>
            <Formular felder={inhaberFelder} werte={ich} onAendern={setIch} />
          </section>
          <section className="karte">
            <h2>Kanzlei</h2>
            <Formular felder={orgFelder} werte={org} onAendern={setOrg} />
          </section>
          <Navigation laeuft={laeuft} onZurueck={() => void zurueck()} onSpaeter={onSpaeter} />
        </form>
      )}

      {schritt === "organisation" && (
        <form onSubmit={(e) => void weiter(e)}>
          <section className="karte">
            <h2>{orgTitel(form)}</h2>
            <Formular felder={orgFelder} werte={org} onAendern={setOrg} />
          </section>
          <Navigation laeuft={laeuft} onZurueck={() => void zurueck()} onSpaeter={onSpaeter} />
        </form>
      )}

      {schritt === "inhaber" && (
        <form onSubmit={(e) => void weiter(e)}>
          <section className="karte">
            <h2>Ihre Person</h2>
            <p className="erklaerung">{VERWENDUNG.inhaber}</p>
            <Formular felder={inhaberFelder} werte={ich} onAendern={setIch} />
            {form === "kanzlei" && (
              <>
                <h3>In der Kanzlei</h3>
                <Formular felder={felder.felder.mitgliedschaft} werte={mitglied} onAendern={setMitglied} />
              </>
            )}
          </section>
          <Navigation laeuft={laeuft} onZurueck={() => void zurueck()} onSpaeter={onSpaeter} />
        </form>
      )}

      {schritt === "berufstraeger" && (
        <>
          <Berufstraeger felder={felder} stand={stand} aufruf={aufruf} aufrufMitStand={aufrufMitStand} laeuft={laeuft} />
          <Navigation laeuft={laeuft} onZurueck={() => void zurueck()} onSpaeter={onSpaeter} onWeiter={() => void weiter()} />
        </>
      )}

      {schritt === "einheiten" && (
        <>
          <Einheiten
            art="konzerngesellschaft"
            felder={felder}
            stand={stand}
            aufruf={aufruf}
            aufrufMitStand={aufrufMitStand}
            laeuft={laeuft}
          />
          <Einheiten
            art="beauftragte_kanzlei"
            felder={felder}
            stand={stand}
            aufruf={aufruf}
            aufrufMitStand={aufrufMitStand}
            laeuft={laeuft}
          />
          <Navigation laeuft={laeuft} onZurueck={() => void zurueck()} onSpaeter={onSpaeter} onWeiter={() => void weiter()} />
        </>
      )}

      {schritt === "zusammenfassung" && (
        <>
          <Vollstaendigkeit stand={stand} />
          <section className="karte">
            <h2>{orgTitel(form)}</h2>
            <Anzeige felder={orgFelder} werte={stand.organisation?.daten} />
          </section>
          <section className="karte">
            <h2>Ihre Person</h2>
            <Anzeige felder={inhaberFelder} werte={stand.inhaber?.daten} />
          </section>
          {form === "kanzlei" && (
            <p className="erklaerung">Berufsträger: {stand.berufstraeger.map((b) => personName(b.daten)).join(", ") || "keine"}</p>
          )}
          {form === "rechtsabteilung" && (
            <p className="erklaerung">
              Konzerngesellschaften: {stand.konzerngesellschaften.length} · Beauftragte Kanzleien:{" "}
              {stand.beauftragte_kanzleien.length}
            </p>
          )}
          <div className="aktionen">
            <button onClick={() => void fertig()} disabled={laeuft}>
              Fertig
            </button>
            <button className="zweitrangig" onClick={() => setSchritt(schritte[nr - 2])}>
              Zurück
            </button>
          </div>
        </>
      )}
    </>
  );
}

function Navigation({
  laeuft,
  onZurueck,
  onSpaeter,
  onWeiter,
}: {
  laeuft: boolean;
  onZurueck: () => void;
  onSpaeter: () => void;
  onWeiter?: () => void;
}) {
  return (
    <div className="aktionen assistent-navigation">
      {onWeiter ? (
        <button type="button" onClick={onWeiter} disabled={laeuft}>
          Weiter
        </button>
      ) : (
        <button type="submit" disabled={laeuft}>
          Weiter
        </button>
      )}
      <button type="button" className="zweitrangig" onClick={onZurueck} disabled={laeuft}>
        Zurück
      </button>
      <button type="button" className="zweitrangig" onClick={onSpaeter}>
        Später fortsetzen
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- Übersicht

function Uebersicht({
  felder,
  stand,
  aufruf,
  aufrufMitStand,
  laeuft,
  onAssistent,
  onImport,
  onExport,
  meldungen,
}: {
  felder: EigeneFelder;
  stand: Stand;
  aufruf: Aufruf;
  aufrufMitStand: AufrufMitStand;
  laeuft: boolean;
  onAssistent: () => void;
  onImport: () => void;
  onExport: () => void;
  meldungen: ReactNode;
}) {
  const form = stand.profil.form;
  const [neueForm, setNeueForm] = useState<Organisationsform | null>(null);
  const [aenderungen, setAenderungen] = useState<EigeneAenderung[] | null>(null);
  const [mitArchiv, setMitArchiv] = useState(false);
  const orgFelder = felder.felder[stand.organisation_felder];
  const inhaberFelder = felder.felder[stand.inhaber_felder];
  const meineMitgliedschaft = stand.berufstraeger.find((b) => b.id === stand.profil.person_id)?.mitgliedschaft;

  async function ladeAenderungen() {
    setAenderungen(await kern<EigeneAenderung[]>("eigene.aenderungen", { limit: 30 }));
  }

  if (!form) {
    return (
      <>
        <header className="kopf">
          <h1>Eigene Daten</h1>
        </header>
        <p className="erklaerung">Noch nicht eingerichtet.</p>
        <button onClick={onAssistent}>Einrichten</button>
        {meldungen}
      </>
    );
  }
  const wechselArchiviert = (neu: Organisationsform) =>
    stand.organisation !== null && (neu === "rechtsabteilung") !== (form === "rechtsabteilung");

  return (
    <>
      <header className="kopf">
        <h1>Eigene Daten</h1>
        <div className="aktionen">
          <button className="zweitrangig" onClick={onImport} disabled={laeuft}>
            Importieren
          </button>
          <button className="zweitrangig" onClick={onExport} disabled={laeuft}>
            Exportieren
          </button>
        </div>
      </header>
      <p className="erklaerung">
        Organisationsform: <strong>{stand.formen[form]}</strong>{" "}
        <select
          aria-label="Organisationsform ändern"
          value=""
          onChange={(e) => e.target.value && setNeueForm(e.target.value as Organisationsform)}
        >
          <option value="">ändern …</option>
          {FORMKARTEN.filter((k) => k.form !== form).map((k) => (
            <option key={k.form} value={k.form}>
              {k.titel}
            </option>
          ))}
        </select>
      </p>
      {neueForm && (
        <Rueckfrage
          frage={`Organisationsform auf „${stand.formen[neueForm]}“ ändern?`}
          erklaerung={
            wechselArchiviert(neueForm)
              ? `Die bisherige ${form === "rechtsabteilung" ? "Unternehmensangabe" : "Kanzlei"} wird archiviert und bleibt für bestehende Akten erhalten. Ihre Person bleibt, ebenso alle anderen Einträge.`
              : "Die Kanzlei bleibt dieselbe; es ändern sich nur die angezeigten Felder."
          }
          ja="Ändern"
          onJa={() => {
            const neu = neueForm;
            setNeueForm(null);
            void aufruf("eigene.form_setzen", { form: neu });
          }}
          onNein={() => setNeueForm(null)}
        />
      )}
      {meldungen}
      <Vollstaendigkeit stand={stand} />

      <Abschnitt
        titel={orgTitel(form)}
        verwendung={VERWENDUNG.organisation}
        felder={orgFelder}
        werte={stand.organisation?.daten}
        laeuft={laeuft}
        onSpeichern={(daten) => aufruf("eigene.organisation_speichern", { daten })}
      />
      <Abschnitt
        titel="Ihre Person"
        verwendung={VERWENDUNG.inhaber}
        felder={inhaberFelder}
        werte={stand.inhaber?.daten}
        zusatzFelder={form === "kanzlei" && stand.organisation ? felder.felder.mitgliedschaft : undefined}
        zusatzWerte={meineMitgliedschaft}
        laeuft={laeuft}
        onSpeichern={(daten, mitgliedschaft) =>
          aufruf("eigene.inhaber_speichern", mitgliedschaft ? { daten, mitgliedschaft } : { daten })
        }
      />

      <label className="schalter-zeile">
        <input type="checkbox" checked={mitArchiv} onChange={(e) => setMitArchiv(e.target.checked)} /> Archivierte
        Einträge zeigen
      </label>
      {form === "kanzlei" && stand.organisation && (
        <Berufstraeger
          felder={felder}
          stand={stand}
          aufruf={aufruf}
          aufrufMitStand={aufrufMitStand}
          laeuft={laeuft}
          mitArchiv={mitArchiv}
        />
      )}
      {form === "rechtsabteilung" && (
        <>
          <Einheiten
            art="konzerngesellschaft"
            felder={felder}
            stand={stand}
            aufruf={aufruf}
            aufrufMitStand={aufrufMitStand}
            laeuft={laeuft}
            mitArchiv={mitArchiv}
          />
          <Einheiten
            art="beauftragte_kanzlei"
            felder={felder}
            stand={stand}
            aufruf={aufruf}
            aufrufMitStand={aufrufMitStand}
            laeuft={laeuft}
            mitArchiv={mitArchiv}
          />
        </>
      )}

      <details
        className="karte"
        onToggle={(e) => {
          if ((e.target as HTMLDetailsElement).open) void ladeAenderungen();
        }}
      >
        <summary>Änderungsprotokoll</summary>
        {aenderungen === null ? (
          <p className="status">Lade …</p>
        ) : aenderungen.length === 0 ? (
          <p className="leer">Noch keine Änderungen.</p>
        ) : (
          <table className="tabelle">
            <tbody>
              {aenderungen.map((a) => (
                <tr key={a.id}>
                  <td>{zeitpunktDe(a.zeitpunkt)}</td>
                  <td>{a.bezeichnung}</td>
                  <td>{a.feld}</td>
                  <td>
                    {a.alt ?? "–"} → {a.neu ?? "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </details>
    </>
  );
}

function Vollstaendigkeit({ stand }: { stand: Stand }) {
  if (stand.fehlend.length === 0 && stand.hinweise.length === 0) {
    return <p className="ki-zeile bereit">Profil vollständig.</p>;
  }
  return (
    <section className="karte vollstaendigkeit">
      {stand.fehlend.length > 0 && (
        <>
          <h3>Es fehlen noch</h3>
          <ul>
            {stand.fehlend.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </>
      )}
      {stand.hinweise.length > 0 && (
        <>
          <h3>Hinweise</h3>
          <ul>
            {stand.hinweise.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/** Ein Abschnitt mit Anzeige und „Bearbeiten“. */
function Abschnitt({
  titel,
  verwendung,
  felder,
  werte,
  zusatzFelder,
  zusatzWerte,
  laeuft,
  onSpeichern,
}: {
  titel: string;
  verwendung: string;
  felder: FeldDef[];
  werte: Werte | undefined;
  zusatzFelder?: FeldDef[];
  zusatzWerte?: Werte;
  laeuft: boolean;
  onSpeichern: (daten: Werte, zusatz?: Werte) => Promise<Stand | null>;
}) {
  const [entwurf, setEntwurf] = useState<Werte | null>(null);
  const [zusatz, setZusatz] = useState<Werte | null>(null);

  async function speichern(e: FormEvent) {
    e.preventDefault();
    if (!entwurf) return;
    if (await onSpeichern(entwurf, zusatz ?? undefined)) {
      setEntwurf(null);
      setZusatz(null);
    }
  }

  return (
    <section className="karte">
      <div className="kopf">
        <h2>{titel}</h2>
        {!entwurf && (
          <button
            className="zweitrangig"
            onClick={() => {
              setEntwurf(startwerte(felder, werte));
              if (zusatzFelder) setZusatz(startwerte(zusatzFelder, zusatzWerte));
            }}
          >
            Bearbeiten
          </button>
        )}
      </div>
      <p className="erklaerung">{verwendung}</p>
      {entwurf ? (
        <form onSubmit={(e) => void speichern(e)}>
          <Formular felder={felder} werte={entwurf} onAendern={setEntwurf} />
          {zusatzFelder && zusatz && <Formular felder={zusatzFelder} werte={zusatz} onAendern={setZusatz} />}
          <div className="aktionen">
            <button type="submit" disabled={laeuft}>
              Speichern
            </button>
            <button type="button" className="zweitrangig" onClick={() => setEntwurf(null)}>
              Abbrechen
            </button>
          </div>
        </form>
      ) : (
        <>
          <Anzeige felder={felder} werte={werte} />
          {zusatzFelder && <Anzeige felder={zusatzFelder} werte={zusatzWerte} />}
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- Listen

function Berufstraeger({
  felder,
  stand,
  aufruf,
  aufrufMitStand,
  laeuft,
  mitArchiv = false,
}: {
  felder: EigeneFelder;
  stand: Stand;
  aufruf: Aufruf;
  aufrufMitStand: AufrufMitStand;
  laeuft: boolean;
  mitArchiv?: boolean;
}) {
  const orgId = stand.organisation?.id;
  const [bearbeitet, setBearbeitet] = useState<{ id: number | null; daten: Werte; mitglied: Werte } | null>(null);
  const [loeschfrage, setLoeschfrage] = useState<EigenePerson | null>(null);
  const personFelder = felder.felder.person_anwalt;
  const mitgliedFelder = felder.felder.mitgliedschaft;
  if (!orgId) return <p className="leer">Bitte zuerst die Kanzlei speichern.</p>;

  async function speichern(e: FormEvent) {
    e.preventDefault();
    if (!bearbeitet) return;
    const ok = await aufrufMitStand("eigene.person_speichern", {
      organisation_id: orgId,
      daten: bearbeitet.daten,
      mitgliedschaft: bearbeitet.mitglied,
      person_id: bearbeitet.id,
    });
    if (ok) setBearbeitet(null);
  }

  const liste = stand.berufstraeger.filter((b) => mitArchiv || !b.archiviert);
  return (
    <section className="karte">
      <div className="kopf">
        <h2>Berufsträger der Kanzlei</h2>
        {!bearbeitet && (
          <button
            className="zweitrangig"
            onClick={() => setBearbeitet({ id: null, daten: startwerte(personFelder, null), mitglied: startwerte(mitgliedFelder, null) })}
          >
            Hinzufügen
          </button>
        )}
      </div>
      <p className="erklaerung">{VERWENDUNG.berufstraeger}</p>
      {bearbeitet && (
        <form className="eintrag-formular" onSubmit={(e) => void speichern(e)}>
          <Formular felder={personFelder} werte={bearbeitet.daten} onAendern={(d) => setBearbeitet({ ...bearbeitet, daten: d })} />
          <Formular
            felder={mitgliedFelder}
            werte={bearbeitet.mitglied}
            onAendern={(m) => setBearbeitet({ ...bearbeitet, mitglied: m })}
          />
          <div className="aktionen">
            <button type="submit" disabled={laeuft}>
              Speichern
            </button>
            <button type="button" className="zweitrangig" onClick={() => setBearbeitet(null)}>
              Abbrechen
            </button>
          </div>
        </form>
      )}
      <ul className="eintraege">
        {liste.map((b) => {
          const ich = b.id === stand.profil.person_id;
          return (
            <li key={b.id} className={b.archiviert ? "archiviert" : undefined}>
              <span>
                <strong>{personName(b.daten)}</strong>
                {ich && <span className="marke-aktiv">Sie</span>}
                <span className="leise">
                  {" "}
                  {[b.daten.berufsbezeichnung, b.mitgliedschaft.stellung, b.mitgliedschaft.ausgeschieden_am ? "ausgeschieden" : ""]
                    .filter(Boolean)
                    .join(" · ")}
                  {b.archiviert ? " · archiviert" : ""}
                </span>
              </span>
              <span className="aktionen">
                <button
                  className="link"
                  onClick={() =>
                    setBearbeitet({
                      id: b.id,
                      daten: startwerte(personFelder, b.daten),
                      mitglied: startwerte(mitgliedFelder, b.mitgliedschaft),
                    })
                  }
                >
                  Bearbeiten
                </button>
                {!ich && !b.archiviert && (
                  <button className="link" onClick={() => void aufruf("eigene.inhaber_waehlen", { person_id: b.id })}>
                    Das bin ich
                  </button>
                )}
                {!ich && (
                  <button
                    className="link"
                    onClick={() =>
                      void aufruf("eigene.archivieren", { objekt: "person", objekt_id: b.id, archiviert: !b.archiviert })
                    }
                  >
                    {b.archiviert ? "Zurückholen" : "Archivieren"}
                  </button>
                )}
                {!ich && (
                  <button className="link gefahr" onClick={() => setLoeschfrage(b)}>
                    Löschen
                  </button>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      {loeschfrage && (
        <Rueckfrage
          frage={`${personName(loeschfrage.daten)} löschen?`}
          erklaerung="Der Eintrag wird ganz entfernt. Wer nur nicht mehr in der Kanzlei ist, wird besser mit einem Ausscheidedatum versehen oder archiviert."
          ja="Löschen"
          onJa={() => {
            const p = loeschfrage;
            setLoeschfrage(null);
            void aufruf("eigene.loeschen", { objekt: "person", objekt_id: p.id });
          }}
          onNein={() => setLoeschfrage(null)}
        />
      )}
    </section>
  );
}

function Einheiten({
  art,
  felder,
  stand,
  aufruf,
  aufrufMitStand,
  laeuft,
  mitArchiv = false,
}: {
  art: "konzerngesellschaft" | "beauftragte_kanzlei";
  felder: EigeneFelder;
  stand: Stand;
  aufruf: Aufruf;
  aufrufMitStand: AufrufMitStand;
  laeuft: boolean;
  mitArchiv?: boolean;
}) {
  const [bearbeitet, setBearbeitet] = useState<{ id: number | null; daten: Werte } | null>(null);
  const [loeschfrage, setLoeschfrage] = useState<EigeneOrganisation | null>(null);
  const eigeneFelder = felder.felder[art];
  const alle = art === "konzerngesellschaft" ? stand.konzerngesellschaften : stand.beauftragte_kanzleien;
  const liste = alle.filter((o) => mitArchiv || !o.archiviert);
  const titel = art === "konzerngesellschaft" ? "Konzerngesellschaften" : "Beauftragte Kanzleien";

  async function speichern(e: FormEvent) {
    e.preventDefault();
    if (!bearbeitet) return;
    const ok = await aufrufMitStand("eigene.einheit_speichern", { art, daten: bearbeitet.daten, einheit_id: bearbeitet.id });
    if (ok) setBearbeitet(null);
  }

  return (
    <section className="karte">
      <div className="kopf">
        <h2>{titel}</h2>
        {!bearbeitet && (
          <button className="zweitrangig" onClick={() => setBearbeitet({ id: null, daten: startwerte(eigeneFelder, null) })}>
            Hinzufügen
          </button>
        )}
      </div>
      <p className="erklaerung">{VERWENDUNG[art]}</p>
      {bearbeitet && (
        <form className="eintrag-formular" onSubmit={(e) => void speichern(e)}>
          <Formular felder={eigeneFelder} werte={bearbeitet.daten} onAendern={(d) => setBearbeitet({ ...bearbeitet, daten: d })} />
          <div className="aktionen">
            <button type="submit" disabled={laeuft}>
              Speichern
            </button>
            <button type="button" className="zweitrangig" onClick={() => setBearbeitet(null)}>
              Abbrechen
            </button>
          </div>
        </form>
      )}
      {liste.length === 0 && !bearbeitet && <p className="leer">Noch keine Einträge.</p>}
      <ul className="eintraege">
        {liste.map((o) => (
          <li key={o.id} className={o.archiviert ? "archiviert" : undefined}>
            <div className="eintrag-kopf">
              <span>
                <strong>{String(o.daten.name ?? "")}</strong>
                <span className="leise">
                  {" "}
                  {[o.daten.rechtsform, o.daten.ort].filter(Boolean).join(" · ")}
                  {o.archiviert ? " · archiviert" : ""}
                </span>
              </span>
              <span className="aktionen">
                <button className="link" onClick={() => setBearbeitet({ id: o.id, daten: startwerte(eigeneFelder, o.daten) })}>
                  Bearbeiten
                </button>
                <button className="link" onClick={() => void aufrufMitStand("eigene.duplizieren", { organisation_id: o.id })}>
                  Duplizieren
                </button>
                <button
                  className="link"
                  onClick={() =>
                    void aufruf("eigene.archivieren", { objekt: "organisation", objekt_id: o.id, archiviert: !o.archiviert })
                  }
                >
                  {o.archiviert ? "Zurückholen" : "Archivieren"}
                </button>
                <button className="link gefahr" onClick={() => setLoeschfrage(o)}>
                  Löschen
                </button>
              </span>
            </div>
            {art === "beauftragte_kanzlei" && (
              <Anwaelte kanzlei={o} felder={felder} aufruf={aufruf} aufrufMitStand={aufrufMitStand} laeuft={laeuft} />
            )}
          </li>
        ))}
      </ul>
      {loeschfrage && (
        <Rueckfrage
          frage={`„${String(loeschfrage.daten.name ?? "")}“ löschen?`}
          erklaerung={
            "Der Eintrag wird ganz entfernt" +
            (art === "beauftragte_kanzlei" ? ", mit den dort erfassten Anwälten" : "") +
            ". Wird er nur nicht mehr gebraucht, ist Archivieren die bessere Wahl."
          }
          ja="Löschen"
          onJa={() => {
            const o = loeschfrage;
            setLoeschfrage(null);
            void aufruf("eigene.loeschen", { objekt: "organisation", objekt_id: o.id });
          }}
          onNein={() => setLoeschfrage(null)}
        />
      )}
    </section>
  );
}

function Anwaelte({
  kanzlei,
  felder,
  aufruf,
  aufrufMitStand,
  laeuft,
}: {
  kanzlei: EigeneOrganisation;
  felder: EigeneFelder;
  aufruf: Aufruf;
  aufrufMitStand: AufrufMitStand;
  laeuft: boolean;
}) {
  const [bearbeitet, setBearbeitet] = useState<{ id: number | null; daten: Werte } | null>(null);
  const personFelder = felder.felder.person_extern;

  async function speichern(e: FormEvent) {
    e.preventDefault();
    if (!bearbeitet) return;
    const ok = await aufrufMitStand("eigene.person_speichern", {
      organisation_id: kanzlei.id,
      daten: bearbeitet.daten,
      person_id: bearbeitet.id,
    });
    if (ok) setBearbeitet(null);
  }

  return (
    <div className="anwaelte">
      <ul>
        {(kanzlei.anwaelte ?? []).map((a) => (
          <li key={a.id}>
            {personName(a.daten)}
            <span className="leise">
              {" "}
              {[a.daten.berufsbezeichnung, Array.isArray(a.daten.fachanwalt) && a.daten.fachanwalt.length
                ? `FA ${a.daten.fachanwalt.join(", ")}`
                : ""]
                .filter(Boolean)
                .join(" · ")}
            </span>{" "}
            <button className="link" onClick={() => setBearbeitet({ id: a.id, daten: startwerte(personFelder, a.daten) })}>
              Bearbeiten
            </button>
            <button className="link gefahr" onClick={() => void aufruf("eigene.loeschen", { objekt: "person", objekt_id: a.id })}>
              Entfernen
            </button>
          </li>
        ))}
      </ul>
      {bearbeitet ? (
        <form className="eintrag-formular" onSubmit={(e) => void speichern(e)}>
          <Formular felder={personFelder} werte={bearbeitet.daten} onAendern={(d) => setBearbeitet({ ...bearbeitet, daten: d })} />
          <div className="aktionen">
            <button type="submit" disabled={laeuft}>
              Speichern
            </button>
            <button type="button" className="zweitrangig" onClick={() => setBearbeitet(null)}>
              Abbrechen
            </button>
          </div>
        </form>
      ) : (
        <button className="link" onClick={() => setBearbeitet({ id: null, daten: startwerte(personFelder, null) })}>
          + Anwalt hinzufügen
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- Formular und Anzeige

export function Formular({
  felder,
  werte,
  onAendern,
}: {
  felder: FeldDef[];
  werte: Werte;
  onAendern: (werte: Werte) => void;
}) {
  const setze = (k: string, w: Werte[string]) => onAendern({ ...werte, [k]: w });
  return (
    <div className="formular-raster">
      {felder.map((f) => {
        const wert = werte[f.schluessel];
        const titel = (
          <span className="feld-titel">
            {f.titel}
            {f.pflicht && <span className="pflicht" title="Pflichtangabe"> *</span>}
          </span>
        );
        const hinweis = f.hinweis && <span className="feld-hinweis">{f.hinweis}</span>;
        if (f.typ === "ja_nein") {
          return (
            <label key={f.schluessel} className="feld feld-ja-nein">
              <span>
                <input type="checkbox" checked={wert === true} onChange={(e) => setze(f.schluessel, e.target.checked)} />{" "}
                {f.titel}
              </span>
              {hinweis}
            </label>
          );
        }
        if (f.typ === "mehrfach") {
          const liste = Array.isArray(wert) ? wert : [];
          const plaetze = f.hoechstens ?? 3;
          return (
            <div key={f.schluessel} className="feld feld-breit">
              {titel}
              <div className="mehrfach">
                {Array.from({ length: plaetze }, (_, i) => {
                  const frei = (f.optionen ?? []).filter((o) => o === liste[i] || !liste.includes(o));
                  const waehle = (w: string) => {
                    const neu = [...liste];
                    neu[i] = w;
                    setze(f.schluessel, neu.filter(Boolean));
                  };
                  return frei.length >= SUCHE_AB ? (
                    <SuchAuswahl
                      key={i}
                      bezeichnung={`${f.titel} ${i + 1}`}
                      optionen={frei}
                      wert={liste[i] ?? ""}
                      onWahl={waehle}
                    />
                  ) : (
                    <select key={i} aria-label={`${f.titel} ${i + 1}`} value={liste[i] ?? ""} onChange={(e) => waehle(e.target.value)}>
                      <option value="">–</option>
                      {frei.map((o) => (
                        <option key={o} value={o}>
                          {o}
                        </option>
                      ))}
                    </select>
                  );
                })}
              </div>
              {hinweis}
            </div>
          );
        }
        const text = typeof wert === "string" ? wert : "";
        // Lange Listen (etwa die Rechtsanwaltskammern) mit Suchfeld; kein <label> drumherum, sonst löst jeder Klick in
        // die offene Liste zusätzlich den Knopf aus.
        if (f.typ === "auswahl" && (f.optionen ?? []).length >= SUCHE_AB) {
          return (
            <div key={f.schluessel} className="feld">
              {titel}
              <SuchAuswahl
                bezeichnung={f.titel}
                optionen={f.optionen ?? []}
                wert={text}
                onWahl={(w) => setze(f.schluessel, w)}
              />
              {hinweis}
            </div>
          );
        }
        return (
          <label key={f.schluessel} className={f.typ === "mehrzeilig" ? "feld feld-breit" : "feld"}>
            {titel}
            {f.typ === "auswahl" ? (
              <select value={text} onChange={(e) => setze(f.schluessel, e.target.value)}>
                <option value="">–</option>
                {(f.optionen ?? []).map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ) : f.typ === "mehrzeilig" ? (
              <textarea rows={3} value={text} onChange={(e) => setze(f.schluessel, e.target.value)} />
            ) : (
              <input
                type={f.typ === "datum" ? "date" : f.typ === "text" ? "text" : f.typ}
                value={text}
                onChange={(e) => setze(f.schluessel, e.target.value)}
                spellCheck={f.typ === "text"}
              />
            )}
            {hinweis}
          </label>
        );
      })}
    </div>
  );
}

function Anzeige({ felder, werte }: { felder: FeldDef[]; werte: Werte | undefined }) {
  const zeilen = felder.map((f) => [f, feldText(f, werte?.[f.schluessel])] as const).filter(([, t]) => t);
  if (zeilen.length === 0) return <p className="leer">Noch keine Angaben.</p>;
  return (
    <dl className="anzeige">
      {zeilen.map(([f, t]) => (
        <div key={f.schluessel}>
          <dt>{f.titel}</dt>
          <dd>{t}</dd>
        </div>
      ))}
    </dl>
  );
}
