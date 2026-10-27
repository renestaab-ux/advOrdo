import { useCallback, useEffect, useMemo, useState } from "react";
import { open, save } from "@tauri-apps/plugin-dialog";
import { Rueckfrage } from "./Akte";
import {
  Beteiligung,
  PlatzhalterEintrag,
  SchriftErgebnis,
  SchriftVorlage,
  SchriftVorlagen,
  SchriftVorschau,
  Verfahren,
  empfaengerVorschlag,
  kern,
} from "./kern";

/**
 * Reiter „Schriftstücke“: Brief oder Schriftsatz aus einer Vorlage erzeugen, gefüllt mit Briefkopf (Eigene Daten),
 * Beteiligten, Verfahren und Rubrum der Akte. Das Ergebnis ist eine Word-Datei; sie kommt als Dokument in die Akte
 * und öffnet sich als Arbeitskopie in der Textverarbeitung. Alles bleibt auf dem Gerät.
 */
export default function Schriftstuecke({
  akteId,
  onGeaendert,
  onDokumente,
}: {
  akteId: number;
  /** Ein Dokument kam in die Akte; Zähler und Dokumentliste neu laden. */
  onGeaendert: () => void;
  onDokumente: () => void;
}) {
  const [vorlagen, setVorlagen] = useState<SchriftVorlagen | null>(null);
  const [katalog, setKatalog] = useState<PlatzhalterEintrag[]>([]);
  const [beteiligte, setBeteiligte] = useState<Beteiligung[]>([]);
  const [verfahren, setVerfahren] = useState<Verfahren[]>([]);
  const [vorlageId, setVorlageId] = useState("grund:brief");
  const [empfaengerId, setEmpfaengerId] = useState<number | null>(null);
  const [verfahrenId, setVerfahrenId] = useState<number | null>(null);
  const [vorschau, setVorschau] = useState<SchriftVorschau | null>(null);
  const [ergebnis, setErgebnis] = useState<(SchriftErgebnis & { geoeffnet: boolean }) | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [entfernen, setEntfernen] = useState<SchriftVorlage | null>(null);

  const alle = useMemo(() => [...(vorlagen?.grund ?? []), ...(vorlagen?.eigene ?? [])], [vorlagen]);
  const vorlage = alle.find((v) => v.id === vorlageId);
  const mitEmpfaenger = vorlage?.platzhalter.some((p) => p.startsWith("Empfänger.")) ?? true;
  const mitVerfahren = vorlage?.platzhalter.some((p) => /^(Gericht|Verfahren|Rubrum)/.test(p)) ?? true;

  async function mit<T>(f: () => Promise<T>): Promise<T | undefined> {
    setFehler(null);
    setLaeuft(true);
    try {
      return await f();
    } catch (e) {
      setFehler(String(e));
      return undefined;
    } finally {
      setLaeuft(false);
    }
  }

  const ladeVorlagen = useCallback(async () => {
    setVorlagen(await kern<SchriftVorlagen>("schriftstuecke.vorlagen"));
  }, []);

  useEffect(() => {
    void mit(async () => {
      const [v, k, s, vf] = await Promise.all([
        kern<SchriftVorlagen>("schriftstuecke.vorlagen"),
        kern<PlatzhalterEintrag[]>("schriftstuecke.katalog"),
        kern<{ beteiligte: Beteiligung[] }>("akten.stammdaten", { akte_id: akteId }),
        kern<Verfahren[]>("akten.verfahren", { akte_id: akteId }),
      ]);
      setVorlagen(v);
      setKatalog(k);
      setBeteiligte(s.beteiligte);
      setVerfahren(vf);
      setVerfahrenId(vf.find((x) => x.aktuell)?.id ?? null);
      setEmpfaengerId(empfaengerVorschlag(s.beteiligte, "brief"));
    });
  }, [akteId]);

  function vorlageWaehlen(id: string) {
    setVorlageId(id);
    setErgebnis(null);
    const v = alle.find((x) => x.id === id);
    if (v) setEmpfaengerId(empfaengerVorschlag(beteiligte, v.art));
  }

  // Vorschau der Werte, sobald Vorlage, Empfänger oder Verfahren wechseln.
  useEffect(() => {
    if (!vorlage) return;
    let aktuell = true;
    kern<SchriftVorschau>("schriftstuecke.vorschau", {
      akte_id: akteId,
      vorlage: vorlage.id,
      empfaenger_id: empfaengerId,
      verfahren_id: verfahrenId,
    }).then(
      (v) => aktuell && setVorschau(v),
      (e) => aktuell && setFehler(String(e)),
    );
    return () => {
      aktuell = false;
    };
  }, [akteId, vorlage, empfaengerId, verfahrenId]);

  const params = { akte_id: akteId, vorlage: vorlageId, empfaenger_id: empfaengerId, verfahren_id: verfahrenId };

  async function inDieAkte() {
    setMeldung(null);
    const r = await mit(async () => {
      const e = await kern<SchriftErgebnis>("schriftstuecke.erzeugen", params);
      let geoeffnet = false;
      if (e.dokument_id) {
        await kern("akten.extern_bearbeiten", { dokument_id: e.dokument_id });
        geoeffnet = true;
      }
      return { ...e, geoeffnet };
    });
    if (!r) return;
    setErgebnis(r);
    onGeaendert();
  }

  async function alsDatei() {
    setMeldung(null);
    const vorschlag = await mit(() => kern<SchriftErgebnis>("schriftstuecke.erzeugen", { ...params, in_akte: false }));
    if (!vorschlag) return;
    const ziel = await save({
      title: "Schriftstück speichern",
      defaultPath: vorschlag.dateiname,
      filters: [{ name: "Word", extensions: ["docx"] }],
    });
    if (!ziel) return;
    const r = await mit(() => kern<SchriftErgebnis>("schriftstuecke.erzeugen", { ...params, in_akte: false, pfad: ziel }));
    if (r) setErgebnis({ ...r, geoeffnet: false });
  }

  async function vorlageHinzufuegen() {
    const pfad = await open({
      title: "Eigene Vorlage hinzufügen",
      filters: [{ name: "Word-Vorlage", extensions: ["docx", "dotx"] }],
    });
    if (typeof pfad !== "string") return;
    const r = await mit(() =>
      kern<SchriftVorlagen & { neu: string; pruefung: { platzhalter: string[]; unbekannt: string[] } }>(
        "schriftstuecke.vorlage_hinzufuegen",
        { pfad },
      ),
    );
    if (!r) return;
    setVorlagen(r);
    setVorlageId(`eigen:${r.neu}`);
    const n = r.pruefung.platzhalter.length;
    setMeldung(
      `Vorlage „${r.neu}“ hinzugefügt, ${n === 1 ? "1 Platzhalter" : `${n} Platzhalter`} gefunden.` +
        (r.pruefung.unbekannt.length ? ` Unbekannt: ${r.pruefung.unbekannt.join(", ")}.` : ""),
    );
  }

  async function grundvorlageSpeichern(v: SchriftVorlage) {
    const ziel = await save({
      title: "Grundvorlage als Ausgangspunkt speichern",
      defaultPath: `Vorlage ${v.titel}.docx`,
      filters: [{ name: "Word", extensions: ["docx"] }],
    });
    if (!ziel) return;
    const r = await mit(() => kern<{ pfad: string }>("schriftstuecke.grundvorlage_speichern", { vorlage: v.id, pfad: ziel }));
    if (r)
      setMeldung(
        `Gespeichert unter ${r.pfad}. In Word anpassen und dann über „Vorlage hinzufügen …“ als eigene Vorlage aufnehmen.`,
      );
  }

  async function bearbeiten(v: SchriftVorlage) {
    const r = await mit(() => kern<{ programm: string }>("schriftstuecke.vorlage_bearbeiten", { datei: v.datei }));
    if (r) setMeldung(`Vorlage an ${r.programm} übergeben. Nach dem Speichern in Word gilt die geänderte Fassung.`);
  }

  async function entfernenBestaetigt() {
    const v = entfernen;
    setEntfernen(null);
    if (!v) return;
    const r = await mit(() => kern<SchriftVorlagen>("schriftstuecke.vorlage_entfernen", { datei: v.datei }));
    if (!r) return;
    setVorlagen(r);
    if (vorlageId === v.id) setVorlageId("grund:brief");
  }

  async function kopieren(p: string) {
    try {
      await navigator.clipboard.writeText(`{{${p}}}`);
      setMeldung(`{{${p}}} kopiert. In Word an der gewünschten Stelle einfügen.`);
    } catch {
      setMeldung(`Bitte von Hand kopieren: {{${p}}}`);
    }
  }

  const name = (b: Beteiligung) => `${b.rolle_text}: ${b.name}`;
  // Ohne Ort zum Nachtragen sind es Angaben, die oft zu Recht fehlen (z. B. keine Abteilung in einer Kanzlei).
  const leer = vorschau?.zeilen.filter((z) => z.bekannt && !z.wert && z.wo) ?? [];
  const gruppen = [...new Set(katalog.map((k) => k.gruppe))];

  return (
    <div className="schriftstuecke">
      <section className="karte schrift-neu">
        <h2>Neues Schriftstück</h2>
        <div className="schrift-wahl">
          <label className="feld">
            Vorlage
            <select value={vorlageId} onChange={(e) => vorlageWaehlen(e.target.value)}>
              <optgroup label="Grundvorlagen">
                {vorlagen?.grund.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.titel}
                  </option>
                ))}
              </optgroup>
              {!!vorlagen?.eigene.length && (
                <optgroup label="Eigene Vorlagen">
                  {vorlagen.eigene.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.titel}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
          </label>
          {mitEmpfaenger && (
            <label className="feld">
              Empfänger
              <select
                value={empfaengerId ?? ""}
                onChange={(e) => setEmpfaengerId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">– ohne –</option>
                {beteiligte.map((b) => (
                  <option key={b.id} value={b.id}>
                    {name(b)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {mitVerfahren && verfahren.length > 1 && (
            <label className="feld">
              Verfahren
              <select
                value={verfahrenId ?? ""}
                onChange={(e) => setVerfahrenId(e.target.value ? Number(e.target.value) : null)}
              >
                {verfahren.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.bezeichnung}
                    {v.aktuell ? " (aktuell)" : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        {vorlage?.beschreibung && <p className="leise">{vorlage.beschreibung}</p>}
        {vorlage?.unbekannt.length ? (
          <p className="hinweis">
            Unbekannte Platzhalter bleiben im Schriftstück stehen: {vorlage.unbekannt.map((p) => `{{${p}}}`).join(", ")}
          </p>
        ) : null}
        {vorschau?.hinweise.map((h) => (
          <p key={h} className="hinweis">
            {h}
          </p>
        ))}
        {leer.length > 0 && (
          <p className="hinweis">
            Noch leer: {leer.map((z) => z.platzhalter).join(", ")}. Nachtragen unter{" "}
            {[...new Set(leer.map((z) => z.wo).filter(Boolean))].join("; ")}, oder später in Word ergänzen.
          </p>
        )}
        <div className="aktionen">
          <button disabled={laeuft || !vorlage} onClick={inDieAkte}>
            In die Akte und in Word öffnen
          </button>
          <button className="zweitrangig" disabled={laeuft || !vorlage} onClick={alsDatei}>
            Nur als Datei speichern …
          </button>
        </div>
        {ergebnis && (
          <div className="status schrift-ergebnis">
            {ergebnis.dokument_id ? (
              <>
                „{ergebnis.dateiname}“ {ergebnis.neu ? "liegt jetzt" : "lag schon"} unter Dokumente
                {ergebnis.geoeffnet && " und ist als Arbeitskopie geöffnet. Nach dem Speichern in Word fragt JuraBox, ob die Änderungen als neue Fassung übernommen werden"}
                .{" "}
                <button className="link" onClick={onDokumente}>
                  Zu den Dokumenten
                </button>
              </>
            ) : (
              <>Gespeichert unter {ergebnis.pfad}.</>
            )}
          </div>
        )}
        {meldung && <p className="status">{meldung}</p>}
        {fehler && <p className="fehler">{fehler}</p>}
        {vorschau && vorschau.zeilen.length > 0 && (
          <details className="schrift-vorschau">
            <summary>Was eingesetzt wird ({vorschau.zeilen.length} Platzhalter)</summary>
            <table>
              <tbody>
                {vorschau.zeilen.map((z) => (
                  <tr key={z.platzhalter} className={!z.wert && z.wo ? "leer" : undefined}>
                    <th>{`{{${z.platzhalter}}}`}</th>
                    <td>
                      {!z.bekannt ? (
                        <span className="fehler">unbekannt, bleibt stehen</span>
                      ) : z.wert ? (
                        z.wert.replace(/\t/g, " ")
                      ) : (
                        <span className="leise">{z.wo ? `fehlt (${z.wo})` : "leer"}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
      </section>

      <section className="karte schrift-vorlagen">
        <h2>Vorlagen</h2>
        <p className="leise">
          Eigene Vorlagen sind Word-Dateien mit Platzhaltern wie {"{{Mandant.Name}}"}. Sie gelten für alle Akten dieser
          Arbeitsumgebung. JuraBox legt eine Kopie ab; deine Datei bleibt, wo sie ist.
        </p>
        {vorlagen?.logo_hinweis && <p className="hinweis">{vorlagen.logo_hinweis}</p>}
        {entfernen && (
          <Rueckfrage
            frage={`Vorlage „${entfernen.titel}“ entfernen?`}
            erklaerung="Entfernt wird die Kopie in JuraBox. Schriftstücke, die schon erzeugt sind, bleiben in den Akten."
            ja="Entfernen"
            onJa={entfernenBestaetigt}
            onNein={() => setEntfernen(null)}
          />
        )}
        {vorlagen && vorlagen.eigene.length > 0 && (
          <ul className="schrift-liste">
            {vorlagen.eigene.map((v) => (
              <li key={v.id}>
                <div>
                  <strong>{v.titel}</strong>{" "}
                  <span className="leise">
                    {v.fehler ?? `${v.platzhalter.length} Platzhalter`}
                    {v.unbekannt.length > 0 && `, davon unbekannt: ${v.unbekannt.join(", ")}`}
                  </span>
                </div>
                <div className="aktionen">
                  <button className="zweitrangig" disabled={laeuft} onClick={() => bearbeiten(v)}>
                    In Word bearbeiten
                  </button>
                  <button className="zweitrangig gefahr" disabled={laeuft} onClick={() => setEntfernen(v)}>
                    Entfernen
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
        <div className="aktionen">
          <button className="zweitrangig" disabled={laeuft} onClick={vorlageHinzufuegen}>
            Vorlage hinzufügen …
          </button>
          {vorlagen?.grund.map((v) => (
            <button key={v.id} className="zweitrangig" disabled={laeuft} onClick={() => grundvorlageSpeichern(v)}>
              „{v.titel}“ als Ausgangspunkt speichern …
            </button>
          ))}
          <button className="zweitrangig" disabled={laeuft} onClick={() => mit(() => kern("schriftstuecke.vorlagen_ordner")).then(ladeVorlagen)}>
            Vorlagenordner zeigen
          </button>
        </div>
        <details className="schrift-katalog">
          <summary>Alle Platzhalter ({katalog.length})</summary>
          <p className="leise">
            Groß- und Kleinschreibung spielen keine Rolle, „Empfänger“ und „Empfaenger“ gelten gleich. Mehrzeilige Werte
            (Anschriften, Rubrum) stehen als Zeilen im selben Absatz.
          </p>
          {gruppen.map((g) => (
            <div key={g} className="schrift-gruppe">
              <h3>{g}</h3>
              <table>
                <tbody>
                  {katalog
                    .filter((k) => k.gruppe === g)
                    .map((k) => (
                      <tr key={k.platzhalter}>
                        <th>
                          <button className="link" title="Kopieren" onClick={() => kopieren(k.platzhalter)}>
                            {`{{${k.platzhalter}}}`}
                          </button>
                        </th>
                        <td>{k.bedeutung}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ))}
        </details>
      </section>
    </div>
  );
}
