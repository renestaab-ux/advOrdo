import { FormEvent, useEffect, useState } from "react";
import {
  BAYERN_GERICHTSBARKEITEN,
  RECHERCHE_GERICHTE,
  RECHERCHE_QUELLE_NAME,
  RechercheErgebnis,
  RechercheFelder,
  RechercheQuelle,
  RechercheTreffer,
  RechtsprechungQuellen,
  kern,
  rechercheFelder,
  riiOnline,
  trefferTitel,
} from "./kern";

const LEER: RechercheFelder = {
  gericht: "",
  gerichtsbarkeit: "",
  aktenzeichen: "",
  volltext: "",
  norm: "",
  von: "",
  bis: "",
};

export function trefferSchluessel(t: Pick<RechercheTreffer, "quelle" | "doknr">): string {
  return `${t.quelle}:${t.doknr}`;
}

/**
 * Online-Suche im Bereich „Rechtsprechung“ (wie in JuraBox Lite): je Quelle eine eigene Maske. Gesucht wird erst auf
 * „Suchen“; an die Quelle gehen nur die eingegebenen Begriffe. Ein Treffer öffnet sich rechts und lässt sich von dort
 * in die Sammlung übernehmen und einer Akte zuordnen.
 */
export default function RechtsprechungSuche({
  offen,
  gespeichert,
  gesperrt,
  onOeffnen,
  onQuellen,
}: {
  /** Schlüssel des rechts geöffneten Treffers. */
  offen: string | null;
  /** Seit der Suche gespeicherte Treffer: Schlüssel → Entscheidung in der Sammlung. */
  gespeichert: Record<string, number>;
  gesperrt: boolean;
  onOeffnen: (t: RechercheTreffer) => void;
  onQuellen: () => void;
}) {
  const [quelle, setQuelle] = useState<RechercheQuelle>("rii");
  const [felder, setFelder] = useState<RechercheFelder>(LEER);
  const [ergebnis, setErgebnis] = useState<RechercheErgebnis | null>(null);
  const [neuris, setNeuris] = useState(false);
  const [laeuft, setLaeuft] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    kern<RechtsprechungQuellen>("rechtsprechung.quellen").then(
      (q) => setNeuris(q.neuris),
      () => setNeuris(false),
    );
  }, []);

  const feld = (name: keyof RechercheFelder) => ({
    value: felder[name],
    onChange: (e: { target: { value: string } }) => setFelder({ ...felder, [name]: e.target.value }),
  });

  const gesendet = rechercheFelder(quelle, felder);
  const leer = Object.keys(gesendet).length === 0;
  const imVerzeichnis = quelle === "rii" && !riiOnline(felder);

  async function ausfuehren(was: string, f: () => Promise<RechercheErgebnis>, anhaengen: boolean) {
    setLaeuft(was);
    setFehler(null);
    try {
      const r = await f();
      setErgebnis((alt) => (anhaengen && alt ? { ...r, treffer: [...alt.treffer, ...r.treffer] } : r));
    } catch (e) {
      setFehler(String(e));
      if (!anhaengen) setErgebnis(null);
    } finally {
      setLaeuft(null);
    }
  }

  function suchen(ev: FormEvent) {
    ev.preventDefault();
    if (leer) return;
    const wo = imVerzeichnis
      ? "im Verzeichnis von rechtsprechung-im-internet.de"
      : `bei ${RECHERCHE_QUELLE_NAME[quelle]}`;
    void ausfuehren(
      `Suche ${wo} …`,
      () =>
        kern<RechercheErgebnis>("rechtsprechung.recherche", {
          quelle,
          felder: gesendet,
        }),
      false,
    );
  }

  function weiter() {
    if (!ergebnis) return;
    void ausfuehren(
      "Lade weitere Treffer …",
      () =>
        kern<RechercheErgebnis>("rechtsprechung.recherche_weiter", {
          quelle: ergebnis.quelle,
        }),
      true,
    );
  }

  function quelleWaehlen(q: RechercheQuelle) {
    setQuelle(q);
    setErgebnis(null);
    setFehler(null);
  }

  const quellen: RechercheQuelle[] = neuris ? ["rii", "bayern", "neuris"] : ["rii", "bayern"];
  const zeitraum = (
    <label>
      Zeitraum (von – bis)
      <span className="zeitraum">
        <input type="date" aria-label="von" {...feld("von")} />
        <input type="date" aria-label="bis" {...feld("bis")} />
      </span>
    </label>
  );

  return (
    <>
      <div className="wahl-reihe" role="group" aria-label="Quelle der Suche">
        {quellen.map((q) => (
          <button
            key={q}
            type="button"
            className={`chip${quelle === q ? " aktiv" : ""}`}
            onClick={() => quelleWaehlen(q)}
          >
            {RECHERCHE_QUELLE_NAME[q]}
          </button>
        ))}
      </div>
      {!neuris && (
        <p className="leise">
          NeuRIS lässt sich unter{" "}
          <button className="link" onClick={onQuellen}>
            Einstellungen → Rechtsquellen
          </button>{" "}
          einschalten.
        </p>
      )}

      <form onSubmit={suchen} aria-label={`Suche bei ${RECHERCHE_QUELLE_NAME[quelle]}`}>
        <div className="recherche-maske">
          {quelle === "bayern" ? (
            <label>
              Gerichtsbarkeit
              <select {...feld("gerichtsbarkeit")}>
                <option value="">Alle Gerichtsbarkeiten</option>
                {BAYERN_GERICHTSBARKEITEN.map((g) => (
                  <option key={g}>{g}</option>
                ))}
              </select>
            </label>
          ) : (
            <label>
              Gericht
              <select {...feld("gericht")}>
                <option value="">Alle Gerichte</option>
                {RECHERCHE_GERICHTE.map((g) => (
                  <option key={g}>{g}</option>
                ))}
              </select>
            </label>
          )}
          <label>
            {quelle === "rii" ? "Aktenzeichen oder ECLI" : "Aktenzeichen"}
            <input
              {...feld("aktenzeichen")}
              placeholder={quelle === "bayern" ? "z. B. 7 U 1234/22" : "z. B. VIII ZR 103/15"}
            />
          </label>
          <label>
            {quelle === "neuris" ? "Suchbegriff" : "Volltext"}
            <input {...feld("volltext")} placeholder="z. B. Gebrauchtwagen Beweislastumkehr" />
          </label>
          {quelle === "rii" && (
            <label>
              Norm
              <input {...feld("norm")} placeholder="z. B. § 476 BGB" />
            </label>
          )}
          {zeitraum}
        </div>
        <div className="recherche-aktionen">
          <button type="submit" disabled={leer || !!laeuft || gesperrt}>
            Suchen
          </button>
          {(Object.values(felder).some((w) => w) || ergebnis) && (
            <button
              type="button"
              className="zweitrangig"
              onClick={() => {
                setFelder(LEER);
                setErgebnis(null);
                setFehler(null);
              }}
            >
              Leeren
            </button>
          )}
          <span className="leise">
            {imVerzeichnis
              ? "Gericht, Aktenzeichen und Zeitraum sucht die App im geladenen Verzeichnis, ohne Netz."
              : "Die Suchbegriffe gehen an die Seite. Namen oder Aktenzeichen eigener Mandate nur eingeben, wenn das gewollt ist."}
          </span>
        </div>
      </form>

      {laeuft && <p className="status" role="status">{laeuft}</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}

      {ergebnis && ergebnis.treffer.length === 0 && !laeuft && (
        <p className="leer">Keine Treffer. Die Suche lässt sich mit weniger oder anderen Begriffen erweitern.</p>
      )}
      {ergebnis && ergebnis.treffer.length > 0 && (
        <>
          <p className="leise">
            {ergebnis.ort === "verzeichnis" ? "Im Verzeichnis" : `Bei ${RECHERCHE_QUELLE_NAME[ergebnis.quelle]}`}:{" "}
            {ergebnis.gesamt.toLocaleString("de-DE")} Treffer, neueste zuerst.
          </p>
          <ul className="sammlung-eintraege">
            {ergebnis.treffer.map((t) => {
              const schluessel = trefferSchluessel(t);
              const inSammlung = t.urteil_id != null || schluessel in gespeichert;
              return (
                <li key={schluessel} className={offen === schluessel ? "sammlung-eintrag aktiv" : "sammlung-eintrag"}>
                  <div
                    className="sammlung-flaeche"
                    role="button"
                    tabIndex={0}
                    aria-label={`${trefferTitel(t)} öffnen`}
                    onClick={() => !gesperrt && onOeffnen(t)}
                    onKeyDown={(ev) => {
                      if (ev.target !== ev.currentTarget || (ev.key !== "Enter" && ev.key !== " ") || gesperrt) return;
                      ev.preventDefault();
                      onOeffnen(t);
                    }}
                  >
                    <strong className="sammlung-titel">
                      {trefferTitel(t)}
                      {inSammlung && <span className="marke-gespeichert">in der Sammlung</span>}
                    </strong>
                    {t.titel && <p className="volltext-titel">{t.titel}</p>}
                    {t.normen && <p className="fundort">Normen: {t.normen}</p>}
                    {t.ausschnitt && <p className="recherche-ausschnitt">{t.ausschnitt}</p>}
                  </div>
                </li>
              );
            })}
          </ul>
          <div className="recherche-fuss">
            <span className="leise">
              {ergebnis.treffer.length.toLocaleString("de-DE")} von {ergebnis.gesamt.toLocaleString("de-DE")} Treffern
              {!ergebnis.weitere &&
                ergebnis.gesamt > ergebnis.treffer.length &&
                " – für die übrigen bitte die Suche eingrenzen"}
            </span>
            {ergebnis.weitere && (
              <button className="zweitrangig" onClick={weiter} disabled={!!laeuft || gesperrt}>
                Weitere Treffer laden
              </button>
            )}
          </div>
        </>
      )}
    </>
  );
}
