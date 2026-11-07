import { useEffect, useMemo, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import {
  Beteiligung,
  SchriftErgebnis,
  SchriftVorlagen,
  SchriftVorschau,
  Verfahren,
  empfaengerVorschlag,
  kern,
} from "./kern";
import Kostennote from "./Kostennote";

/**
 * Reiter „Schriftstücke“: Brief oder Schriftsatz aus einer Vorlage erzeugen, gefüllt mit Briefkopf (Eigene Daten),
 * Beteiligten, Verfahren und Rubrum der Akte. Das Ergebnis ist eine Word-Datei; sie kommt als Dokument in die Akte
 * und öffnet sich als Arbeitskopie in der Textverarbeitung. Alles bleibt auf dem Gerät. Eigene Vorlagen verwaltet
 * Einstellungen → Schriftstücke.
 */
export default function Schriftstuecke({
  akteId,
  onGeaendert,
  onDokumente,
  onVorlagen,
  onEigeneDaten,
}: {
  akteId: number;
  /** Ein Dokument kam in die Akte; Zähler und Dokumentliste neu laden. */
  onGeaendert: () => void;
  onDokumente: () => void;
  /** Zu Einstellungen → Schriftstücke (eigene Vorlagen). */
  onVorlagen: () => void;
  /** Zu Eigene Daten (Steuernummer, Bankverbindung, Rechnungsnummer). */
  onEigeneDaten: () => void;
}) {
  const [vorlagen, setVorlagen] = useState<SchriftVorlagen | null>(null);
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

  useEffect(() => {
    void mit(async () => {
      const [v, s, vf] = await Promise.all([
        kern<SchriftVorlagen>("schriftstuecke.vorlagen"),
        kern<{ beteiligte: Beteiligung[] }>("akten.stammdaten", { akte_id: akteId }),
        kern<Verfahren[]>("akten.verfahren", { akte_id: akteId }),
      ]);
      setVorlagen(v);
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

  const name = (b: Beteiligung) => `${b.rolle_text}: ${b.name}`;
  // Ohne Ort zum Nachtragen sind es Angaben, die oft zu Recht fehlen (z. B. keine Abteilung in einer Kanzlei).
  const leer = vorschau?.zeilen.filter((z) => z.bekannt && !z.wert && z.wo) ?? [];

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
        {meldung && <p className="status" role="status">{meldung}</p>}
        {fehler && <p className="fehler" role="alert">{fehler}</p>}
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

      <Kostennote
        akteId={akteId}
        beteiligte={beteiligte}
        hatVerfahren={verfahren.length > 0}
        onGeaendert={onGeaendert}
        onDokumente={onDokumente}
        onEigeneDaten={onEigeneDaten}
      />

      <section className="karte schrift-hinweis">
        <h2>Eigene Vorlagen</h2>
        <p>
          Neben den Grundvorlagen kannst du eigene Word-Vorlagen verwenden, z. B. den Briefbogen der Kanzlei oder ein
          Muster für Vollmacht oder Deckungsanfrage. Dazu eine Grundvorlage als Ausgangspunkt speichern oder eine
          vorhandene Datei nehmen, in Word Platzhalter wie {"{{Mandant.Name}}"} einsetzen und die Datei in den
          Einstellungen hinzufügen. Dort stehen auch die Anleitung und alle Platzhalter zum Kopieren.
          {vorlagen && ` Zurzeit ${vorlagen.eigene.length === 1 ? "1 eigene Vorlage" : `${vorlagen.eigene.length} eigene Vorlagen`}.`}
        </p>
        <div className="aktionen">
          <button className="zweitrangig" onClick={onVorlagen}>
            Vorlagen in den Einstellungen …
          </button>
        </div>
      </section>
    </div>
  );
}
