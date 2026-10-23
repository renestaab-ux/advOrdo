import { useEffect, useState } from "react";
import { Akte, AktenOptionen, Fundstelle, RubrumPartei, RubrumVorschau, kern } from "./kern";

const SEITE_TEXT = { aktiv: "Klägerseite", passiv: "Beklagtenseite" } as const;

interface ParteiWahl {
  uebernehmen: boolean;
  /** "" = neu anlegen, sonst die ID des vorhandenen Eintrags. */
  beteiligter_id: string;
  bev_uebernehmen: boolean;
  bev_id: string;
}

const vorhanden = (t: RubrumPartei["treffer"]) => String(t.find((x) => x.stufe === "gleich")?.id ?? "");

/** Fundstelle als „S. 1, Abschnitt 12“; der Abschnittstext erscheint beim Darüberfahren. */
export function Fund({ f, abschnitte }: { f: Fundstelle | undefined; abschnitte: Record<string, string> }) {
  if (!f) return null;
  return (
    <span className="fund" title={abschnitte[String(f.abschnitt)]}>
      {[f.seite ? `S. ${f.seite}` : null, `Abschnitt ${f.abschnitt}`].filter(Boolean).join(", ")}
    </span>
  );
}

/**
 * Prüfansicht für „Akte aus Dokument“: alles, was JuraBox im Rubrum erkannt hat, mit Fundstelle. Erst „Akte anlegen“
 * übernimmt die Auswahl; das Dokument wird dabei als erstes Dokument der Akte eingelesen.
 */
