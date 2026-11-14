import { useState } from "react";
import { type KiAuftrag, type KiLeistung, kern, leistungsBericht } from "./kern";
import { useAuftrag } from "./useAuftrag";

const STAND_TEXT = { ok: "in Ordnung", warnung: "Hinweis", fehler: "Fehler" } as const;

/**
 * KI-Leistungstest in der Diagnose: misst Antwortzeit und Geschwindigkeit des gewählten Modells und stellt feste
 * Prüffragen mit bekannter Antwort (Fristen, Zuständigkeit, erfundene Normen, Zitattreue). Startet nur auf Klick.
 */
export default function KiLeistungstest() {
  const [auftrag, setAuftrag] = useState<KiAuftrag | null>(null);
  const [ergebnis, setErgebnis] = useState<KiLeistung | null>(null);
  const [zeitpunkt, setZeitpunkt] = useState<Date | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const laeuft = auftrag?.status === "laeuft";

  useAuftrag(
    laeuft ? auftrag.auftrag_id : null,
    (stand) => {
      setAuftrag(stand);
      if (stand.status === "fertig") {
        setErgebnis(stand.ergebnis as KiLeistung);
        setZeitpunkt(new Date());
      }
      if (stand.status === "fehler") setFehler(stand.fehler);
    },
    (e) => {
      setFehler(String(e));
      setAuftrag(null);
    },
  );

  async function starten() {
    setFehler(null);
    setMeldung(null);
    setErgebnis(null);
    try {
      setAuftrag(await kern<KiAuftrag>("ki.leistungstest"));
    } catch (e) {
      setFehler(String(e));
    }
  }

  async function abbrechen() {
    if (auftrag) setAuftrag(await kern<KiAuftrag>("ki.abbrechen", { auftrag_id: auftrag.auftrag_id }));
  }

  async function kopieren() {
    if (!ergebnis) return;
    try {
      await navigator.clipboard.writeText(leistungsBericht(ergebnis, zeitpunkt ?? new Date()));
      setMeldung("Bericht kopiert. Er enthält nur die Testfragen und die Antworten des Modells.");
    } catch {
      setFehler("Kopieren war nicht möglich.");
    }
  }

  return (
    <section className="karte ki-leistung" aria-labelledby="ki-leistung-titel">
      <h2 id="ki-leistung-titel">KI-Leistungstest</h2>
      <p className="erklaerung">
        Prüft das gewählte Sprachmodell: wie schnell es antwortet und ob es 16 feste Prüffragen mit bekannter Antwort
        richtig löst (Fristen, Zuständigkeit, erfundene Normen, wörtliche Zitate). advOrdo wertet die Antworten selbst
        aus; jede erwartete Antwort nennt ihre Fundstelle. Ans Modell gehen nur diese Testtexte, keine Akteninhalte. Mit
        einem lokalen Modell dauert der Test einige Minuten. Ein Dutzend Fragen ist eine Stichprobe, kein Benchmark.
      </p>
      <div className="aktionen">
        <button onClick={() => void starten()} disabled={laeuft}>
          {laeuft ? "Test läuft …" : ergebnis ? "Erneut testen" : "KI-Leistung testen"}
        </button>
        {laeuft && (
          <button className="zweitrangig" onClick={() => void abbrechen()}>
            Abbrechen
          </button>
        )}
        {ergebnis && !laeuft && (
          <button className="zweitrangig" onClick={() => void kopieren()}>
            Bericht kopieren
          </button>
        )}
      </div>
      {laeuft && (
        <p className="leise" role="status">
          {auftrag.text} ({auftrag.sekunden} s)
        </p>
      )}
      {auftrag?.status === "abgebrochen" && <p className="leise">Test abgebrochen.</p>}
      {meldung && <p className="meldung">{meldung}</p>}
      {fehler && (
        <p className="fehler" role="alert">
          {fehler}
        </p>
      )}

      {ergebnis && (
        <>
          <p className="leise klein">
            Modell {ergebnis.modell || "–"} ({ergebnis.anbieter}, {ergebnis.ort}), Dauer {ergebnis.dauer} s
          </p>
          <h3>Geschwindigkeit</h3>
          <ul className="diagnose-liste">
            {ergebnis.messwerte.map((w) => (
              <li key={w.titel} className={`diagnose-zeile stand-${w.stand}`}>
                <span className="diagnose-marke" aria-hidden />
                <div>
                  <div className="diagnose-titel">
                    <strong>{w.titel}</strong>
                    <span className="leise klein">{STAND_TEXT[w.stand]}</span>
                  </div>
                  <div>{w.wert}</div>
                  {w.hinweis && <div className="leise klein">{w.hinweis}</div>}
                </div>
              </li>
            ))}
          </ul>

          <h3>Prüffragen</h3>
          <p className={`diagnose-summe stand-${ergebnis.gesamt.stand}`}>{ergebnis.gesamt.meldung}</p>
          <p className="leise klein">
            {ergebnis.bereiche.map((b) => `${b.bereich}: ${b.richtig} von ${b.von}`).join(" · ")}
          </p>
          <ul className="diagnose-liste">
            {ergebnis.fragen.map((f) => (
              <li key={f.id} className={`diagnose-zeile stand-${f.richtig ? "ok" : "fehler"}`}>
                <span className="diagnose-marke" aria-hidden />
                <div>
                  <div className="diagnose-titel">
                    <strong>{f.bereich}</strong>
                    <span className="leise klein">
                      {f.richtig ? "richtig" : "falsch"} · {String(f.sekunden).replace(".", ",")} s
                    </span>
                  </div>
                  <div>{f.frage}</div>
                  <div className="ki-leistung-antwort">
                    Antwort des Modells: {f.antwort}
                    {!f.richtig && <> · Erwartet: {f.erwartet}</>}
                  </div>
                  <details className="leise klein">
                    <summary>Fundstelle</summary>
                    {f.fundstelle}
                  </details>
                </div>
              </li>
            ))}
          </ul>
          <p className="leise klein">Fundstellen geprüft am {ergebnis.stand_fundstellen}.</p>
        </>
      )}
    </section>
  );
}
