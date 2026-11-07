import { useState } from "react";
import { open, save } from "@tauri-apps/plugin-dialog";
import { kern, kernImHintergrund } from "./kern";

/** Kopie des Original-PDFs mit den Markierungen als PDF-Anmerkungen (juracore/dokumente/pdf_markiert.py). */

interface Fehlend {
  id: number;
  zitat: string | null;
  seite: number | null;
  grund: string;
  dokument?: string;
}

function fehlendText(f: Fehlend[]): string | null {
  if (f.length === 0) return null;
  const liste = f
    .slice(0, 3)
    .map((x) => `„${(x.zitat ?? "").slice(0, 40)}${(x.zitat ?? "").length > 40 ? " …" : ""}“ (${x.grund})`)
    .join(", ");
  return `${f.length === 1 ? "Eine Markierung fehlt" : `${f.length} Markierungen fehlen`} in der Kopie: ${liste}${f.length > 3 ? " …" : ""}. Diese bitte in der Textansicht prüfen.`;
}

function useAblauf(arbeit: string) {
  const [laeuft, setLaeuft] = useState(false);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [hinweis, setHinweis] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  async function ausfuehren(f: () => Promise<void>) {
    setLaeuft(true);
    setMeldung(null);
    setHinweis(null);
    setFehler(null);
    try {
      await f();
    } catch (e) {
      setFehler(String(e));
    } finally {
      setLaeuft(false);
    }
  }
  const anzeige = (
    <>
      {laeuft && <p className="status" role="status">{arbeit}</p>}
      {meldung && <p className="status" role="status">{meldung}</p>}
      {hinweis && <p className="hinweis">{hinweis}</p>}
      {fehler && <p className="fehler" role="alert">{fehler}</p>}
    </>
  );
  return { laeuft, ausfuehren, setMeldung, setHinweis, anzeige };
}

/** Ein Dokument: Speichern-Dialog, dann die Kopie. */
export function PdfKopieKnopf({ dokumentId }: { dokumentId: number }) {
  const a = useAblauf("PDF wird erstellt …");
  const speichern = () =>
    a.ausfuehren(async () => {
      const { name } = await kern<{ name: string }>("anmerkungen.pdf_name", { dokument_id: dokumentId });
      const ziel = await save({
        title: "PDF mit Markierungen speichern",
        defaultPath: `${name}.pdf`,
        filters: [{ name: "PDF", extensions: ["pdf"] }],
      });
      if (!ziel) return;
      const r = await kern<{ pfad: string; eingezeichnet: number; fehlend: Fehlend[] }>("anmerkungen.pdf", { dokument_id: dokumentId, pfad: ziel });
      a.setMeldung(`${r.eingezeichnet} ${r.eingezeichnet === 1 ? "Markierung" : "Markierungen"} eingezeichnet. Gespeichert unter ${r.pfad}; der Dateimanager zeigt die Datei.`);
      a.setHinweis(fehlendText(r.fehlend));
    });
  return (
    <div className="pdf-kopie">
      <button
        className="link"
        disabled={a.laeuft}
        onClick={() => void speichern()}
        title="Kopie des Original-PDFs; Markierungen und Kommentare erscheinen dort als PDF-Anmerkungen. Das Original bleibt unverändert."
      >
        PDF mit Markierungen speichern …
      </button>
      {a.anzeige}
    </div>
  );
}

/** Ganze Akte: Ordner wählen, je PDF mit ausgewählten Markierungen eine Kopie. */
export function PdfKopienAkte({ akteId, ids }: { akteId: number; ids: number[] }) {
  const a = useAblauf("PDF-Kopien werden erstellt …");
  const speichern = () =>
    a.ausfuehren(async () => {
      const ordner = await open({ directory: true, title: "Ordner für die PDF-Kopien mit Markierungen" });
      if (!ordner || Array.isArray(ordner)) {
        a.setMeldung("Kein Ordner gewählt, nichts gespeichert.");
        return;
      }
      const r = await kernImHintergrund<{ ordner: string; dateien: { dokument: string; eingezeichnet: number }[]; kein_pdf: string[]; fehlend: Fehlend[] }>(
        "anmerkungen.pdf_akte",
        { akte_id: akteId, ordner, ids },
      );
      const n = r.dateien.length;
      a.setMeldung(n ? `${n} ${n === 1 ? "PDF" : "PDFs"} mit Markierungen gespeichert in ${r.ordner}; der Dateimanager zeigt den Ordner.` : "Kein PDF gespeichert.");
      const teile = [
        r.kein_pdf.length ? `Keine PDFs, daher ohne Kopie: ${r.kein_pdf.join(", ")}. Für diese bitte Word oder PDF oben nutzen.` : null,
        fehlendText(r.fehlend),
      ].filter(Boolean);
      a.setHinweis(teile.length ? teile.join(" ") : null);
    });
  return (
    <div className="pdf-kopie">
      <button className="zweitrangig" disabled={a.laeuft || ids.length === 0} onClick={() => void speichern()}>
        PDF-Kopien mit Markierungen …
      </button>
      <p className="leise">
        Je Dokument eine Kopie des Originals, Markierungen und Kommentare als PDF-Anmerkungen; die Originale bleiben unverändert.
      </p>
      {a.anzeige}
    </div>
  );
}