export default function AusDokument({
  pfad,
  vorschau,
  onAbbrechen,
  onAngelegt,
}: {
  pfad: string;
  vorschau: RubrumVorschau;
  onAbbrechen: () => void;
  onAngelegt: (akteId: number) => Promise<void>;
}) {
  const v = vorschau;
  const [optionen, setOptionen] = useState<AktenOptionen | null>(null);
  const [seite, setSeite] = useState<"aktiv" | "passiv" | "">(v.eigene_seite?.wert ?? "");
  const [name, setName] = useState(v.kurzbezeichnung);
  const [az, setAz] = useState("");
  const [gegenstand, setGegenstand] = useState(v.gegenstand?.wert ?? "");
  const [streitwert, setStreitwert] = useState(v.streitwert?.wert ?? "");
  const [art, setArt] = useState(v.verfahren_art);
  const [instanz, setInstanz] = useState(v.verfahren_art === "klage" ? "1. Instanz" : "");
  const [gericht, setGericht] = useState(v.gericht?.name ?? "");
  const anschrift = v.gericht?.anschrift;
  const [spruchkoerper, setSpruchkoerper] = useState(v.gericht?.spruchkoerper ?? "");
  const [gerichtAz, setGerichtAz] = useState(v.aktenzeichen?.wert ?? "");
  const [wahl, setWahl] = useState<ParteiWahl[]>(
    v.parteien.map((p) => ({
      uebernehmen: true,
      beteiligter_id: vorhanden(p.treffer),
      bev_uebernehmen: !!p.bevollmaechtigte && !p.bevollmaechtigte.eigene,
      bev_id: vorhanden(p.bevollmaechtigte?.treffer ?? []),
    })),
  );
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    void kern<AktenOptionen>("akten.optionen").then(setOptionen, () => undefined);
  }, []);

  const setzeWahl = (i: number, teil: Partial<ParteiWahl>) => setWahl((alt) => alt.map((w, j) => (j === i ? { ...w, ...teil } : w)));
  const seiteNamen = (s: "aktiv" | "passiv") =>
    v.parteien
      .filter((p) => p.seite === s)
      .map((p) => p.name)
      .join(", ") || "nicht erkannt";

  async function anlegen() {
    if (!seite) return;
    setLaeuft(true);
    setFehler(null);
    const auswahl = {
      name: name.trim() || v.dateiname,
      aktenzeichen: az.trim() || null,
      eigene_seite: seite,
      gegenstand,
      gegenstandswert: streitwert,
      parteien: v.parteien.map((p, i) => ({
        seite: p.seite,
        art: p.art,
        daten: p.daten,
        vertreter: p.vertreter,
        uebernehmen: wahl[i].uebernehmen,
        beteiligter_id: wahl[i].beteiligter_id ? Number(wahl[i].beteiligter_id) : null,
        eigene_organisation_id: p.eigene_organisation_id,
        bevollmaechtigte: p.bevollmaechtigte && {
          daten: p.bevollmaechtigte.daten,
          zeichen: p.bevollmaechtigte.zeichen,
          uebernehmen: wahl[i].bev_uebernehmen,
          beteiligter_id: wahl[i].bev_id ? Number(wahl[i].bev_id) : null,
        },
      })),
      verfahren: art
        ? {
            art,
            instanz,
            gericht,
            spruchkoerper,
            aktenzeichen: gerichtAz,
            // Die Anschrift aus dem Dokument gehört nur zum dort genannten Gericht.
            gericht_anschrift: anschrift && gericht.trim() === v.gericht?.name ? anschrift : null,
          }
        : null,
    };
    try {
      const a = await kern<Akte>("akten.aus_dokument_anlegen", { pfad, auswahl });
      await onAngelegt(a.id);
    } catch (e) {
      setFehler(String(e));
      setLaeuft(false);
    }
  }

  return (
    <div className="aus-dokument">
      <section className="karte">
        <h2>Aus „{v.dateiname}“ erkannt</h2>
        <p className="erklaerung">
          Bitte prüfen. Jede Angabe nennt ihre Fundstelle im Dokument (Maus darüber zeigt den Text). Übernommen wird erst
          mit „Akte anlegen“; das Dokument wird dabei als erstes Dokument eingelesen.
          {v.dokumentart && ` Erkannt als ${v.dokumentart.wert}.`}
        </p>
        {v.lesart === "leer" && (
          <p className="hinweis-text">Das Dokument enthält keinen lesbaren Text (Scan ohne Texterkennung?).</p>
        )}
        {v.hinweise.length > 0 && (
          <ul className="hinweis-liste">
            {v.hinweise.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        )}

        <fieldset className="seite-wahl">
          <legend>Wir vertreten</legend>
          {(["aktiv", "passiv"] as const).map((s) => (
            <label key={s} className={seite === s ? "gewaehlt" : undefined}>
              <input type="radio" name="seite" checked={seite === s} onChange={() => setSeite(s)} />
              <span>
                <strong>{SEITE_TEXT[s]}</strong> <span className="leise">({seiteNamen(s)})</span>
              </span>
            </label>
          ))}
          {v.eigene_seite ? (
            <small className="leise">Vorauswahl: {v.eigene_seite.grund}</small>
          ) : (
            <small className="hinweis-text">Bitte wählen; JuraBox konnte es nicht aus „Eigene Daten“ ableiten.</small>
          )}
        </fieldset>

        <div className="formular-raster">
          <label className="feld">
            Kurzbezeichnung
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="feld">
            Aktenzeichen
            <input value={az} onChange={(e) => setAz(e.target.value)} placeholder={`${v.aktenzeichen_vorschlag} (Vorschlag)`} />
          </label>
          <label className="feld">
            <span>
              Gegenstand <Fund f={v.gegenstand?.fundstelle} abschnitte={v.abschnitte} />
            </span>
            <input value={gegenstand} onChange={(e) => setGegenstand(e.target.value)} />
          </label>
          <label className="feld">
            <span>
              {v.streitwert?.art ?? "Streitwert"} in €{" "}
              <Fund f={v.streitwert?.fundstelle} abschnitte={v.abschnitte} />
            </span>
            <input value={streitwert} onChange={(e) => setStreitwert(e.target.value)} inputMode="decimal" className="betrag" />
          </label>
        </div>
      </section>

      <section className="karte">
        <h3>Verfahren</h3>
        <div className="formular-raster">
          <label className="feld">
            Art
            <select value={art} onChange={(e) => setArt(e.target.value)}>
              <option value="">(kein Verfahren eintragen)</option>
              {optionen &&
                Object.entries(optionen.verfahren_arten).map(([k, t]) => (
                  <option key={k} value={k}>
                    {t}
                  </option>
                ))}
            </select>
          </label>
          <label className="feld">
            Instanz
            <select value={instanz} onChange={(e) => setInstanz(e.target.value)}>
              <option value="">–</option>
              {optionen?.instanzen.map((i) => (
                <option key={i}>{i}</option>
              ))}
            </select>
          </label>
          <label className="feld">
            <span>
              Gericht <Fund f={v.gericht?.fundstelle} abschnitte={v.abschnitte} />
            </span>
            <input value={gericht} onChange={(e) => setGericht(e.target.value)} />
            {anschrift && gericht.trim() === v.gericht?.name && (
              <span className="feld-hinweis">
                Anschrift aus dem Dokument: {anschrift.strasse}, {anschrift.plz} {anschrift.ort}
              </span>
            )}
          </label>
          <label className="feld">
            Spruchkörper
            <input value={spruchkoerper} onChange={(e) => setSpruchkoerper(e.target.value)} />
          </label>
          <label className="feld">
            <span>
              Gerichtliches Aktenzeichen <Fund f={v.aktenzeichen?.fundstelle} abschnitte={v.abschnitte} />
            </span>
            <input value={gerichtAz} onChange={(e) => setGerichtAz(e.target.value)} placeholder="noch keins" />
          </label>
        </div>
      </section>

      <section className="karte">
        <h3>Parteien</h3>
        {v.parteien.length === 0 && <p className="leer">Keine Parteien erkannt; sie lassen sich danach unter „Beteiligte“ eintragen.</p>}
        <ul className="rubrum-parteien">
          {v.parteien.map((p, i) => {
            const eigen = seite !== "" && p.seite === seite;
            const b = p.bevollmaechtigte;
            return (
              <li key={p.index} className={wahl[i].uebernehmen ? undefined : "abgewaehlt"}>
                <label className="partei-kopf">
                  <input type="checkbox" checked={wahl[i].uebernehmen} onChange={(e) => setzeWahl(i, { uebernehmen: e.target.checked })} />
                  <strong>{p.name}</strong>
                  <span className={`rolle-marke ${seite === "" ? "" : eigen ? "eigene" : "gegen"}`}>
                    {seite === "" ? SEITE_TEXT[p.seite] : eigen ? "Mandant" : "Gegner"}
                  </span>
                  <span className="leise">
                    {[p.rolle, p.zusatz].filter(Boolean).join(" ")} · <Fund f={p.fundstelle} abschnitte={v.abschnitte} />
                  </span>
                </label>
                <div className="partei-daten leise">
                  {[p.daten.strasse, [p.daten.plz, p.daten.ort].filter(Boolean).join(" ")].filter(Boolean).join(", ") ||
                    "Anschrift nicht erkannt"}
                  {p.vertreter.map((vt) => (
                    <div key={vt.name}>
                      vertreten durch {vt.funktion} {vt.name}
                    </div>
                  ))}
                  {p.hinweise.map((h) => (
                    <div key={h}>{h}</div>
                  ))}
                  {p.eigene_organisation_id && eigen && <div>Konzerngesellschaft aus „Eigene Daten“</div>}
                </div>
                {p.treffer.length > 0 && wahl[i].uebernehmen && !(eigen && p.eigene_organisation_id) && (
                  <label className="treffer-wahl">
                    Im Verzeichnis:{" "}
                    <select value={wahl[i].beteiligter_id} onChange={(e) => setzeWahl(i, { beteiligter_id: e.target.value })}>
                      <option value="">neu anlegen</option>
                      {p.treffer.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name} ({t.stufe === "gleich" ? "gleicher Name" : "ähnlich"})
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {b && (
                  <div className="bevollmaechtigte">
                    {eigen || b.eigene ? (
                      <span className="leise">
                        Prozessbevollmächtigte: {b.name} {eigen ? "(unsere Seite, wird nicht eingetragen)" : "(eigene Kanzlei)"}
                      </span>
                    ) : (
                      <>
                        <label>
                          <input
                            type="checkbox"
                            checked={wahl[i].bev_uebernehmen}
                            onChange={(e) => setzeWahl(i, { bev_uebernehmen: e.target.checked })}
                          />{" "}
                          Prozessbevollmächtigte des Gegners: <strong>{b.name}</strong>
                          {b.zeichen && <span className="leise"> · Zeichen {b.zeichen}</span>}
                        </label>
                        {b.treffer.length > 0 && wahl[i].bev_uebernehmen && (
                          <select value={wahl[i].bev_id} onChange={(e) => setzeWahl(i, { bev_id: e.target.value })} aria-label="Eintrag im Verzeichnis">
                            <option value="">neu anlegen</option>
                            {b.treffer.map((t) => (
                              <option key={t.id} value={t.id}>
                                {t.name} ({t.stufe === "gleich" ? "gleicher Name" : "ähnlich"})
                              </option>
                            ))}
                          </select>
                        )}
                      </>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        <p className="leise klein">
          Nach dem Anlegen läuft die Kollisionsprüfung; das Ergebnis steht unter „Beteiligte“. Fristen und Termine aus dem
          Dokument schlägt der Reiter „Fristen“ vor.
        </p>
      </section>

      <span className="aktionen leiste-unten">
        <button onClick={anlegen} disabled={laeuft || !seite}>
          Akte anlegen
        </button>
        <button className="zweitrangig" onClick={onAbbrechen} disabled={laeuft}>
          Abbrechen
        </button>
        {!seite && <span className="leise">Bitte zuerst wählen, welche Seite wir vertreten.</span>}
        {fehler && <p className="fehler">{fehler}</p>}
      </span>
    </div>
  );
}
