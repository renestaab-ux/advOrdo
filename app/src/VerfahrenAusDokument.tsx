import { open } from "@tauri-apps/plugin-dialog";
import { useEffect, useState } from "react";
import { Fund } from "./AusDokument";
import { AktenDokument, AktenOptionen, INSTANZ_VORGABE, RubrumVorschau, Verfahren, datumLang, kern } from "./kern";

const SEITE_TEXT = { aktiv: "Klägerseite", passiv: "Beklagtenseite" } as const;
// Welche bisherigen Verfahren mit dem neuen in der Regel enden (Vorauswahl „abschließen“, frei änderbar).
const VORGAENGER: Record<string, string[]> = {
  klage: ["mahnverfahren", "aussergerichtlich"],
  berufung: ["klage"],
  revision: ["berufung"],
  vollstreckung: ["klage", "berufung", "revision", "mahnverfahren"],
};

type Quelle = { pfad: string } | { dokument_id: number };

interface ParteiWahl {
  uebernehmen: boolean;
  beteiligter_id: string;
  bev_uebernehmen: boolean;
  bev_id: string;
}

const vorhanden = (t: { id: number; stufe: string }[]) => String(t.find((x) => x.stufe === "gleich")?.id ?? "");

/**
 * Weiteres Verfahren aus einem Dokument übernehmen (z. B. das Klageverfahren nach dem Mahnverfahren): erst das Dokument
 * wählen, neu von der Festplatte oder aus der Akte, dann die Erkennung prüfen. Übernommen wird erst mit „Verfahren
 * übernehmen“; ein neues Dokument wird dabei in die Akte eingelesen.
 */
export default function VerfahrenAusDokument({
  akteId,
  onFertig,
  onAbbrechen,
}: {
  akteId: number;
  onFertig: (liste: Verfahren[]) => void;
  onAbbrechen: () => void;
}) {
  const [dokumente, setDokumente] = useState<AktenDokument[] | null>(null);
  const [dokumentId, setDokumentId] = useState("");
  const [geladen, setGeladen] = useState<{ quelle: Quelle; vorschau: RubrumVorschau } | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    void kern<AktenDokument[]>("akten.dokumente", { akte_id: akteId }).then((l) => {
      // Neueste zuerst: das Dokument zum neuen Verfahren ist meist eines der letzten.
      const sortiert = [...l].sort((a, b) => (b.datum ?? b.importiert_am).localeCompare(a.datum ?? a.importiert_am));
      setDokumente(sortiert);
      setDokumentId(sortiert[0] ? String(sortiert[0].id) : "");
    }, (e) => setFehler(String(e)));
  }, [akteId]);

  async function erkennen(quelle: Quelle) {
    setLaeuft(true);
    setFehler(null);
    try {
      setGeladen({ quelle, vorschau: await kern<RubrumVorschau>("akten.rubrum_lesen", { ...quelle, akte_id: akteId }) });
    } catch (e) {
      setFehler(String(e));
    } finally {
      setLaeuft(false);
    }
  }

  async function dateiWaehlen() {
    const pfad = await open({
      title: "Dokument zum neuen Verfahren wählen (Abgabenachricht, Klage, Verfügung …)",
      multiple: false,
      directory: false,
      filters: [{ name: "Dokumente", extensions: ["pdf", "docx", "txt", "md"] }],
    });
    if (typeof pfad === "string") await erkennen({ pfad });
  }

  if (geladen) {
    return (
      <Pruefansicht
        key={JSON.stringify(geladen.quelle)}
        akteId={akteId}
        quelle={geladen.quelle}
        vorschau={geladen.vorschau}
        onFertig={onFertig}
        onZurueck={() => setGeladen(null)}
        onAbbrechen={onAbbrechen}
      />
    );
  }

  return (
    <div className="verfahren-aus-dokument">
      <h3>Verfahren aus Dokument übernehmen</h3>
      <p className="erklaerung">
        JuraBox liest Gericht, Aktenzeichen und Parteien aus dem Dokument und zeigt sie mit Fundstelle zur Prüfung.
      </p>
      <div className="quelle-wahl">
        <label className="feld">
          Dokument aus der Akte
          <select value={dokumentId} onChange={(e) => setDokumentId(e.target.value)} disabled={!dokumente?.length}>
            {dokumente?.length === 0 && <option value="">(noch keine Dokumente)</option>}
            {dokumente?.map((d) => (
              <option key={d.id} value={d.id}>
                {d.datum ? `${datumLang(d.datum)} · ` : ""}
                {d.dateiname}
              </option>
            ))}
          </select>
        </label>
        <button onClick={() => erkennen({ dokument_id: Number(dokumentId) })} disabled={laeuft || !dokumentId}>
          Erkennen
        </button>
        <span className="leise">oder</span>
        <button className="zweitrangig" onClick={dateiWaehlen} disabled={laeuft}>
          Neues Dokument wählen …
        </button>
      </div>
      {laeuft && <p className="leise">Dokument wird gelesen …</p>}
      <span className="aktionen">
        <button className="zweitrangig" onClick={onAbbrechen} disabled={laeuft}>
          Abbrechen
        </button>
      </span>
      {fehler && <p className="fehler">{fehler}</p>}
    </div>
  );
}

