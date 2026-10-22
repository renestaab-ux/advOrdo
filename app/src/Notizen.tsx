import { FormEvent, useEffect, useState } from "react";
import { AktenDokument, Notiz, kern, zeitpunkt } from "./kern";

/** Reiter „Notizen“: kurze Vermerke zur Akte oder zu einem Dokument; wichtige werden oben angeheftet. */
export default function Notizen({ akteId }: { akteId: number }) {
  const [notizen, setNotizen] = useState<Notiz[] | null>(null);
  const [dokumente, setDokumente] = useState<AktenDokument[]>([]);
  const [text, setText] = useState("");
  const [dokumentId, setDokumentId] = useState("");
  const [anheften, setAnheften] = useState(false);
  const [bearbeitet, setBearbeitet] = useState<{ id: number; text: string } | null>(null);
  const [loeschfrage, setLoeschfrage] = useState<Notiz | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    void kern<Notiz[]>("akten.notizen", { akte_id: akteId }).then(setNotizen, (e) => setFehler(String(e)));
    void kern<AktenDokument[]>("akten.dokumente", { akte_id: akteId }).then(setDokumente, () => undefined);
  }, [akteId]);

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
        dokument_id: dokumentId ? Number(dokumentId) : null,
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
      <form className="karte notiz-neu" onSubmit={hinzufuegen}>
        <label className="feld">
          Neue Notiz
          <textarea
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="z. B. Telefonat mit dem Mandanten: Vergleich bis 8.000 € denkbar."
          />
        </label>
        <div className="notiz-optionen">
          <label>
            Zu Dokument{" "}
            <select value={dokumentId} onChange={(e) => setDokumentId(e.target.value)}>
              <option value="">(zur ganzen Akte)</option>
              {dokumente.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.dateiname}
                </option>
              ))}
            </select>
          </label>
          <label>
            <input type="checkbox" checked={anheften} onChange={(e) => setAnheften(e.target.checked)} /> oben anheften
          </label>
          <button type="submit" disabled={!text.trim()}>
            Notiz speichern
          </button>
        </div>
      </form>

      {fehler && <p className="fehler">{fehler}</p>}
      {notizen && notizen.length === 0 && <p className="leer">Noch keine Notizen.</p>}
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
              <form
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
                <p className="notiz-text">{n.text}</p>
                <div className="notiz-fuss">
                  <span className="leise klein">
                    {n.angeheftet && "📌 angeheftet · "}
                    {zeitpunkt(n.geaendert_am)}
                    {n.dokument && ` · zu ${n.dokument}`}
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
