import { FormEvent, useEffect, useState } from "react";
import { NachrichtenEinstellungen, NachrichtenFeed, kern } from "./kern";

/** Feeds laden nur Schlagzeilen, keine Akteninhalte; http ist daher erlaubt, aber benannt. */
const HTTP_HINWEIS =
  "Die Quelle bietet kein https an; der Feed wird unverschlüsselt geladen. Übertragen werden nur Schlagzeilen, keine Akteninhalte.";

/**
 * Einstellungen, Reiter „Nachrichten“: RSS- und Atom-Feeds für die Startseite. Sobald einer eingetragen ist,
 * erscheint dort unter „Zuletzt geöffnet“ und „Nächste Fristen und Termine“ das Feld „Nachrichten“.
 */
export default function Nachrichten() {
  const [e, setE] = useState<NachrichtenEinstellungen | null>(null);
  const [adresse, setAdresse] = useState("");
  const [laeuft, setLaeuft] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    void kern<NachrichtenEinstellungen>("nachrichten.einstellungen").then(setE, (f) => setFehler(String(f)));
  }, []);

  async function hinzufuegen(url: string, titel = "") {
    setLaeuft(url);
    setFehler(null);
    setMeldung(null);
    try {
      const r = await kern<NachrichtenEinstellungen & { neu: NachrichtenFeed; eintraege: number }>(
        "nachrichten.hinzufuegen",
        { url, titel },
      );
      setE(r);
      setAdresse("");
      setMeldung(
        `„${r.neu.titel}“ hinzugefügt (${r.eintraege} ${r.eintraege === 1 ? "Eintrag" : "Einträge"}).` +
          (r.neu.url !== url.trim() ? ` Gefunden unter ${r.neu.url}.` : "") +
          (r.neu.url.startsWith("http://") ? ` ${HTTP_HINWEIS}` : ""),
      );
    } catch (f) {
      setFehler(String(f));
    } finally {
      setLaeuft(null);
    }
  }

  async function aendern(methode: string, params: Record<string, unknown>) {
    setFehler(null);
    setMeldung(null);
    try {
      setE(await kern<NachrichtenEinstellungen>(methode, params));
    } catch (f) {
      setFehler(String(f));
    }
  }

  function absenden(ev: FormEvent) {
    ev.preventDefault();
    if (adresse.trim()) void hinzufuegen(adresse);
  }

  const offen = e?.vorschlaege.filter((v) => !v.eingetragen) ?? [];

  return (
    <>
      <p className="erklaerung">
        Nachrichten aus RSS- oder Atom-Feeds erscheinen auf der Startseite unter „Zuletzt geöffnet“ und „Nächste Fristen
        und Termine“, sobald mindestens ein Feed eingetragen ist. Die App lädt nur diese Adressen und sendet dabei nichts
        aus Akten oder Dokumenten. Die Feeds gelten für dieses Gerät.
      </p>

      <section className="karte">
        <h2>Eigene Feeds</h2>
        {e && e.feeds.length === 0 && <p className="leer">Noch kein Feed eingetragen; die Startseite zeigt keine Nachrichten.</p>}
        {e && e.feeds.length > 0 && (
          <ul className="feed-liste">
            {e.feeds.map((f) => (
              <FeedZeile
                key={f.id}
                feed={f}
                onUmbenennen={(titel) => void aendern("nachrichten.umbenennen", { feed_id: f.id, titel })}
                onEntfernen={() => void aendern("nachrichten.entfernen", { feed_id: f.id })}
              />
            ))}
          </ul>
        )}
        <form className="feed-formular" onSubmit={absenden}>
          <label>
            Adresse des Feeds oder der Webseite
            <input
              value={adresse}
              placeholder="z. B. https://www.lto.de/rss"
              onChange={(ev) => setAdresse(ev.target.value)}
              disabled={!!laeuft}
            />
          </label>
          <button type="submit" disabled={!!laeuft || !adresse.trim()}>
            Hinzufügen
          </button>
        </form>
        <p className="grenze">
          Statt der Feed-Adresse genügt meist die Seite, die auf den Feed verweist: Die App lädt sie und nimmt den ersten
          Feed, den sie dort findet.
        </p>
        {laeuft && <p className="status" role="status">Prüfe {laeuft} …</p>}
        {meldung && <p className="gut">{meldung}</p>}
        {fehler && <p className="fehler" role="alert">{fehler}</p>}
      </section>

      {offen.length > 0 && (
        <section className="karte">
          <h2>Vorschläge</h2>
          <p className="erklaerung">Diese Feeds waren beim Einbau (Oktober 2026) abrufbar.</p>
          <ul className="feed-liste">
            {offen.map((v) => (
              <li key={v.url}>
                <div>
                  <strong>{v.titel}</strong>
                  <span className="leise">{v.hinweis}</span>
                  <code className="feed-url">{v.url}</code>
                </div>
                <button className="zweitrangig" disabled={!!laeuft} onClick={() => void hinzufuegen(v.url, v.titel)}>
                  Hinzufügen
                </button>
              </li>
            ))}
          </ul>
          <p className="grenze">
            Feeds von Bundesverfassungsgericht oder Bundesgesetzblatt ließen sich beim Einbau nicht prüfen und fehlen
            deshalb hier. Wer auf deren Webseiten einen Feed findet, trägt dessen Adresse oben ein.
          </p>
        </section>
      )}
    </>
  );
}

function FeedZeile({
  feed,
  onUmbenennen,
  onEntfernen,
}: {
  feed: NachrichtenFeed;
  onUmbenennen: (titel: string) => void;
  onEntfernen: () => void;
}) {
  const [titel, setTitel] = useState(feed.titel);
  useEffect(() => setTitel(feed.titel), [feed.titel]);
  return (
    <li>
      <div>
        <input
          className="feed-titel"
          value={titel}
          aria-label="Name des Feeds"
          onChange={(ev) => setTitel(ev.target.value)}
          onBlur={() => titel.trim() && titel !== feed.titel && onUmbenennen(titel)}
        />
        <code className="feed-url">{feed.url}</code>
        {feed.url.startsWith("http://") && (
          <span className="feld-hinweis warnhinweis" title={HTTP_HINWEIS}>
            unverschlüsselt (http)
          </span>
        )}
      </div>
      <button className="zweitrangig" onClick={onEntfernen}>
        Entfernen
      </button>
    </li>
  );
}
