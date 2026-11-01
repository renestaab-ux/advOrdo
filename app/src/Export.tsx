import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { save } from "@tauri-apps/plugin-dialog";
import { Druckansicht, EXPORT_FORMATE, ExportFormat, ExportTeil, KiErgebnisse, drucken, exportTeile, kern } from "./kern";

/**
 * Knöpfe für Word, PDF, Excel, Markdown, Text und Drucken samt Speichern-Dialog und Druckansicht. Wer sie nutzt,
 * liefert den Dateinamen-Vorschlag, das Schreiben (Kern) und die Druckansicht (Kern).
 */
export function AusgabeKnoepfe({
  was,
  gesperrt,
  name,
  schreiben,
  druckansicht,
}: {
  /** Für den Titel des Speichern-Dialogs, z. B. „KI-Auswertung“. */
  was: string;
  gesperrt?: boolean;
  name: () => Promise<string>;
  schreiben: (format: ExportFormat, pfad: string) => Promise<{ pfad: string }>;
  druckansicht: () => Promise<Druckansicht>;
}) {
  const [laeuft, setLaeuft] = useState(false);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [druck, setDruck] = useState<Druckansicht | null>(null);

  // Der Titel der Seite wird beim Drucken als PDF zum Dateinamen; danach den alten wiederherstellen.
  useEffect(() => {
    if (!druck) return;
    const vorher = document.title;
    document.title = druck.titel;
    return () => {
      document.title = vorher;
    };
  }, [druck]);

  async function ausfuehren(f: () => Promise<void>) {
    setFehler(null);
    setMeldung(null);
    setLaeuft(true);
    try {
      await f();
    } catch (e) {
      setFehler(String(e));
    } finally {
      setLaeuft(false);
    }
  }

  const speichern = (format: ExportFormat, titel: string) =>
    ausfuehren(async () => {
      const vorschlag = await name();
      const ziel = await save({
        title: `${was} als ${titel} speichern`,
        defaultPath: `${vorschlag}.${format}`,
        filters: [{ name: titel, extensions: [format] }],
      });
      if (!ziel) return;
      const r = await schreiben(format, ziel);
      setMeldung(`Gespeichert unter ${r.pfad}`);
    });

  const druckenStarten = () =>
    ausfuehren(async () => {
      setDruck(await druckansicht());
      // Erst drucken, wenn die Druckansicht im Dokument steht.
      await new Promise((fertig) => requestAnimationFrame(() => requestAnimationFrame(fertig)));
      await drucken();
    });

  return (
    <>
      <div className="aktionen ki-export-knoepfe">
        {EXPORT_FORMATE.map((f) => (
          <button key={f.id} className="zweitrangig" disabled={laeuft || gesperrt} onClick={() => speichern(f.id, f.titel)}>
            {f.titel} …
          </button>
        ))}
        <button disabled={laeuft || gesperrt} onClick={druckenStarten}>
          Drucken …
        </button>
      </div>
      {meldung && <p className="status" role="status">{meldung}</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
      {druck &&
        createPortal(
          <div id="druckbereich">
            <style>{druck.stil}</style>
            {/* Vom Kern erzeugt; alle Inhalte dort maskiert (juracore/ausgabe/html.py). */}
            <div dangerouslySetInnerHTML={{ __html: druck.html }} />
          </div>,
          document.body,
        )}
    </>
  );
}

/** Gespeicherte KI-Ergebnisse als Word, PDF, Excel, Markdown oder Text speichern oder drucken, jeweils mit Fundstellen. */
export default function KiExport({
  akteId,
  ergebnisse,
  onSchliessen,
}: {
  akteId: number;
  ergebnisse: KiErgebnisse;
  onSchliessen: () => void;
}) {
  const teile = exportTeile(ergebnisse);
  const [gewaehlt, setGewaehlt] = useState<ExportTeil[]>(teile.filter((t) => t.vorhanden).map((t) => t.id));
  const [zitate, setZitate] = useState(true);

  const auswahl = teile.filter((t) => t.vorhanden && gewaehlt.includes(t.id)).map((t) => t.id);
  const params = { akte_id: akteId, teile: auswahl, zitate };

  return (
    <section className="karte ki-export">
      <div className="ki-export-kopf">
        <strong>Ergebnisse ausgeben</strong>
        <button className="zweitrangig" onClick={onSchliessen}>
          Schließen
        </button>
      </div>
      <div className="ki-export-teile">
        {teile.map((t) => (
          <label key={t.id} className={t.vorhanden ? undefined : "leise"} title={t.vorhanden ? undefined : "Noch kein Ergebnis"}>
            <input
              type="checkbox"
              disabled={!t.vorhanden}
              checked={t.vorhanden && gewaehlt.includes(t.id)}
              onChange={(e) => setGewaehlt(e.target.checked ? [...gewaehlt, t.id] : gewaehlt.filter((g) => g !== t.id))}
            />{" "}
            {t.titel}
          </label>
        ))}
      </div>
      <label className="ki-export-zitate">
        <input type="checkbox" checked={zitate} onChange={(e) => setZitate(e.target.checked)} /> Zitate aus den
        Dokumenten mitnehmen <span className="leise">(Fundstellen mit Dokument, Seite und Rn. stehen immer dabei)</span>
      </label>
      <AusgabeKnoepfe
        was="KI-Auswertung"
        gesperrt={auswahl.length === 0}
        name={async () => (await kern<{ name: string }>("ki.export_name", { akte_id: akteId })).name}
        schreiben={(format, pfad) => kern<{ pfad: string }>("ki.export", { ...params, format, pfad })}
        druckansicht={() => kern<Druckansicht>("ki.export_druck", params)}
      />
    </section>
  );
}
