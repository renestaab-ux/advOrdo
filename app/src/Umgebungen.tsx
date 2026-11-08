import { FormEvent, useState } from "react";
import { Rueckfrage } from "./Rueckfrage";
import { Umgebung, UmgebungsListe, kern } from "./kern";

/**
 * Arbeitsumgebungen: getrennte Datenordner je Identität (z. B. Kanzlei, Rechtsabteilung, Test).
 * Akten und KI-Ergebnisse gehören zur Umgebung; Gesetze, Rechtsprechungsverzeichnis und Einstellungen sind gemeinsam.
 */
export default function Umgebungen({
  liste,
  onGeaendert,
}: {
  liste: UmgebungsListe | null;
  onGeaendert: (liste: UmgebungsListe, gewechselt: boolean) => void;
}) {
  const [neu, setNeu] = useState("");
  const [bearbeitet, setBearbeitet] = useState<{ id: string; name: string } | null>(null);
  const [loeschfrage, setLoeschfrage] = useState<Umgebung | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);

  async function ausfuehren(arbeit: () => Promise<UmgebungsListe>, gewechselt = false, text?: string) {
    setLaeuft(true);
    setFehler(null);
    setMeldung(null);
    try {
      const ergebnis = await arbeit();
      onGeaendert(ergebnis, gewechselt);
      if (text) setMeldung(text);
      return true;
    } catch (e) {
      setFehler(String(e));
      return false;
    } finally {
      setLaeuft(false);
    }
  }

  async function anlegen(e: FormEvent) {
    e.preventDefault();
    const name = neu.trim();
    const ok = await ausfuehren(async () => {
      await kern<Umgebung>("umgebungen.anlegen", { name });
      return kern<UmgebungsListe>("umgebungen.liste");
    }, false, `Umgebung „${name}“ angelegt. Mit „Wechseln“ arbeitest du darin.`);
    if (ok) setNeu("");
  }

  async function umbenennen(e: FormEvent) {
    e.preventDefault();
    if (!bearbeitet) return;
    const ok = await ausfuehren(() =>
      kern<UmgebungsListe>("umgebungen.umbenennen", { umgebung_id: bearbeitet.id, name: bearbeitet.name }),
    );
    if (ok) setBearbeitet(null);
  }

  async function loeschen() {
    if (!loeschfrage) return;
    const u = loeschfrage;
    setLoeschfrage(null);
    await ausfuehren(
      () => kern<UmgebungsListe>("umgebungen.loeschen", { umgebung_id: u.id }),
      false,
      `Umgebung „${u.name}“ wurde gelöscht.`,
    );
  }

  const umgebungen = liste?.umgebungen ?? [];

  return (
    <section className="karte">
      <h2>Arbeitsumgebungen</h2>
      <p className="erklaerung">
        Jede Umgebung hat eigene Akten und eigene Analysen, etwa für die Kanzlei, eine Rechtsabteilung oder zum Testen.
        Gesetze, Rechtsprechungsverzeichnis und diese Einstellungen gelten für alle Umgebungen gemeinsam.
      </p>
      <ul className="umgebungen">
        {umgebungen.map((u) => (
          <li key={u.id} className={u.aktiv ? "aktiv" : undefined}>
            {bearbeitet?.id === u.id ? (
              <form className="umgebung-name" onSubmit={umbenennen}>
                <input
                  value={bearbeitet.name}
                  onChange={(e) => setBearbeitet({ id: u.id, name: e.target.value })}
                  maxLength={60}
                  autoFocus
                  aria-label="Neuer Name"
                />
                <button type="submit" disabled={laeuft || !bearbeitet.name.trim()}>
                  Speichern
                </button>
                <button type="button" className="zweitrangig" onClick={() => setBearbeitet(null)}>
                  Abbrechen
                </button>
              </form>
            ) : (
              <>
                <span className="umgebung-titel">
                  {u.name}
                  {u.aktiv && <span className="marke-aktiv">aktiv</span>}
                  {u.standard && <span className="leise"> · bisherige Daten</span>}
                </span>
                <span className="aktionen">
                  {!u.aktiv && (
                    <button
                      disabled={laeuft}
                      onClick={() =>
                        void ausfuehren(
                          () => kern<UmgebungsListe>("umgebungen.wechseln", { umgebung_id: u.id }),
                          true,
                          `Du arbeitest jetzt in „${u.name}“.`,
                        )
                      }
                    >
                      Wechseln
                    </button>
                  )}
                  <button className="zweitrangig" disabled={laeuft} onClick={() => setBearbeitet({ id: u.id, name: u.name })}>
                    Umbenennen
                  </button>
                  {!u.standard && !u.aktiv && (
                    <button className="gefahr" disabled={laeuft} onClick={() => setLoeschfrage(u)}>
                      Löschen
                    </button>
                  )}
                </span>
              </>
            )}
          </li>
        ))}
      </ul>
      <form className="umgebung-neu" onSubmit={anlegen}>
        <input
          value={neu}
          onChange={(e) => setNeu(e.target.value)}
          placeholder="z. B. Test Rechtsabteilung"
          maxLength={60}
          aria-label="Name der neuen Umgebung"
        />
        <button type="submit" disabled={laeuft || !neu.trim()}>
          Neue Umgebung
        </button>
      </form>
      {meldung && <p className="status" role="status">{meldung}</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
      {loeschfrage && (
        <Rueckfrage
          frage={`Umgebung „${loeschfrage.name}“ löschen?`}
          erklaerung={
            "Gelöscht werden alle Akten dieser Umgebung mit ihren Analysen und den Kopien, die die App beim Einlesen " +
            "abgelegt hat. Deine Originaldateien am ursprünglichen Ort, die Gesetze und die anderen Umgebungen " +
            "bleiben unverändert."
          }
          ja="Löschen"
          onJa={() => void loeschen()}
          onNein={() => setLoeschfrage(null)}
        />
      )}
    </section>
  );
}
