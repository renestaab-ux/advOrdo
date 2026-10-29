import { FormEvent, useEffect, useState } from "react";
import { ZeitEinstellungen, ZeitStufe, euro, kern } from "./kern";

/** Kernwerte („380.00“) deutsch zum Bearbeiten („380,00“). */
const de = (t: string) => t.replace(".", ",");

/**
 * Einstellungen → Zeiterfassung: Stundensatz-Stufen, Bearbeiter mit Stufe und die Taktung. Gilt für die aktive
 * Arbeitsumgebung; erfasste Zeiten behalten den Satz, der bei der Erfassung galt.
 */
export default function ZeitSaetze({ onEigeneDaten }: { onEigeneDaten: () => void }) {
  const [e, setE] = useState<ZeitEinstellungen | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [neueStufe, setNeueStufe] = useState({ name: "", satz: "" });
  const [neuerName, setNeuerName] = useState("");
  const [neueStufeId, setNeueStufeId] = useState("");
  const [zeigeArchiv, setZeigeArchiv] = useState(false);

  useEffect(() => {
    void kern<ZeitEinstellungen>("zeit.einstellungen").then(setE, (x) => setFehler(String(x)));
  }, []);

  async function mit(methode: string, params: Record<string, unknown> = {}) {
    setFehler(null);
    setMeldung(null);
    try {
      const r = await kern<ZeitEinstellungen>(methode, params);
      setE(r);
      return r;
    } catch (x) {
      setFehler(String(x));
      return null;
    }
  }

  if (!e) {
    return (
      <section className="karte">
        <h2>Zeiterfassung</h2>
        {fehler ? <p className="fehler">{fehler}</p> : <p className="status">Lade …</p>}
      </section>
    );
  }

  async function stufeNeu(x: FormEvent) {
    x.preventDefault();
    if (await mit("zeit.stufe_speichern", { name: neueStufe.name, satz: neueStufe.satz })) setNeueStufe({ name: "", satz: "" });
  }

  async function bearbeiterNeu(x: FormEvent) {
    x.preventDefault();
    if (await mit("zeit.bearbeiter_speichern", { name: neuerName, stufe_id: neueStufeId ? Number(neueStufeId) : null })) {
      setNeuerName("");
      setNeueStufeId("");
    }
  }

  async function ausEigenen() {
    const r = await mit("zeit.aus_eigenen_daten");
    if (r) setMeldung(r.neu ? `${r.neu} Person(en) aus Eigene Daten übernommen. Bitte noch die Stufe zuordnen.` : "Alle Personen aus Eigene Daten sind schon da.");
  }

  const sichtbar = e.bearbeiter.filter((b) => zeigeArchiv || !b.archiviert);
  const archiviert = e.bearbeiter.filter((b) => b.archiviert).length;

  return (
    <>
      <section className="karte zeit-einstellungen">
        <h2>Zeiterfassung</h2>
        <p className="erklaerung">
          Grundlage für die Abrechnung nach Zeitaufwand ist eine Vergütungsvereinbarung in Textform (§ 3a Abs. 1 S. 1
          RVG). Stufen, Bearbeiter und Taktung gelten für die aktive Arbeitsumgebung. Eine Änderung der Sätze wirkt nur
          auf neue Einträge; schon erfasste Zeiten behalten ihren Satz.
        </p>
        <label className="feld kurz">
          Taktung
          <select value={e.taktung} onChange={(x) => void mit("zeit.taktung_setzen", { minuten: Number(x.target.value) })}>
            {e.taktungen.map((t) => (
              <option key={t} value={t}>
                {t === 1 ? "minutengenau" : `${t} Minuten${t === 6 ? " (1/10 Std.)" : ""}${t > 6 ? " – über der empfohlenen Grenze" : ""}`}
              </option>
            ))}
          </select>
        </label>
        <p className="leise klein">
          Jeder Eintrag wird auf den nächsten vollen Takt aufgerundet, z. B. 7 Minuten bei 6er-Taktung auf 0,2 Std. Erfasst
          wird immer minutengenau; die Taktung wirkt erst bei Anzeige und Abrechnung. Eine andere vereinbarte
          Taktung trägst du als Rahmenvereinbarung beim Mandanten (Beteiligte) oder als Einzelvereinbarung im Reiter
          „Zeiten“ der Akte ein; sie geht dieser Einstellung vor.
        </p>
        {e.taktung_hinweis && <p className="hinweis">{e.taktung_hinweis}</p>}
      </section>

      <section className="karte zeit-einstellungen">
        <h3>Stundensätze je Stufe</h3>
        {e.stufen.length === 0 && <p className="leer">Noch keine Stufen.</p>}
        <ul className="zeit-stufen">
          {e.stufen.map((s, i) => (
            <StufeZeile
              key={s.id}
              s={s}
              erste={i === 0}
              letzte={i === e.stufen.length - 1}
              onSpeichern={(name, satz) => mit("zeit.stufe_speichern", { stufe_id: s.id, name, satz })}
              onSchieben={(richtung) => void mit("zeit.stufe_verschieben", { stufe_id: s.id, richtung })}
              onLoeschen={() => {
                if (window.confirm(`Stufe „${s.name}“ löschen? Bearbeiter dieser Stufe haben dann keinen Satz mehr.`))
                  void mit("zeit.stufe_loeschen", { stufe_id: s.id });
              }}
            />
          ))}
        </ul>
        <form className="kosten-zeile" onSubmit={stufeNeu}>
          <input
            className="text"
            placeholder="Neue Stufe, z. B. Counsel"
            value={neueStufe.name}
            onChange={(x) => setNeueStufe({ ...neueStufe, name: x.target.value })}
          />
          <label>
            €/Std.
            <input
              className="betrag"
              inputMode="decimal"
              value={neueStufe.satz}
              onChange={(x) => setNeueStufe({ ...neueStufe, satz: x.target.value })}
            />
          </label>
          <button type="submit" disabled={!neueStufe.name.trim() || !neueStufe.satz.trim()}>
            Hinzufügen
          </button>
        </form>
        <p className="leise klein">Die vorgegebenen Stufen und Sätze sind nur Beispiele; bitte an eure Vereinbarungen anpassen. Für Reisezeiten o. Ä.
          eine eigene Stufe anlegen; sie lässt sich im einzelnen Eintrag statt der Stufe des Bearbeiters wählen.</p>
      </section>

      <section className="karte zeit-einstellungen">
        <div className="kopf">
          <h3>Bearbeiter</h3>
          <button className="zweitrangig" onClick={() => void ausEigenen()}>
            Aus Eigene Daten übernehmen
          </button>
        </div>
        {meldung && <p className="meldung">{meldung}</p>}
        {sichtbar.length === 0 && (
          <p className="leer">
            Noch keine Bearbeiter. Übernimm die Berufsträger aus{" "}
            <button className="link" onClick={onEigeneDaten}>
              Eigene Daten
            </button>{" "}
            oder lege unten welche an (auch Mitarbeitende ohne Zulassung).
          </p>
        )}
        <ul className="zeit-stufen">
          {sichtbar.map((b) => (
            <li key={b.id} className={b.archiviert ? "kosten-zeile archiviert" : "kosten-zeile"}>
              <input
                className="text"
                aria-label="Name"
                defaultValue={b.name}
                onBlur={(x) =>
                  x.target.value.trim() !== b.name &&
                  void mit("zeit.bearbeiter_speichern", { bearbeiter_id: b.id, name: x.target.value, stufe_id: b.stufe_id })
                }
              />
              <select
                aria-label="Stufe"
                value={b.stufe_id ?? ""}
                onChange={(x) =>
                  void mit("zeit.bearbeiter_speichern", {
                    bearbeiter_id: b.id,
                    name: b.name,
                    stufe_id: x.target.value ? Number(x.target.value) : null,
                  })
                }
              >
                <option value="">– ohne Stufe (kein Satz) –</option>
                {e.stufen.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} · {euro(s.satz)}
                  </option>
                ))}
              </select>
              {!b.archiviert && (
                <label title="Wird beim Timer und bei neuen Einträgen vorgeschlagen">
                  <input
                    type="radio"
                    name="standard-bearbeiter"
                    checked={e.standard_bearbeiter_id === b.id}
                    onChange={() => void mit("zeit.standard_setzen", { bearbeiter_id: b.id })}
                  />{" "}
                  Standard
                </label>
              )}
              {b.archiviert ? (
                <button
                  className="link klein"
                  onClick={() => void mit("zeit.bearbeiter_speichern", { bearbeiter_id: b.id, name: b.name, stufe_id: b.stufe_id, archiviert: false })}
                >
                  Wieder aktiv
                </button>
              ) : (
                <button
                  className="link klein gefahr"
                  title="Ohne erfasste Zeiten wird gelöscht, sonst nur ausgeblendet"
                  onClick={() => void mit("zeit.bearbeiter_loeschen", { bearbeiter_id: b.id })}
                >
                  Entfernen
                </button>
              )}
            </li>
          ))}
        </ul>
        <form className="kosten-zeile" onSubmit={bearbeiterNeu}>
          <input className="text" placeholder="Name, z. B. Jana Köhler" value={neuerName} onChange={(x) => setNeuerName(x.target.value)} />
          <select aria-label="Stufe" value={neueStufeId} onChange={(x) => setNeueStufeId(x.target.value)}>
            <option value="">– Stufe –</option>
            {e.stufen.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} · {euro(s.satz)}
              </option>
            ))}
          </select>
          <button type="submit" disabled={!neuerName.trim()}>
            Hinzufügen
          </button>
        </form>
        {archiviert > 0 && (
          <button className="link klein" onClick={() => setZeigeArchiv(!zeigeArchiv)}>
            {zeigeArchiv ? "Ausgeblendete verbergen" : `${archiviert} ausgeblendete zeigen`}
          </button>
        )}
      </section>
      {fehler && <p className="fehler">{fehler}</p>}
    </>
  );
}

