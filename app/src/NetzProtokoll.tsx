import { useCallback, useEffect, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import {
  NETZ_ORTE,
  NetzEinstellungen,
  NetzProtokoll as Protokoll,
  istDesktop,
  kern,
  netzErgebnis,
  netzFrist,
  netzZeit,
} from "./kern";

const ANZEIGE = 200;

/**
 * Protokoll der Online-Anfragen: jede Verbindung, die der Kern aufgebaut hat, mit Ziel, Zweck und dem, was dabei
 * gesendet wurde. Zum Nachprüfen, dass an öffentliche Quellen nur Normen und Entscheidungsangaben gehen.
 */
export default function NetzProtokoll() {
  const [auchNetz, setAuchNetz] = useState(false);
  const [protokoll, setProtokoll] = useState<Protokoll | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [einst, setEinst] = useState<NetzEinstellungen | null>(null);

  useEffect(() => {
    if (!istDesktop) return;
    void kern<NetzEinstellungen>("netz.einstellungen").then(setEinst, (e) => setFehler(String(e)));
  }, []);

  async function aufbewahren(tage: number, hoechstens: number) {
    try {
      setEinst(await kern<NetzEinstellungen>("netz.einstellungen_setzen", { tage, hoechstens }));
      await laden();
    } catch (e) {
      setFehler(String(e));
    }
  }

  const laden = useCallback(async () => {
    if (!istDesktop) return;
    try {
      setProtokoll(await kern<Protokoll>("netz.protokoll", { nur_internet: !auchNetz, limit: ANZEIGE }));
      setFehler(null);
    } catch (e) {
      setFehler(String(e));
    }
  }, [auchNetz]);

  useEffect(() => {
    void laden();
  }, [laden]);

  async function exportieren() {
    setMeldung(null);
    const ziel = await save({
      title: "Protokoll der Online-Anfragen exportieren",
      defaultPath: `advordo-online-anfragen-${new Date().toISOString().slice(0, 10)}.csv`,
      filters: [
        { name: "Tabelle (CSV, z. B. für Excel)", extensions: ["csv"] },
        { name: "Text", extensions: ["txt"] },
      ],
    });
    if (!ziel) return;
    try {
      const r = await kern<{ pfad: string; anzahl: number }>("netz.exportieren", { pfad: ziel, nur_internet: !auchNetz });
      setMeldung(`${r.anzahl} Einträge exportiert nach ${r.pfad}.`);
    } catch (e) {
      setFehler(String(e));
    }
  }

  const eintraege = protokoll?.eintraege ?? [];
  return (
    <section className="karte netzprotokoll">
      <h2>Protokoll der Online-Anfragen</h2>
      <p className="erklaerung">
        Jede Verbindung, die advOrdo aufbaut, mit Ziel, Zweck und dem, was dabei außer der Adresse gesendet wurde.
        API-Schlüssel und Texte an ein Sprachmodell stehen nicht darin; bei KI-Anfragen nur Anbieter, Modell, Aufgabe und
        Umfang. Das Protokoll liegt nur auf diesem Gerät. Was du im Browser öffnest, sieht advOrdo nicht.
      </p>
      <div className="aktionen">
        <label className="schalter-zeile">
          <input type="checkbox" checked={auchNetz} onChange={(e) => setAuchNetz(e.target.checked)} />
          Auch Anfragen im eigenen Netz (lokales Sprachmodell)
        </label>
        <button className="zweitrangig" onClick={() => void laden()}>
          Aktualisieren
        </button>
        <button className="zweitrangig" onClick={() => void exportieren()} disabled={!protokoll?.gesamt}>
          Exportieren …
        </button>
      </div>
      {einst && (
        <div className="aktionen netzprotokoll-aufbewahrung">
          <label>
            Aufbewahren{" "}
            <select value={einst.tage} onChange={(e) => void aufbewahren(Number(e.target.value), einst.hoechstens)}>
              {einst.tage_wahl.map((t) => (
                <option key={t} value={t}>
                  {netzFrist(t)}
                  {t === einst.vorgabe.tage ? " (Vorgabe)" : ""}
                </option>
              ))}
            </select>
          </label>
          <label>
            höchstens{" "}
            <select value={einst.hoechstens} onChange={(e) => void aufbewahren(einst.tage, Number(e.target.value))}>
              {einst.hoechstens_wahl.map((h) => (
                <option key={h} value={h}>
                  {h.toLocaleString("de-DE")} Einträge{h === einst.vorgabe.hoechstens ? " (Vorgabe)" : ""}
                </option>
              ))}
            </select>
          </label>
          <span className="leise klein">Ältere Einträge löscht advOrdo beim Start und einmal am Tag.</span>
        </div>
      )}
      {meldung && <p className="meldung">{meldung}</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
      {protokoll && protokoll.gesamt === 0 && <p className="leise">Noch keine Anfragen protokolliert.</p>}
      {eintraege.length > 0 && (
        <>
          <p className="leise klein">
            {protokoll!.gesamt > eintraege.length
              ? `Die neuesten ${eintraege.length} von ${protokoll!.gesamt} Einträgen; alle im Export.`
              : `${protokoll!.gesamt} Einträge`}
            {protokoll!.seit && `, seit ${netzZeit(protokoll!.seit)}`}.
          </p>
          <div className="netzprotokoll-rahmen">
            <table className="netzprotokoll-tabelle">
              <thead>
                <tr>
                  <th>Zeit</th>
                  <th>Ziel</th>
                  <th>Zweck</th>
                  <th>Gesendet</th>
                  <th>Ergebnis</th>
                </tr>
              </thead>
              <tbody>
                {eintraege.map((e, i) => {
                  const erg = netzErgebnis(e);
                  return (
                    <tr key={`${e.zeit}-${i}`}>
                      <td className="nowrap">{netzZeit(e.zeit)}</td>
                      <td>
                        {e.ziel}
                        <div className="leise klein">{NETZ_ORTE[e.ort] ?? e.ort}</div>
                      </td>
                      <td>{e.zweck}</td>
                      <td>
                        <div className="netzprotokoll-adresse">
                          {e.methode} {e.adresse}
                        </div>
                        {e.gesendet && <div className="klein">{e.gesendet}</div>}
                      </td>
                      <td className={erg.ok ? "" : "fehler"}>
                        {erg.text}
                        <div className="leise klein">{(e.dauer_ms / 1000).toLocaleString("de-DE", { maximumFractionDigits: 1 })} s</div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
