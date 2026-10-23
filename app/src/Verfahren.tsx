import { FormEvent, useEffect, useState } from "react";
import { AktenOptionen, INSTANZ_VORGABE, Verfahren, datumLang, kern } from "./kern";
import VerfahrenAusDokument from "./VerfahrenAusDokument";

interface Entwurf {
  art: string;
  instanz: string;
  gericht: string;
  spruchkoerper: string;
  aktenzeichen: string;
  status: string;
  beginn: string;
  ende: string;
  notiz: string;
}

const LEER: Entwurf = {
  art: "klage",
  instanz: "1. Instanz",
  gericht: "",
  spruchkoerper: "",
  aktenzeichen: "",
  status: "laufend",
  beginn: "",
  ende: "",
  notiz: "",
};
/**
 * Verfahren der Akte (Stammdaten): Mahnverfahren, Klage in erster Instanz, Berufung … je mit Gericht und gerichtlichem
 * Aktenzeichen. Das Gericht steht danach auch unter den Beteiligten.
 */
export default function VerfahrenKarte({ akteId, onGeaendert }: { akteId: number; onGeaendert: () => void }) {
  const [verfahren, setVerfahren] = useState<Verfahren[] | null>(null);
  const [optionen, setOptionen] = useState<AktenOptionen | null>(null);
  const [bearbeitet, setBearbeitet] = useState<{ id: number | null; e: Entwurf } | null>(null);
  const [loeschfrage, setLoeschfrage] = useState<Verfahren | null>(null);
  const [gerichte, setGerichte] = useState<string[]>([]);
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [ausDokument, setAusDokument] = useState(false);

  useEffect(() => {
    void kern<Verfahren[]>("akten.verfahren", { akte_id: akteId }).then(setVerfahren, (e) => setFehler(String(e)));
    void kern<AktenOptionen>("akten.optionen").then(setOptionen, () => undefined);
    // Gerichte aus dem Beteiligtenverzeichnis als Vorschläge für das Eingabefeld.
    void kern<{ name: string; daten: Record<string, string> }[]>("beteiligte.liste", { suche: "", art: "organisation" }).then(
      (l) => setGerichte(l.filter((b) => b.daten.kategorie === "Gericht").map((b) => b.name)),
      () => undefined,
    );
  }, [akteId]);

  async function speichern(ev: FormEvent) {
    ev.preventDefault();
    if (!bearbeitet) return;
    setLaeuft(true);
    setFehler(null);
    try {
      setVerfahren(
        await kern<Verfahren[]>("akten.verfahren_speichern", {
          akte_id: akteId,
          daten: bearbeitet.e,
          verfahren_id: bearbeitet.id,
        }),
      );
      setBearbeitet(null);
      onGeaendert();
    } catch (e) {
      setFehler(String(e));
    } finally {
      setLaeuft(false);
    }
  }

  async function loeschen(v: Verfahren) {
    setLoeschfrage(null);
    try {
      setVerfahren(await kern<Verfahren[]>("akten.verfahren_loeschen", { verfahren_id: v.id }));
      onGeaendert();
    } catch (e) {
      setFehler(String(e));
    }
  }

  const e = bearbeitet?.e;
  const setze = (teil: Partial<Entwurf>) => bearbeitet && setBearbeitet({ ...bearbeitet, e: { ...bearbeitet.e, ...teil } });

  return (
    <section className="karte verfahren-karte">
      <div className="kopf">
        <h2>Verfahren</h2>
        {!bearbeitet && !ausDokument && (
          <span className="aktionen">
            <button className="zweitrangig" onClick={() => setAusDokument(true)} title="Gericht, Aktenzeichen und Parteien aus einem Dokument übernehmen">
              Aus Dokument …
            </button>
            <button className="zweitrangig" onClick={() => setBearbeitet({ id: null, e: { ...LEER } })}>
              + Verfahren
            </button>
          </span>
        )}
      </div>
      <p className="erklaerung">
        Mahnverfahren, Klage, Berufung usw. mit Instanz, Gericht und gerichtlichem Aktenzeichen. Das jüngste laufende
        Verfahren steht im Kopf der Akte.
      </p>
      {verfahren && verfahren.length === 0 && !bearbeitet && <p className="leer">Noch kein Verfahren eingetragen.</p>}
      {verfahren && verfahren.length > 0 && (
        <ol className="verfahren-liste">
          {verfahren.map((v) => (
            <li key={v.id} className={v.aktuell ? "aktuell" : undefined}>
              <div>
                <strong>
                  {v.art_text}
                  {v.instanz && `, ${v.instanz}`}
                </strong>
                {v.aktuell && <span className="marke-aktuell">aktuell</span>}
                {v.status !== "laufend" && <span className={`status-marke ${v.status}`}>{v.status}</span>}
                <div className="leise">
                  {[v.gericht, v.spruchkoerper, v.aktenzeichen].filter(Boolean).join(" · ") || "Gericht noch offen"}
                  {v.beginn && ` · seit ${datumLang(v.beginn)}`}
                  {v.ende && ` · bis ${datumLang(v.ende)}`}
                </div>
                {v.notiz && <div className="klein">{v.notiz}</div>}
              </div>
              <span className="aktionen">
                <button
                  className="link klein"
                  onClick={() =>
                    setBearbeitet({
                      id: v.id,
                      e: {
                        art: v.art,
                        instanz: v.instanz ?? "",
                        gericht: v.gericht ?? "",
                        spruchkoerper: v.spruchkoerper ?? "",
                        aktenzeichen: v.aktenzeichen ?? "",
                        status: v.status,
                        beginn: v.beginn ?? "",
                        ende: v.ende ?? "",
                        notiz: v.notiz ?? "",
                      },
                    })
                  }
                >
                  Bearbeiten
                </button>
                <button className="link klein gefahr" onClick={() => setLoeschfrage(v)}>
                  Entfernen
                </button>
              </span>
            </li>
          ))}
        </ol>
      )}
      {loeschfrage && (
        <div className="rueckfrage" role="alertdialog" aria-label="Verfahren entfernen?">
          <strong>{loeschfrage.bezeichnung} entfernen?</strong>
          <p>Fristen und Termine bleiben in der Akte, das Gericht bleibt unter den Beteiligten.</p>
          <div className="aktionen">
            <button className="gefahr-voll" onClick={() => loeschen(loeschfrage)}>
              Entfernen
            </button>
            <button className="zweitrangig" onClick={() => setLoeschfrage(null)} autoFocus>
              Abbrechen
            </button>
          </div>
        </div>
      )}
      {ausDokument && (
        <VerfahrenAusDokument
          akteId={akteId}
          onAbbrechen={() => setAusDokument(false)}
          onFertig={(liste) => {
            setVerfahren(liste);
            setAusDokument(false);
            onGeaendert();
          }}
        />
      )}
      {e && optionen && (
        <form className="verfahren-formular" onSubmit={speichern}>
          {!bearbeitet?.id && (
            <p className="leise klein">
              Gericht und Aktenzeichen stehen schon in einem Dokument?{" "}
              <button
                type="button"
                className="link klein"
                onClick={() => {
                  setBearbeitet(null);
                  setAusDokument(true);
                }}
              >
                Aus Dokument übernehmen …
              </button>
            </p>
          )}
          <div className="formular-raster">
            <label className="feld">
              Art
              <select
                value={e.art}
                onChange={(ev) =>
                  setze({ art: ev.target.value, instanz: INSTANZ_VORGABE[ev.target.value] ?? (bearbeitet?.id ? e.instanz : "") })
                }
              >
                {Object.entries(optionen.verfahren_arten).map(([k, t]) => (
                  <option key={k} value={k}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label className="feld">
              Instanz
              <select value={e.instanz} onChange={(ev) => setze({ instanz: ev.target.value })}>
                <option value="">–</option>
                {optionen.instanzen.map((i) => (
                  <option key={i}>{i}</option>
                ))}
              </select>
            </label>
            <label className="feld">
              Gericht
              <input
                list="verfahren-gerichte"
                value={e.gericht}
                onChange={(ev) => setze({ gericht: ev.target.value })}
                placeholder="z. B. Landgericht Freiburg im Breisgau"
              />
              <datalist id="verfahren-gerichte">
                {gerichte.map((g) => (
                  <option key={g} value={g} />
                ))}
              </datalist>
            </label>
            <label className="feld">
              Spruchkörper
              <input
                value={e.spruchkoerper}
                onChange={(ev) => setze({ spruchkoerper: ev.target.value })}
                placeholder="z. B. 2. Zivilkammer"
              />
            </label>
            <label className="feld">
              Gerichtliches Aktenzeichen
              <input value={e.aktenzeichen} onChange={(ev) => setze({ aktenzeichen: ev.target.value })} placeholder="z. B. 2 O 233/26" />
            </label>
            <label className="feld">
              Status
              <select value={e.status} onChange={(ev) => setze({ status: ev.target.value })}>
                {Object.entries(optionen.status).map(([k, t]) => (
                  <option key={k} value={k}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label className="feld">
              Beginn
              <input type="date" value={e.beginn} onChange={(ev) => setze({ beginn: ev.target.value })} />
            </label>
            <label className="feld">
              Ende
              <input type="date" value={e.ende} onChange={(ev) => setze({ ende: ev.target.value })} />
            </label>
            <label className="feld feld-breit">
              Notiz
              <input value={e.notiz} onChange={(ev) => setze({ notiz: ev.target.value })} placeholder="z. B. Abgabe nach Widerspruch" />
            </label>
          </div>
          <span className="aktionen">
            <button type="submit" disabled={laeuft}>
              {bearbeitet?.id ? "Speichern" : "Verfahren eintragen"}
            </button>
            <button type="button" className="zweitrangig" onClick={() => setBearbeitet(null)}>
              Abbrechen
            </button>
          </span>
        </form>
      )}
      {fehler && <p className="fehler">{fehler}</p>}
    </section>
  );
}