function StufeZeile({
  s,
  erste,
  letzte,
  onSpeichern,
  onSchieben,
  onLoeschen,
}: {
  s: ZeitStufe;
  erste: boolean;
  letzte: boolean;
  onSpeichern: (name: string, satz: string) => Promise<unknown>;
  onSchieben: (richtung: number) => void;
  onLoeschen: () => void;
}) {
  const [name, setName] = useState(s.name);
  const [satz, setSatz] = useState(de(s.satz));
  useEffect(() => {
    setName(s.name);
    setSatz(de(s.satz));
  }, [s.name, s.satz]);
  const geaendert = name.trim() !== s.name || satz.trim() !== de(s.satz);
  return (
    <li className="kosten-zeile">
      <input className="text" aria-label="Stufe" value={name} onChange={(x) => setName(x.target.value)} />
      <label>
        €/Std.
        <input className="betrag" inputMode="decimal" value={satz} onChange={(x) => setSatz(x.target.value)} />
      </label>
      {geaendert && (
        <button className="klein" onClick={() => void onSpeichern(name, satz)}>
          Speichern
        </button>
      )}
      <button className="link klein" disabled={erste} onClick={() => onSchieben(-1)} aria-label="Nach oben" title="Nach oben">
        ▲
      </button>
      <button className="link klein" disabled={letzte} onClick={() => onSchieben(1)} aria-label="Nach unten" title="Nach unten">
        ▼
      </button>
      <button className="link klein gefahr" onClick={onLoeschen}>
        Löschen
      </button>
    </li>
  );
}
