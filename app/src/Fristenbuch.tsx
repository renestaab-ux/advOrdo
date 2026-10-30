import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { save } from "@tauri-apps/plugin-dialog";
import { KalenderFilter } from "./kalenderLogik";
import { Druckansicht, EXPORT_FORMATE, datumLang, drucken, kern } from "./kern";

/**
 * Fristenbuch des Zeitraums (mit den Filtern des Kalenders) speichern oder drucken, dazu die Kalenderdatei (.ics)
 * für Outlook, Apple- oder Google-Kalender. Beides schreibt der Kern als Datei; nichts geht über das Netz.
 */
export default function Fristenbuch({
  von: vonStart,
  bis: bisStart,
  filter,
  onSchliessen,
}: {
  von: string;
  bis: string;
  filter: KalenderFilter;
  onSchliessen: () => void;
}) {
  const [von, setVon] = useState(vonStart);
  const [bis, setBis] = useState(bisStart);
  const [laeuft, setLaeuft] = useState(false);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [druck, setDruck] = useState<Druckansicht | null>(null);
  const params = { von, bis, filter };
  const gueltig = !!von && !!bis && von <= bis;

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

  const speichern = (endung: string, titel: string) =>
    ausfuehren(async () => {
      const { name } = await kern<{ name: string }>("kalender.fristenbuch_name", { von, bis });
      const ziel = await save({
        title: endung === "ics" ? "Kalenderdatei speichern" : `Fristenbuch als ${titel} speichern`,
        defaultPath: `${endung === "ics" ? name.replace("Fristenbuch", "JuraBox Kalender") : name}.${endung}`,
        filters: [{ name: titel, extensions: [endung] }],
      });
      if (!ziel) return;
      const r = await kern<{ pfad: string; anzahl?: number }>("kalender.fristenbuch", { ...params, pfad: ziel });
      setMeldung(
        endung === "ics" ? `${r.anzahl ?? 0} Einträge gespeichert unter ${r.pfad}` : `Gespeichert unter ${r.pfad}`,
      );
    });

  const druckenStarten = () =>
    ausfuehren(async () => {
      setDruck(await kern<Druckansicht>("kalender.fristenbuch_druck", params));
      await new Promise((fertig) => requestAnimationFrame(() => requestAnimationFrame(fertig)));
      await drucken();
    });

  return (
    <section className="karte fristenbuch" aria-label="Fristenbuch und Kalenderdatei">
      <div className="vorschlaege-kopf">
        <h3>Fristenbuch und Kalenderdatei</h3>
        <button className="link klein" onClick={onSchliessen}>
          Schließen
        </button>
      </div>
      <div className="fristenbuch-zeitraum">
        <label className="feld">
          Von
          <input type="date" value={von} onChange={(e) => setVon(e.target.value)} />
        </label>
        <label className="feld">
          Bis
          <input type="date" value={bis} onChange={(e) => setBis(e.target.value)} />
        </label>
        <p className="leise klein">
          Es gelten die Filter des Kalenders. Abgelaufene, nicht erledigte Fristen und Wiedervorlagen vor dem{" "}
          {gueltig ? datumLang(von) : "Beginn"} stehen im Fristenbuch immer oben.
        </p>
      </div>
      <div className="aktionen">
        {EXPORT_FORMATE.filter((f) => ["docx", "pdf", "xlsx"].includes(f.id)).map((f) => (
          <button key={f.id} className="zweitrangig" disabled={laeuft || !gueltig} onClick={() => speichern(f.id, f.titel)}>
            {f.titel} …
          </button>
        ))}
        <button disabled={laeuft || !gueltig} onClick={druckenStarten}>
          Drucken …
        </button>
        <button className="zweitrangig" disabled={laeuft || !gueltig} onClick={() => speichern("ics", "Kalenderdatei")}>
          Kalenderdatei (.ics) …
        </button>
      </div>
      <p className="hinweis-text klein">
        Die Kalenderdatei enthält Aktenzeichen, Parteien und Gerichte. Wird sie in einen Online-Kalender (etwa Google,
        iCloud oder Microsoft 365) eingelesen, liegen diese Angaben beim Anbieter. Einen laufenden Abgleich gibt es
        nicht; nach Änderungen die Datei neu speichern und einlesen, die Einträge werden dann aktualisiert.
      </p>
      {meldung && <p className="status">{meldung}</p>}
      {fehler && <p className="fehler">{fehler}</p>}
      {druck &&
        createPortal(
          <div id="druckbereich">
            <style>{druck.stil}</style>
            {/* Vom Kern erzeugt; alle Inhalte dort maskiert (juracore/ausgabe/html.py). */}
            <div dangerouslySetInnerHTML={{ __html: druck.html }} />
          </div>,
          document.body,
        )}
    </section>
  );
}
