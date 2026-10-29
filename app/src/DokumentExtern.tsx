import { useState } from "react";
import Zeichen from "./Symbole";
import { AktenDokument, Arbeitskopie, DokumentFassung, kern, zeitpunkt } from "./kern";

type Ausfuehren = <T>(was: string, f: () => Promise<T>) => Promise<T | undefined>;

const KOPIE_TEXT: Record<Arbeitskopie["status"], string> = {
  unveraendert: "Arbeitskopie geöffnet, noch nicht geändert",
  geaendert: "Arbeitskopie geändert, noch nicht übernommen",
  gesperrt: "Arbeitskopie wird gerade gespeichert",
  fehlt: "Arbeitskopie nicht mehr vorhanden",
};

/**
 * Öffnen und Bearbeiten in externen Programmen, unter der Leiste des geöffneten Dokuments.
 * Öffnen zeigt eine schreibgeschützte Kopie; Bearbeiten legt eine Arbeitskopie an, deren Änderungen
 * JuraBox als neue Fassung übernimmt. Die abgelegten Dateien bleiben unverändert.
 */
export default function DokumentExtern({
  dokument,
  kopie,
  gefragt,
  laeuft,
  ausfuehren,
  onKopien,
  onUebernehmen,
  onMeldung,
}: {
  dokument: AktenDokument;
  kopie: Arbeitskopie | undefined;
  /** Die Übernahme wird gerade oben in der Akte erfragt; dann hier kein zweiter Knopf. */
  gefragt: boolean;
  laeuft: boolean;
  ausfuehren: Ausfuehren;
  /** Arbeitskopien neu laden (nach Bearbeiten oder Verwerfen). */
  onKopien: () => Promise<void>;
  onUebernehmen: (dokumentId: number) => Promise<void>;
  onMeldung: (text: string) => void;
}) {
  const [fassungen, setFassungen] = useState<DokumentFassung[] | null>(null);
  const [verwerfenFrage, setVerwerfenFrage] = useState(false);
  const id = dokument.id;
  const art = dokument.format === "pdf" ? "PDF-Programm" : "Textverarbeitung";

  async function ansehen(nr?: number) {
    const r = await ausfuehren("Öffne …", () =>
      kern<{ programm: string }>("akten.extern_ansehen", { dokument_id: id, nr: nr ?? null }),
    );
    if (r) onMeldung(`Schreibgeschützte Kopie${nr ? ` von Fassung ${nr}` : ""} an ${art} übergeben.`);
  }

  async function bearbeiten() {
    const r = await ausfuehren("Öffne Arbeitskopie …", () =>
      kern<{ neu: boolean }>("akten.extern_bearbeiten", { dokument_id: id }),
    );
    if (!r) return;
    await onKopien();
    onMeldung(
      (r.neu ? "Arbeitskopie angelegt und geöffnet." : "Vorhandene Arbeitskopie wieder geöffnet.") +
        " Nach dem Speichern fragt JuraBox, ob die Änderungen als neue Fassung übernommen werden sollen.",
    );
  }

  async function verwerfen() {
    setVerwerfenFrage(false);
    const r = await ausfuehren("Verwerfe Arbeitskopie …", () => kern("akten.arbeitskopie_verwerfen", { dokument_id: id }));
    if (r) {
      await onKopien();
      onMeldung("Arbeitskopie verworfen. Die übernommenen Fassungen bleiben erhalten.");
    }
  }

  async function fassungenUmschalten() {
    if (fassungen) return setFassungen(null);
    const f = await ausfuehren("Lade Fassungen …", () => kern<DokumentFassung[]>("akten.fassungen", { dokument_id: id }));
    if (f) setFassungen(f);
  }

  return (
    <div className="dok-extern">
      <div className="dok-extern-leiste">
        <button
          className="zweitrangig"
          onClick={() => ansehen()}
          disabled={laeuft}
          title={`Schreibgeschützte Kopie im ${art} öffnen (Einstellungen › Programme)`}
        >
          <Zeichen name="oeffnen" groesse={15} /> Öffnen
        </button>
        <button
          className="zweitrangig"
          onClick={bearbeiten}
          disabled={laeuft}
          title="Arbeitskopie im externen Programm bearbeiten; Änderungen kommen als neue Fassung zurück"
        >
          <Zeichen name="bearbeiten" groesse={15} /> Bearbeiten
        </button>
        <button
          className="zweitrangig"
          onClick={() => ausfuehren("Öffne Ordner …", () => kern("akten.im_ordner_zeigen", { dokument_id: id }))}
          disabled={laeuft}
          title="Zeigt die Arbeitskopie bzw. eine Kopie zum Ansehen im Dateimanager"
        >
          <Zeichen name="ordner" groesse={15} /> Im Ordner zeigen
        </button>
        <button
          className="link klein dok-fassung"
          onClick={fassungenUmschalten}
          aria-expanded={!!fassungen}
          title="Alle Fassungen dieses Dokuments"
        >
          <Zeichen name="fassungen" groesse={14} /> Fassung {dokument.fassung.nr}
          {dokument.fassung.nr > 1 && ` · geändert ${zeitpunkt(dokument.fassung.erstellt_am)}`}
        </button>
      </div>

      {kopie && (
        <div className={`arbeitskopie-zeile ${kopie.status}`}>
          <span>{KOPIE_TEXT[kopie.status]}</span>
          {kopie.status === "geaendert" && !gefragt && (
            <button onClick={() => onUebernehmen(id)} disabled={laeuft}>
              Als Fassung {dokument.fassung.nr + 1} übernehmen
            </button>
          )}
          <button
            className="link klein"
            onClick={() => (kopie.status === "geaendert" ? setVerwerfenFrage(true) : verwerfen())}
            disabled={laeuft}
          >
            Arbeitskopie verwerfen
          </button>
        </div>
      )}
      {verwerfenFrage && (
        <div className="rueckfrage" role="alertdialog" aria-label="Arbeitskopie verwerfen?">
          <strong>Arbeitskopie mit nicht übernommenen Änderungen verwerfen?</strong>
          <p>Die Änderungen seit der letzten Übernahme gehen verloren. Die Fassungen in der Akte bleiben unverändert.</p>
          <div className="aktionen">
            <button className="gefahr-voll" onClick={verwerfen}>
              Verwerfen
            </button>
            <button className="zweitrangig" onClick={() => setVerwerfenFrage(false)} autoFocus>
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {fassungen && (
        <ol className="fassungen" aria-label="Fassungen">
          {fassungen.map((f) => (
            <li key={f.nr}>
              <span>
                <strong>Fassung {f.nr}</strong>
                {f.aktuell && " (aktuell)"}
              </span>
              <span className="leise">
                {f.quelle === "import" ? "eingelesen" : "bearbeitet"} {zeitpunkt(f.erstellt_am)}
              </span>
              <button className="link klein" onClick={() => ansehen(f.nr)} disabled={laeuft}>
                Öffnen
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** Frage nach dem Speichern im externen Programm: Änderungen als neue Fassung übernehmen? */
export function UebernahmeFrage({
  kopien,
  dokumente,
  laeuft,
  onUebernehmen,
  onSpaeter,
}: {
  kopien: Arbeitskopie[];
  dokumente: AktenDokument[];
  laeuft: boolean;
  onUebernehmen: (dokumentId: number) => void;
  onSpaeter: (k: Arbeitskopie) => void;
}) {
  return (
    <>
      {kopien.map((k) => {
        const nr = (dokumente.find((d) => d.id === k.dokument_id)?.fassung.nr ?? k.basis_nr) + 1;
        return (
          <div key={k.dokument_id} className="rueckfrage uebernahme" role="alertdialog" aria-label="Neue Fassung übernehmen?">
            <strong>„{k.dateiname}“ wurde außerhalb von JuraBox geändert.</strong>
            <p>
              Gespeichert {k.geaendert_am ? zeitpunkt(k.geaendert_am) : ""}. Übernehmen legt die Datei als Fassung {nr}{" "}
              ab und liest Text, Normzitate und Datum neu ein. Die bisherigen Fassungen bleiben erhalten.
            </p>
            <div className="aktionen">
              <button onClick={() => onUebernehmen(k.dokument_id)} disabled={laeuft}>
                Als Fassung {nr} übernehmen
              </button>
              <button className="zweitrangig" onClick={() => onSpaeter(k)}>
                Später
              </button>
            </div>
          </div>
        );
      })}
    </>
  );
}
