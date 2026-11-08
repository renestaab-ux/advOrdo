import { FormEvent, useEffect, useState } from "react";
import { AktenEinstellungen as Werte, UmgebungsListe, istDesktop, kern } from "./kern";
import { ERINNERUNGEN_AUS, testErinnerung } from "./erinnerungen";
import { gemerkt, merke } from "./merken";

/**
 * Aktenzeichen (Startnummer, Zusatz), welche anderen Umgebungen die Kollisionsprüfung durchsucht und ob die App an
 * Fristen erinnert.
 */
export default function AktenEinstellungen({ umgebungen }: { umgebungen: UmgebungsListe | null }) {
  const [werte, setWerte] = useState<Werte | null>(null);
  const [vorschlag, setVorschlag] = useState("");
  const [zusatz, setZusatz] = useState("");
  const [nummer, setNummer] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [erinnern, setErinnern] = useState(() => !gemerkt(ERINNERUNGEN_AUS));

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
          Aktenzeichen nach dem Schema Nummer/Jahr, z. B. 102/26. Nächstes Aktenzeichen: <strong>{vorschlag || "…"}</strong>.
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
            <span className="feld-hinweis">Erscheint hinter dem Jahr: 102/26 {zusatz.trim() || "RS"}.</span>
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

      <h3>Erinnerungen</h3>
      <p className="erklaerung">
        Solange advOrdo läuft, meldet das Betriebssystem fällige Fristen (Vorfrist, Vortag, Ablauf), Termine (Vortag
        und Tag) und Wiedervorlagen. Ist die App geschlossen, erinnert sie nicht; sie ersetzt keinen Fristenkalender.
        Die Einstellung gilt für dieses Gerät.
      </p>
      <label className="schalter-zeile">
        <input
          type="checkbox"
          checked={erinnern}
          onChange={() => {
            merke(ERINNERUNGEN_AUS, erinnern);
            setErinnern(!erinnern);
            setMeldung(erinnern ? "Erinnerungen sind aus." : "Erinnerungen sind an.");
          }}
        />
        An Fristen, Termine und Wiedervorlagen erinnern
      </label>
      <button
        className="zweitrangig"
        onClick={() => {
          setFehler(null);
          setMeldung(null);
          void testErinnerung().then(
            () => setMeldung("Probe-Erinnerung gesendet. Erscheint keine, bitte die Mitteilungen des Systems für advOrdo prüfen."),
            (e) => setFehler(String(e)),
          );
        }}
      >
        Probe-Erinnerung senden
      </button>
      {meldung && <p className="meldung">{meldung}</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
    </section>
  );
}
