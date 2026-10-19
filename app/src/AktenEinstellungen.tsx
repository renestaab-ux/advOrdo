import { FormEvent, useEffect, useState } from "react";
import { AktenEinstellungen as Werte, UmgebungsListe, istDesktop, kern } from "./kern";

/** Aktenzeichen (Startnummer, Zusatz) und welche anderen Umgebungen die Kollisionsprüfung durchsucht. */
export default function AktenEinstellungen({ umgebungen }: { umgebungen: UmgebungsListe | null }) {
  const [werte, setWerte] = useState<Werte | null>(null);
  const [vorschlag, setVorschlag] = useState("");
  const [zusatz, setZusatz] = useState("");
  const [nummer, setNummer] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);

  async function laden() {
    const w = await kern<Werte>("akten.einstellungen");
    setWerte(w);
    setZusatz(w.aktenzeichen_zusatz);
    setVorschlag((await kern<{ aktenzeichen: string }>("akten.aktenzeichen_vorschlag")).aktenzeichen);
  }

  useEffect(() => {
    if (istDesktop) void laden().catch((e) => setFehler(String(e)));
  }, [umgebungen?.aktiv]);

  async function setzen(params: Record<string, unknown>, text: string) {
    setFehler(null);
    setMeldung(null);
    try {
      await kern<Werte>("akten.einstellungen_setzen", params);
      await laden();
      setMeldung(text);
    } catch (e) {
      setFehler(String(e));
    }
  }

  async function aktenzeichenSpeichern(e: FormEvent) {
    e.preventDefault();
    const params: Record<string, unknown> = { aktenzeichen_zusatz: zusatz };
    if (nummer.trim()) params.naechste_nummer = Number(nummer);
    await setzen(params, "Gespeichert.");
    setNummer("");
  }

  if (!werte) return null;
  const andere = (umgebungen?.umgebungen ?? []).filter((u) => !u.aktiv);
  return (
    <section className="karte">
      <h2>Akten</h2>
      <form onSubmit={aktenzeichenSpeichern}>
        <p className="erklaerung">
          Aktenzeichen nach dem Schema Nummer/Jahr, z. B. 102/26. Nächstes Aktenzeichen: <strong>{vorschlag}</strong>.
          Wer eine bisherige Zählung fortführt, trägt die nächste Nummer des laufenden Jahres ein.
        </p>
        <div className="formular-raster">
          <label className="feld">
            Nächste Nummer in diesem Jahr
            <input type="number" min={1} value={nummer} onChange={(e) => setNummer(e.target.value)} placeholder="unverändert" />
          </label>
          <label className="feld">
            Zusatz (optional)
            <input value={zusatz} onChange={(e) => setZusatz(e.target.value)} placeholder="z. B. Kürzel RS" maxLength={12} />
            <span className="feld-hinweis">Erscheint hinter dem Jahr: 102/26 RS.</span>
          </label>
        </div>
        <button type="submit" className="zweitrangig">
          Speichern
        </button>
      </form>

      <h3>Kollisionsprüfung</h3>
      <p className="erklaerung">
        Die Prüfung durchsucht alle Akten dieser Umgebung und, nur lesend, die der anderen Umgebungen auf diesem
        Gerät, etwa bei Doppelzulassung als Syndikus und in eigener Kanzlei. Daten werden dabei nicht übernommen.
        Testumgebungen lassen sich ausnehmen.
      </p>
      {andere.length === 0 && <p className="leer">Es gibt keine weiteren Umgebungen.</p>}
      {andere.map((u) => {
        const aus = werte.kollision_ausgenommen.includes(u.id);
        return (
          <label key={u.id} className="schalter-zeile">
            <input
              type="checkbox"
              checked={!aus}
              onChange={() =>
                void setzen(
                  {
                    kollision_ausgenommen: aus
                      ? werte.kollision_ausgenommen.filter((x) => x !== u.id)
                      : [...werte.kollision_ausgenommen, u.id],
                  },
                  aus ? `„${u.name}“ wird wieder durchsucht.` : `„${u.name}“ wird nicht mehr durchsucht.`,
                )
              }
            />
            Umgebung „{u.name}“ durchsuchen
          </label>
        );
      })}
      {meldung && <p className="meldung">{meldung}</p>}
      {fehler && <p className="fehler">{fehler}</p>}
    </section>
  );
}