function Pruefansicht({
  akteId,
  quelle,
  vorschau,
  onFertig,
  onZurueck,
  onAbbrechen,
}: {
  akteId: number;
  quelle: Quelle;
  vorschau: RubrumVorschau;
  onFertig: (liste: Verfahren[]) => void;
  onZurueck: () => void;
  onAbbrechen: () => void;
}) {
  const v = vorschau;
  const neuesDokument = "pfad" in quelle;
  const [optionen, setOptionen] = useState<AktenOptionen | null>(null);
  const [seite, setSeite] = useState<"aktiv" | "passiv" | "">(v.eigene_seite?.wert ?? "");
  const [art, setArt] = useState(v.verfahren_art || "klage");
  const [instanz, setInstanz] = useState(INSTANZ_VORGABE[v.verfahren_art || "klage"] ?? "");
  const [gericht, setGericht] = useState(v.gericht?.name ?? "");
  const anschrift = v.gericht?.anschrift;
  const [spruchkoerper, setSpruchkoerper] = useState(v.gericht?.spruchkoerper ?? "");
  const [gerichtAz, setGerichtAz] = useState(v.aktenzeichen?.wert ?? "");
  const [beginn, setBeginn] = useState("");
  const [ergaenzen, setErgaenzen] = useState(!!v.verfahren_vorhanden);
  const laufende = (v.laufende_verfahren ?? []).filter((x) => !(ergaenzen && x.id === v.verfahren_vorhanden?.id));
  const [abschliessen, setAbschliessen] = useState<number[]>(
    laufende.filter((x) => (VORGAENGER[v.verfahren_art] ?? []).includes(x.art)).map((x) => x.id),
  );
  const [wahl, setWahl] = useState<ParteiWahl[]>(
    v.parteien.map((p) => ({
      uebernehmen: !p.in_akte,
      beteiligter_id: vorhanden(p.treffer),
      bev_uebernehmen: !!p.bevollmaechtigte && !p.bevollmaechtigte.eigene && !p.bevollmaechtigte.in_akte,
      bev_id: vorhanden(p.bevollmaechtigte?.treffer ?? []),
    })),
  );
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    void kern<AktenOptionen>("akten.optionen").then(setOptionen, () => undefined);
  }, []);

  const setzeWahl = (i: number, teil: Partial<ParteiWahl>) => setWahl((alt) => alt.map((w, j) => (j === i ? { ...w, ...teil } : w)));
  const neueParteien = v.parteien.some((p, i) => !p.in_akte && wahl[i].uebernehmen);
  const neueBev = v.parteien.some((p, i) => p.bevollmaechtigte && wahl[i].bev_uebernehmen && p.seite !== seite);
  const seiteFehlt = (neueParteien || neueBev) && !seite;

  async function uebernehmen() {
    setLaeuft(true);
    setFehler(null);
    const auswahl = {
      eigene_seite: seite,
      parteien: v.parteien.map((p, i) => ({
        seite: p.seite,
        art: p.art,
        daten: p.daten,
        vertreter: p.vertreter,
        in_akte: p.in_akte ?? null,
        uebernehmen: !p.in_akte && wahl[i].uebernehmen,
        beteiligter_id: wahl[i].beteiligter_id ? Number(wahl[i].beteiligter_id) : null,
        eigene_organisation_id: p.eigene_organisation_id,
        bevollmaechtigte: p.bevollmaechtigte && {
          daten: p.bevollmaechtigte.daten,
          zeichen: p.bevollmaechtigte.zeichen,
          in_akte: p.bevollmaechtigte.in_akte ?? null,
          uebernehmen: wahl[i].bev_uebernehmen,
          beteiligter_id: wahl[i].bev_id ? Number(wahl[i].bev_id) : null,
        },
      })),
      verfahren: {
        art,
        instanz,
        gericht,
        spruchkoerper,
        aktenzeichen: gerichtAz,
        beginn,
        // Die Anschrift aus dem Dokument gehört nur zum dort genannten Gericht.
        gericht_anschrift: anschrift && gericht.trim() === v.gericht?.name ? anschrift : null,
      },
      abschliessen: abschliessen.filter((id) => laufende.some((x) => x.id === id)),
      verfahren_id: ergaenzen ? v.verfahren_vorhanden?.id : null,
    };
    try {
      onFertig(
        await kern<Verfahren[]>("akten.verfahren_aus_dokument", {
          akte_id: akteId,
          auswahl,
          pfad: neuesDokument ? quelle.pfad : null,
        }),
      );
    } catch (e) {
      setFehler(String(e));
      setLaeuft(false);
    }
  }

  return (
    <div className="verfahren-aus-dokument">
      <h3>Aus „{v.dateiname}“ erkannt</h3>
      <p className="erklaerung">
        Bitte prüfen. Jede Angabe nennt ihre Fundstelle im Dokument (Maus darüber zeigt den Text). Übernommen wird erst
        mit „{ergaenzen ? "Verfahren ergänzen" : "Verfahren übernehmen"}“{neuesDokument && "; das Dokument wird dabei in die Akte eingelesen"}.
        {v.dokumentart && ` Erkannt als ${v.dokumentart.wert}.`}
      </p>
      {v.lesart === "leer" && <p className="hinweis-text">Das Dokument enthält keinen lesbaren Text (Scan ohne Texterkennung?).</p>}
      {v.verfahren_vorhanden && (
        <fieldset className="abschliessen-wahl">
          <legend>Verfahren mit diesem Aktenzeichen steht schon in der Akte</legend>
          <label>
            <input type="radio" name="ergaenzen" checked={ergaenzen} onChange={() => setErgaenzen(true)} /> „
            {v.verfahren_vorhanden.bezeichnung}“ ergänzen (leere Felder unten lassen Vorhandenes stehen)
          </label>
          <label>
            <input type="radio" name="ergaenzen" checked={!ergaenzen} onChange={() => setErgaenzen(false)} /> Als weiteres
            Verfahren anlegen
          </label>
        </fieldset>
      )}
      {v.hinweise.length > 0 && (
        <ul className="hinweis-liste">
          {v.hinweise.map((h) => (
            <li key={h}>{h}</li>
          ))}
        </ul>
      )}

      <div className="formular-raster">
        <label className="feld">
          Art
          <select
            value={art}
            onChange={(e) => {
              setArt(e.target.value);
              setInstanz(INSTANZ_VORGABE[e.target.value] ?? "");
            }}
          >
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
        <label className="feld">
          Beginn
          <input type="date" value={beginn} onChange={(e) => setBeginn(e.target.value)} />
        </label>
      </div>

      {laufende.length > 0 && (
        <fieldset className="abschliessen-wahl">
          <legend>Bisherige Verfahren</legend>
          {laufende.map((x) => (
            <label key={x.id}>
              <input
                type="checkbox"
                checked={abschliessen.includes(x.id)}
                onChange={(e) => setAbschliessen((alt) => (e.target.checked ? [...alt, x.id] : alt.filter((id) => id !== x.id)))}
              />{" "}
              {x.bezeichnung} als abgeschlossen markieren
            </label>
          ))}
          <small className="leise">Als Ende gilt der Beginn des neuen Verfahrens, wenn du ihn einträgst.</small>
        </fieldset>
      )}

      <h3>Parteien</h3>
      {v.parteien.length === 0 && <p className="leer">Keine Parteien erkannt.</p>}
      {(neueParteien || neueBev || !v.eigene_seite) && v.parteien.length > 0 && (
        <fieldset className="seite-wahl">
          <legend>Wir vertreten</legend>
          {(["aktiv", "passiv"] as const).map((s) => (
            <label key={s} className={seite === s ? "gewaehlt" : undefined}>
              <input type="radio" name="verfahren-seite" checked={seite === s} onChange={() => setSeite(s)} />
              <strong>{SEITE_TEXT[s]}</strong>
            </label>
          ))}
          {v.eigene_seite ? (
            <small className="leise">Vorauswahl: {v.eigene_seite.grund}</small>
          ) : (
            <small className="hinweis-text">Bitte wählen; nötig, damit neue Parteien als Mandant oder Gegner eingetragen werden.</small>
          )}
        </fieldset>
      )}
      <ul className="rubrum-parteien">
        {v.parteien.map((p, i) => {
          const eigen = seite !== "" && p.seite === seite;
          const b = p.bevollmaechtigte;
          return (
            <li key={p.index} className={p.in_akte || wahl[i].uebernehmen ? undefined : "abgewaehlt"}>
              <label className="partei-kopf">
                {p.in_akte ? (
                  <input type="checkbox" checked disabled title="Steht schon in der Akte" />
                ) : (
                  <input type="checkbox" checked={wahl[i].uebernehmen} onChange={(e) => setzeWahl(i, { uebernehmen: e.target.checked })} />
                )}
                <strong>{p.name}</strong>
                <span className={`rolle-marke ${seite === "" ? "" : eigen ? "eigene" : "gegen"}`}>
                  {seite === "" ? SEITE_TEXT[p.seite] : eigen ? "Mandant" : "Gegner"}
                </span>
                <span className="leise">
                  {[p.rolle, p.zusatz].filter(Boolean).join(" ")} · <Fund f={p.fundstelle} abschnitte={v.abschnitte} />
                </span>
              </label>
              <div className="partei-daten leise">
                {p.in_akte ? `Steht schon in der Akte (${p.in_akte.rolle_text}).` : "Neu in dieser Akte."}
              </div>
              {!p.in_akte && p.treffer.length > 0 && wahl[i].uebernehmen && !(eigen && p.eigene_organisation_id) && (
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
                  {b.in_akte ? (
                    <span className="leise">Prozessbevollmächtigte: {b.name} (schon in der Akte)</span>
                  ) : eigen || b.eigene ? (
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

      <span className="aktionen">
        <button onClick={uebernehmen} disabled={laeuft || !art || seiteFehlt}>
          {ergaenzen ? "Verfahren ergänzen" : "Verfahren übernehmen"}
        </button>
        <button className="zweitrangig" onClick={onZurueck} disabled={laeuft}>
          Anderes Dokument
        </button>
        <button className="zweitrangig" onClick={onAbbrechen} disabled={laeuft}>
          Abbrechen
        </button>
        {seiteFehlt && <span className="leise">Bitte zuerst wählen, welche Seite wir vertreten.</span>}
      </span>
      {fehler && <p className="fehler">{fehler}</p>}
    </div>
  );
}
