import { useCallback, useEffect, useState } from "react";
import { Beleg, Zitatbereich } from "./Belege";
import {
  Gegenueberstellung,
  GegenueberstellungErgebnis,
  GegenueberstellungZitat,
  KiAuftrag,
  KiFundstelle,
  UrteilStelle,
  dauerText,
  kern,
} from "./kern";

export const ERGEBNIS_TEXT: Record<GegenueberstellungErgebnis, string> = {
  traegt: "trägt",
  traegt_teilweise: "trägt teilweise",
  traegt_nicht: "trägt nicht",
  nicht_beurteilbar: "nicht beurteilbar",
  nicht_pruefbar: "nicht prüfbar",
};

/** Je Urteilszitat: links die Stelle im Schriftsatz, rechts die Stelle der Entscheidung, darunter die Einschätzung. */
export function GegenueberstellungListe({
  zitate,
  onFundstelle,
}: {
  zitate: GegenueberstellungZitat[];
  onFundstelle: (f: KiFundstelle) => void;
}) {
  return (
    <Zitatbereich zeigen>
      <ul className="gegenueber">
        {zitate.map((z, i) => (
          <li key={i} className={`ergebnis-${z.ergebnis}`}>
            <div className="gegenueber-kopf">
              <span className={`marke-status gegenueber-${z.ergebnis}`}>{ERGEBNIS_TEXT[z.ergebnis]}</span>{" "}
              <strong>
                {z.zitat}
                {z.rn_zitiert != null && `, Rn. ${z.rn_zitiert}`}
              </strong>
              {z.status === "ohne_beleg" && <span className="ohne-beleg">ohne Beleg aus der Entscheidung</span>}
            </div>
            {z.ergebnis === "nicht_pruefbar" ? (
              <>
                <ul className="belege">
                  <Beleg f={z.zitierstelle} gewaehlt={false} onFundstelle={() => onFundstelle(z.zitierstelle)} />
                </ul>
                {z.hinweis && <p className="hinweis">{z.hinweis}</p>}
              </>
            ) : (
              <>
                <div className="gegenueber-spalten">
                  <div>
                    <div className="gegenueber-titel">Schriftsatz</div>
                    {z.behauptung && <p>{z.behauptung}</p>}
                    <ul className="belege">
                      {(z.schriftsatz_belege?.length ? z.schriftsatz_belege : [z.zitierstelle]).map((f, j) => (
                        <Beleg key={j} f={f} gewaehlt={false} onFundstelle={() => onFundstelle(f)} />
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="gegenueber-titel">{z.urteil}</div>
                    {z.entscheidung && <p>{z.entscheidung}</p>}
                    {z.urteil_belege && z.urteil_belege.length > 0 ? (
                      <ul className="belege">
                        {z.urteil_belege.map((u, j) => (
                          <UrteilZeile key={j} u={u} />
                        ))}
                      </ul>
                    ) : (
                      <p className="leise">Vorgelegt: {z.stellen.join(", ") || "–"}</p>
                    )}
                  </div>
                </div>
                {z.begruendung && (
                  <p className="gegenueber-begruendung">
                    <span className="art">Einschätzung des Modells</span> {z.begruendung}
                  </p>
                )}
                {z.hinweis && <p className="hinweis">{z.hinweis}</p>}
              </>
            )}
          </li>
        ))}
      </ul>
    </Zitatbereich>
  );
}

function UrteilZeile({ u }: { u: UrteilStelle }) {
  return (
    <li>
      <span className="fundort">{u.stelle}</span>
      {u.treffer === "angenaehert" && <span className="leise">angenähert</span>}
      <div className="ausschnitt">
        {u.ausschnitt.davor}
        <mark>{u.ausschnitt.wert}</mark>
        {u.ausschnitt.danach}
      </div>
    </li>
  );
}

/** Bereich im Reiter Rechtsprechung: gespeicherte Gegenüberstellungen zeigen, fehlende vom Modell prüfen lassen. */
export function GegenueberstellungBereich({
  akteId,
  dokumentId,
  onFundstelle,
}: {
  akteId: number;
  dokumentId?: number;
  onFundstelle: (f: KiFundstelle) => void;
}) {
  const [daten, setDaten] = useState<Gegenueberstellung | null>(null);
  const [auftrag, setAuftrag] = useState<KiAuftrag | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const lade = useCallback(async () => {
    setDaten(await kern<Gegenueberstellung>("ki.gegenueberstellung", { akte_id: akteId, dokument_id: dokumentId }));
  }, [akteId, dokumentId]);

  useEffect(() => {
    setDaten(null);
    setFehler(null);
    void (async () => {
      try {
        await lade();
        const laufend = await kern<KiAuftrag | null>("ki.laufend");
        if (laufend?.aufgabe === "gegenueberstellung") setAuftrag(laufend);
      } catch (e) {
        setFehler(String(e));
      }
    })();
  }, [lade]);

  const laeuft = auftrag?.status === "laeuft";
  useEffect(() => {
    if (!laeuft || !auftrag) return;
    const id = auftrag.auftrag_id;
    const takt = window.setInterval(async () => {
      try {
        const stand = await kern<KiAuftrag>("ki.auftrag", { auftrag_id: id });
        setAuftrag(stand);
        if (stand.status === "laeuft") return;
        if (stand.status === "fehler") setFehler(stand.fehler);
        await lade();
      } catch (e) {
        setFehler(String(e));
        setAuftrag(null);
      }
    }, 1000);
    return () => window.clearInterval(takt);
  }, [laeuft, auftrag?.auftrag_id, lade]);

  async function starte() {
    setFehler(null);
    try {
      setAuftrag(await kern<KiAuftrag>("ki.starten", { aufgabe: "gegenueberstellung", akte_id: akteId, dokument_id: dokumentId }));
    } catch (e) {
      setFehler(String(e));
    }
  }

  if (!daten || daten.anzahl === 0) return fehler ? <p className="fehler">{fehler}</p> : null;
  const geprueft = daten.zitate.filter((z) => z.ergebnis !== "nicht_pruefbar").length;
  return (
    <details className="gegenueber-bereich" open={geprueft > 0 || laeuft}>
      <summary>
        Gegenüberstellung Schriftsatz ↔ Entscheidung
        {geprueft > 0 && <span className="leise"> · {geprueft} geprüft</span>}
        {daten.offen > 0 && <span className="leise"> · {daten.offen} offen</span>}
      </summary>
      <div className="volltexte-laden">
        <button className="zweitrangig" onClick={starte} disabled={laeuft || !daten.modell}>
          {daten.offen > 0 ? `Zitate gegenüberstellen (${daten.offen})` : "Erneut gegenüberstellen"}
        </button>
        <span className="fundort">
          {daten.modell
            ? `Das Sprachmodell (${daten.modell}) prüft je Zitat, ob die zitierte Stelle der Entscheidung den Vortrag trägt. Vorgelegt werden nur die zitierende Stelle und die passenden Randnummern aus dem Volltext.`
            : "Dafür bitte unter „Einstellungen“ ein Sprachmodell wählen."}
        </span>
      </div>
      {laeuft && auftrag && (
        <div className="ki-fortschritt" role="status">
          <div>
            <strong>{auftrag.text}</strong> <span className="leise">· {dauerText(auftrag.sekunden)}</span>
          </div>
          <button className="zweitrangig" onClick={async () => setAuftrag(await kern<KiAuftrag>("ki.abbrechen", { auftrag_id: auftrag.auftrag_id }))}>
            Abbrechen
          </button>
        </div>
      )}
      {fehler && <p className="fehler">{fehler}</p>}
      {daten.zitate.length > 0 && <GegenueberstellungListe zitate={daten.zitate} onFundstelle={onFundstelle} />}
    </details>
  );
}
