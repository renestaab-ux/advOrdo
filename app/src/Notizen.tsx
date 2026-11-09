import { FormEvent, useEffect, useState } from "react";
import { AktenDokument, Notiz, dokumentName, kern, zeitpunkt } from "./kern";
import { LeerHinweis } from "./Symbole";
import { useBearbeitung } from "./ungespeichert";
import { useFremdeAenderung } from "./aenderungen";
import { protokollLesen } from "./terminsprotokoll";

/** Reiter „Notizen“: kurze Vermerke zur Akte oder zu einem Dokument; wichtige werden oben angeheftet.
 *  Mit ``dokumentId`` (Ansicht „Details“) nur die Notizen zu diesem Dokument, neue gehören zu ihm. */
export default function Notizen({
  akteId,
  dokumentId: festesDokument,
  onDokument,
}: {
  akteId: number;
  dokumentId?: number;
  /** Öffnet ein Dokument (Verweise im Terminsprotokoll); ohne Angabe sind die Verweise schlichter Text. */
  onDokument?: (dokumentId: number) => void;
}) {
  const neuBearb = useBearbeitung("Neue Notiz");
  const notizBearb = useBearbeitung("Notiz");
  const [alle, setNotizen] = useState<Notiz[] | null>(null);
  const notizen = festesDokument == null ? alle : (alle?.filter((n) => n.dokument_id === festesDokument) ?? null);
  const [dokumente, setDokumente] = useState<AktenDokument[]>([]);
  const [text, setText] = useState("");
  const [dokumentId, setDokumentId] = useState("");
  const [anheften, setAnheften] = useState(false);
  const [bearbeitet, setBearbeitet] = useState<{ id: number; text: string } | null>(null);
  const [loeschfrage, setLoeschfrage] = useState<Notiz | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    void kern<Notiz[]>("akten.notizen", { akte_id: akteId }).then(setNotizen, (e) => setFehler(String(e)));
    if (festesDokument == null)
      void kern<AktenDokument[]>("akten.dokumente", { akte_id: akteId }).then(setDokumente, () => undefined);
  }, [akteId, festesDokument]);
  // Notizen aus einem anderen Fenster (Arbeitsfenster der Akte oder Hauptfenster).
  useFremdeAenderung(["notizen"], () => {
    void kern<Notiz[]>("akten.notizen", { akte_id: akteId }).then(setNotizen, (e) => setFehler(String(e)));
  });

  async function mit(f: () => Promise<Notiz[]>) {
    setFehler(null);
    try {
      setNotizen(await f());
      return true;
    } catch (e) {
      setFehler(String(e));
      return false;
    }
  }

  async function hinzufuegen(e: FormEvent) {
    e.preventDefault();
    const ok = await mit(() =>
      kern<Notiz[]>("akten.notiz_speichern", {
        akte_id: akteId,
        text,
        dokument_id: festesDokument ?? (dokumentId ? Number(dokumentId) : null),
        angeheftet: anheften,
      }),
    );
    if (ok) {
      setText("");
      setAnheften(false);
    }
  }

  return (
    <div className="notizen">
      <form {...neuBearb.formular} className="karte notiz-neu" onSubmit={hinzufuegen}>
        <label className="feld">
          {festesDokument == null ? "Neue Notiz" : "Neue Notiz zu diesem Dokument"}
          <textarea
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="z. B. Telefonat mit dem Mandanten: Vergleich bis 8.000 € denkbar."
          />
        </label>
        <div className="notiz-optionen">
          {festesDokument == null && (
            <label>
              Zu Dokument{" "}
              <select value={dokumentId} onChange={(e) => setDokumentId(e.target.value)}>
                <option value="">(zur ganzen Akte)</option>
                {dokumente.map((d) => (
                  <option key={d.id} value={d.id}>
                    {dokumentName(d)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            <input type="checkbox" checked={anheften} onChange={(e) => setAnheften(e.target.checked)} /> oben anheften
          </label>
          <button type="submit" disabled={!text.trim()}>
            Notiz speichern
          </button>
        </div>
      </form>

      {fehler && <p className="fehler" role="alert">{fehler}</p>}
      {notizen && notizen.length === 0 && (
        <LeerHinweis symbol="notizen">
          {festesDokument == null ? "Noch keine Notizen." : "Noch keine Notiz zu diesem Dokument."}
        </LeerHinweis>
      )}
      {loeschfrage && (
        <div className="rueckfrage" role="alertdialog" aria-label="Notiz löschen?">
          <strong>Diese Notiz löschen?</strong>
          <p>{loeschfrage.text.slice(0, 160)}</p>
          <div className="aktionen">
            <button
              className="gefahr-voll"
              onClick={() => {
                setLoeschfrage(null);
                void mit(() => kern<Notiz[]>("akten.notiz_loeschen", { notiz_id: loeschfrage.id }));
              }}
            >
              Löschen
            </button>
            <button className="zweitrangig" onClick={() => setLoeschfrage(null)} autoFocus>
              Abbrechen
            </button>
          </div>
        </div>
      )}
      <ul className="notiz-liste">
        {notizen?.map((n) => (
          <li key={n.id} className={n.angeheftet ? "notiz angeheftet" : "notiz"}>
            {bearbeitet?.id === n.id ? (
              <form {...notizBearb.formular}
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (
                    await mit(() =>
                      kern<Notiz[]>("akten.notiz_speichern", { akte_id: akteId, text: bearbeitet.text, notiz_id: n.id }),
                    )
                  )
                    setBearbeitet(null);
                }}
              >
                <textarea rows={3} value={bearbeitet.text} onChange={(e) => setBearbeitet({ id: n.id, text: e.target.value })} autoFocus />
                <span className="aktionen">
                  <button type="submit" disabled={!bearbeitet.text.trim()}>
                    Speichern
                  </button>
                  <button type="button" className="zweitrangig" onClick={() => setBearbeitet(null)}>
                    Abbrechen
                  </button>
                </span>
              </form>
            ) : (
              <>
                <NotizText text={n.text} dokumente={dokumente} onDokument={onDokument} />
                <div className="notiz-fuss">
                  <span className="leise klein">
                    {n.angeheftet && "📌 angeheftet · "}
                    {zeitpunkt(n.geaendert_am)}
                    {n.dokument && festesDokument == null && ` · zu ${n.dokument}`}
                    {n.zeiteintrag &&
                      ` · zur Zeiterfassung ${n.zeiteintrag.slice(8, 10)}.${n.zeiteintrag.slice(5, 7)}.${n.zeiteintrag.slice(0, 4)}${n.zeiteintrag.slice(10)}`}
                  </span>
                  <span className="aktionen">
                    <button
                      className="link klein"
                      onClick={() => void mit(() => kern<Notiz[]>("akten.notiz_anheften", { notiz_id: n.id, angeheftet: !n.angeheftet }))}
                    >
                      {n.angeheftet ? "Lösen" : "Anheften"}
                    </button>
                    <button className="link klein" onClick={() => setBearbeitet({ id: n.id, text: n.text })}>
                      Bearbeiten
                    </button>
                    <button className="link klein gefahr" onClick={() => setLoeschfrage(n)}>
                      Löschen
                    </button>
                  </span>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Text einer Notiz; ein Terminsprotokoll erscheint so gegliedert wie im Terminmodus. */
function NotizText({
  text,
  dokumente,
  onDokument,
}: {
  text: string;
  dokumente: AktenDokument[];
  onDokument?: (dokumentId: number) => void;
}) {
  const p = protokollLesen(text);
  if (!p) return <p className="notiz-text">{text}</p>;
  return (
    <div className="notiz-text terminsprotokoll">
      <p className="tp-kopf">{p.kopf}</p>
      <ol className="af-tn-liste">
        {p.eintraege.map((e, i) => (
          <li key={i}>
            <time>{e.zeit}</time>
            <div>
              {e.art && <strong>{e.art}: </strong>}
              {e.text}
              {e.bezug && <ProtokollBezug name={e.bezug} dokumente={dokumente} onDokument={onDokument} />}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Dokumentverweis einer Protokollzeile: Link, wenn das Dokument in der Akte zu finden ist, sonst schlichter Text. */
function ProtokollBezug({
  name,
  dokumente,
  onDokument,
}: {
  name: string;
  dokumente: AktenDokument[];
  onDokument?: (dokumentId: number) => void;
}) {
  const d = dokumente.find((x) => x.titel === name) ?? dokumente.find((x) => x.dateiname === name || dokumentName(x) === name);
  if (!d || !onDokument)
    return (
      <span className="tp-bezug-text" title={d ? undefined : "Dieses Dokument ist nicht mehr in der Akte."}>
        {" "}
        ↳ {name}
      </span>
    );
  return (
    <>
      {" "}
      <button className="link tp-bezug" onClick={() => onDokument(d.id)} title="Dokument öffnen">
        ↳ {name}
      </button>
    </>
  );
}
