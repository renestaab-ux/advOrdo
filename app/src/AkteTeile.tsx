import { OrdnerFrage } from "./Akte";
import { AktenDokument, BETEILIGTE, STATUS_TEXT, ZitatStatus, dokumentDatum, tagsAusText } from "./kern";

export function OrdnerRueckfrage({
  frage,
  onTags,
  onEinlesen,
  onAbbrechen,
}: {
  frage: OrdnerFrage;
  onTags: (herkunft: string, text: string) => void;
  onEinlesen: (mitTags: boolean) => void;
  onAbbrechen: () => void;
}) {
  const { funde } = frage;
  return (
    <div className="rueckfrage" role="dialog" aria-label="Ordner einlesen">
      <strong>
        Ordner „{funde.name}“: {funde.dateien.length} Dateien in {funde.unterordner.length}{" "}
        {funde.unterordner.length === 1 ? "Ordner" : "Ordnern"}
      </strong>
      <p>
        Aus den Ordnernamen lassen sich Tags ableiten, die zeigen, zu welchem Beteiligten ein Dokument gehört. Sollen sie
        übernommen werden? Du kannst die Vorschläge hier anpassen (mehrere mit Komma trennen) und später jederzeit ändern.
      </p>
      <table className="dokumente">
        <thead>
          <tr>
            <th>Ordner</th>
            <th>Dateien</th>
            <th>Tags</th>
          </tr>
        </thead>
        <tbody>
          {funde.unterordner.map((u) => (
            <tr key={u.herkunft}>
              <td>{u.herkunft || <span className="leer">(oberste Ebene)</span>}</td>
              <td>{u.dateien}</td>
              <td>
                <input
                  className="tag-eingabe"
                  value={frage.tags[u.herkunft] ?? ""}
                  onChange={(e) => onTags(u.herkunft, e.target.value)}
                  placeholder="kein Tag"
                  aria-label={`Tags für ${u.herkunft || "oberste Ebene"}`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {funde.uebersprungen.length > 0 && (
        <p className="hinweis" title={funde.uebersprungen.join("\n")}>
          {funde.uebersprungen.length} Dateien in anderen Formaten werden übersprungen (z. B. {funde.uebersprungen[0]}).
        </p>
      )}
      <div className="aktionen">
        <button onClick={() => onEinlesen(true)}>Mit diesen Tags einlesen</button>
        <button className="zweitrangig" onClick={() => onEinlesen(false)}>
          Ohne Tags einlesen
        </button>
        <button className="zweitrangig" onClick={onAbbrechen}>
          Abbrechen
        </button>
      </div>
    </div>
  );
}

export function TagEditor({
  text,
  onText,
  onSpeichern,
  onAbbrechen,
}: {
  text: string;
  onText: (t: string) => void;
  onSpeichern: () => void;
  onAbbrechen: () => void;
}) {
  const gesetzt = tagsAusText(text);
  const ergaenze = (name: string) => onText(tagsAusText(`${text}, ${name}`).join(", "));
  return (
    <form
      className="tag-editor"
      onSubmit={(e) => {
        e.preventDefault();
        onSpeichern();
      }}
    >
      <input
        className="tag-eingabe"
        value={text}
        onChange={(e) => onText(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && onAbbrechen()}
        placeholder="z. B. Kläger, Anlage K 1"
        aria-label="Tags, mit Komma getrennt"
        autoFocus
      />
      <div className="tags">
        {BETEILIGTE.filter((b) => !gesetzt.includes(b)).map((b) => (
          <button key={b} type="button" className="tag-wahl" onClick={() => ergaenze(b)}>
            + {b}
          </button>
        ))}
      </div>
      <div className="aktionen">
        <button type="submit">Speichern</button>
        <button type="button" className="zweitrangig" onClick={onAbbrechen}>
          Abbrechen
        </button>
      </div>
    </form>
  );
}

/** Datum in der Dokumentliste: Wert und Herkunft; die Datumszeile öffnet das Dokument an ihrer Fundstelle. */
export function DokumentDatum({ d, onFundstelle }: { d: AktenDokument; onFundstelle: () => void }) {
  const angabe = dokumentDatum(d);
  if (!d.datum) return <span title={angabe.erklaerung}>–</span>;
  return (
    <div className="dok-datum" title={angabe.erklaerung}>
      {d.datum_quelle === "dokument" && d.datum_abschnitt != null ? (
        <button className="link" onClick={onFundstelle}>
          {angabe.text}
        </button>
      ) : (
        angabe.text
      )}
      <div className="herkunft">{angabe.herkunft}</div>
    </div>
  );
}

/** Zahl der Normzitate je Prüfstand; „kurz“ zeigt nur die Zahlen, der Text steht im Tooltip. */
export function ZitatZaehlung({ zitate, kurz = false }: { zitate: Partial<Record<ZitatStatus, number>>; kurz?: boolean }) {
  const reihenfolge: ZitatStatus[] = ["belegt", "nicht_gefunden", "unbekanntes_gesetz"];
  const teile = reihenfolge.filter((s) => zitate[s]);
  if (teile.length === 0) return <span className="leer">{kurz ? "–" : "keine"}</span>;
  return (
    <span className={kurz ? "zitat-kurz" : undefined}>
      {teile.map((s) => (
        <span key={s} className={`zitat-zahl ${s}`} title={kurz ? `${zitate[s]} ${STATUS_TEXT[s]}` : undefined}>
          {kurz ? zitate[s] : `${zitate[s]} ${STATUS_TEXT[s]}`}
        </span>
      ))}
    </span>
  );
}

/** Hinweise zur Einrichtung (Texterkennung, Wissensbasis) in einer einzigen, eingeklappten Zeile. */
export function EinrichtungsHinweise({ hinweise }: { hinweise: ({ titel: string; text: string } | null)[] }) {
  const da = hinweise.filter((h): h is { titel: string; text: string } => h != null);
  if (da.length === 0) return null;
  if (da.length === 1)
    return (
      <details className="hinweis kurz-hinweis">
        <summary>{da[0].titel}</summary>
        {da[0].text}
      </details>
    );
  return (
    <details className="hinweis kurz-hinweis">
      <summary>{da.length} Hinweise zur Einrichtung</summary>
      {da.map((h) => (
        <p key={h.titel}>
          <strong>{h.titel}:</strong> {h.text}
        </p>
      ))}
    </details>
  );
}
