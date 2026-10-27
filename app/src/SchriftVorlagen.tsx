import { useEffect, useState } from "react";
import { open, save } from "@tauri-apps/plugin-dialog";
import { Rueckfrage } from "./Akte";
import { PlatzhalterEintrag, SchriftVorlage, SchriftVorlagen, kern } from "./kern";

/**
 * Einstellungen → Schriftstücke: eigene Word-Vorlagen der Arbeitsumgebung, Grundvorlagen als Ausgangspunkt und die
 * Liste aller Platzhalter. Erzeugt werden die Schriftstücke im Reiter „Schriftstücke“ einer Akte.
 */
export default function SchriftVorlagenEinstellungen() {
  const [vorlagen, setVorlagen] = useState<SchriftVorlagen | null>(null);
  const [katalog, setKatalog] = useState<PlatzhalterEintrag[]>([]);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [entfernen, setEntfernen] = useState<SchriftVorlage | null>(null);

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
      const [v, k] = await Promise.all([
        kern<SchriftVorlagen>("schriftstuecke.vorlagen"),
        kern<PlatzhalterEintrag[]>("schriftstuecke.katalog"),
      ]);
      setVorlagen(v);
      setKatalog(k);
    });
  }, []);

  async function hinzufuegen() {
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
      setMeldung(`Gespeichert unter ${r.pfad}. In Word anpassen, speichern und dann über „Vorlage hinzufügen …“ aufnehmen.`);
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
    if (r) setVorlagen(r);
  }

  async function kopieren(p: string) {
    try {
      await navigator.clipboard.writeText(`{{${p}}}`);
      setMeldung(`{{${p}}} kopiert. In Word an der gewünschten Stelle einfügen.`);
    } catch {
      setMeldung(`Bitte von Hand kopieren: {{${p}}}`);
    }
  }

  const gruppen = [...new Set(katalog.map((k) => k.gruppe))];

  return (
    <div className="schriftstuecke">
      <section className="karte schrift-vorlagen">
        <h2>Eigene Vorlagen</h2>
        <p className="leise">
          Eigene Vorlagen gelten für alle Akten dieser Arbeitsumgebung und stehen im Reiter „Schriftstücke“ jeder Akte zur
          Wahl. JuraBox legt eine Kopie ab; deine Datei bleibt, wo sie ist.
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
        {vorlagen && vorlagen.eigene.length === 0 && <p className="leise">Noch keine eigene Vorlage.</p>}
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
          <button disabled={laeuft} onClick={hinzufuegen}>
            Vorlage hinzufügen …
          </button>
          <button className="zweitrangig" disabled={laeuft} onClick={() => mit(() => kern("schriftstuecke.vorlagen_ordner"))}>
            Vorlagenordner zeigen
          </button>
        </div>
        {meldung && <p className="status">{meldung}</p>}
        {fehler && <p className="fehler">{fehler}</p>}
      </section>

      <section className="karte">
        <h2>So entsteht eine eigene Vorlage</h2>
        <ol className="schrift-anleitung">
          <li>
            Am einfachsten eine Grundvorlage als Ausgangspunkt speichern. Sie enthält Briefkopf, Anschriftfeld nach DIN 5008
            und alle Platzhalter:
            <div className="aktionen">
              {vorlagen?.grund.map((v) => (
                <button key={v.id} className="zweitrangig" disabled={laeuft} onClick={() => grundvorlageSpeichern(v)}>
                  „{v.titel}“ speichern …
                </button>
              ))}
            </div>
          </li>
          <li>
            Die Datei in Word anpassen, z. B. Schrift, Briefbogen, Fußzeile oder feste Textbausteine. Oder du nimmst einen
            vorhandenen Briefbogen der Kanzlei (.docx oder .dotx).
          </li>
          <li>
            An die Stellen, die JuraBox füllen soll, Platzhalter in doppelten geschweiften Klammern schreiben, z. B.{" "}
            <code>{"{{Mandant.Name}}"}</code> oder <code>{"{{Gericht.Aktenzeichen}}"}</code>. Die Liste unten kopiert sie per
            Klick. Der Platzhalter übernimmt die Formatierung, die er in Word hat (fett, Schriftgröße).
          </li>
          <li>
            Speichern und hier mit „Vorlage hinzufügen …“ aufnehmen. JuraBox meldet, welche Platzhalter es gefunden hat und
            welche es nicht kennt. Unbekannte bleiben im Schriftstück stehen, damit ein Tippfehler auffällt.
          </li>
          <li>Später ändern: „In Word bearbeiten“ und speichern; das nächste Schriftstück nimmt die neue Fassung.</li>
        </ol>
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
