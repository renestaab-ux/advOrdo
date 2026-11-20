import { useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { kern } from "./kern";

/** Was als Markdown gespeichert wird: genau eines von Gesetz (mit Fassung), Dokument der Akte oder Urteil. */
export type MarkdownQuelle =
  | { gesetz: string; fassung_id?: number }
  | { dokument_id: number }
  | { urteil_id: number };

/**
 * Knopf „Markdown …“: schlägt den Dateinamen vor (Gesetze: „BGB_Buergerliches-Gesetzbuch_Stand-2026-10-09.md“),
 * öffnet den Speichern-Dialog und lässt den Kern die Datei schreiben. Der Wortlaut bleibt unverändert; Fundstellen
 * (Seite, Randnummer, Fassung) stehen in der Datei.
 */
export default function MarkdownKnopf({
  quelle,
  text = "Markdown …",
  was,
  className = "zweitrangig klein",
  gesperrt,
}: {
  quelle: MarkdownQuelle;
  text?: string;
  /** Für den Titel des Speichern-Dialogs, z. B. „Gesetz“ oder „Dokument“. */
  was: string;
  className?: string;
  gesperrt?: boolean;
}) {
  const [laeuft, setLaeuft] = useState(false);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  async function speichern() {
    setFehler(null);
    setMeldung(null);
    setLaeuft(true);
    try {
      const vorschlag = await kern<{ name: string; warnung: string | null }>("markdown.name", quelle);
      const ziel = await save({
        title: `${was} als Markdown speichern`,
        defaultPath: vorschlag.name,
        filters: [{ name: "Markdown", extensions: ["md"] }],
      });
      if (!ziel) return;
      const r = await kern<{ pfad: string; warnung: string | null }>("markdown.speichern", { ...quelle, pfad: ziel });
      setMeldung(`Gespeichert unter ${r.pfad}${r.warnung ? `. Achtung: ${r.warnung}` : ""}`);
    } catch (e) {
      setFehler(String(e));
    } finally {
      setLaeuft(false);
    }
  }

  return (
    <>
      <button
        className={className}
        disabled={laeuft || gesperrt}
        onClick={speichern}
        title={`${was} als Markdown-Datei speichern, z. B. für eine Wissenssammlung oder ein Sprachmodell. Der Wortlaut bleibt unverändert.`}
      >
        {text}
      </button>
      {meldung && (
        <span className="status markdown-meldung" role="status">
          {meldung}
        </span>
      )}
      {fehler && (
        <span className="fehler markdown-meldung" role="alert">
          {fehler}
        </span>
      )}
    </>
  );
}
