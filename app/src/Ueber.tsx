import { useEffect, useState } from "react";
import { getTauriVersion, getVersion } from "@tauri-apps/api/app";
import logo from "./bilder/advordo-logo.png";
import { istDesktop } from "./kern";

/** Wer die Rechte an advOrdo hält (Urhebervermerk nach Art. 5 EUPL). */
export const RECHTEINHABER = "René Staab";
export const KONTAKT = "advordo@staab.legal";
export const ERSTES_JAHR = 2026;

/** Öffentliche Quellen, aus denen advOrdo Rechtstexte, Gerichtsdaten und Nachrichten lädt, mit ihren Hinweisen. */
export const QUELLEN: { name: string; adresse: string; inhalt: string; hinweis: string }[] = [
  {
    name: "Gesetze im Internet",
    adresse: "gesetze-im-internet.de",
    inhalt: "Bundesgesetze und -verordnungen",
    hinweis: "Konsolidierte, nichtamtliche Fassung.",
  },
  {
    name: "Bürgerservice BAYERN.RECHT",
    adresse: "gesetze-bayern.de",
    inhalt: "Bayerisches Landesrecht und Rechtsprechung",
    hinweis:
      "Nichtamtliche Fassung; maßgeblich ist das Gesetz- und Verordnungsblatt. Entscheidungen redaktionell bearbeitet und anonymisiert.",
  },
  {
    name: "EUR-Lex und Amtsblatt der EU",
    adresse: "eur-lex.europa.eu, publications.europa.eu",
    inhalt: "Unionsrecht (z. B. DSGVO, EuGVVO, Rom I und II)",
    hinweis:
      "Fassung des Amtsblatts ohne spätere Änderungen. © Europäische Union; Weiterverwendung mit Quellenangabe erlaubt (Beschluss 2011/833/EU).",
  },
  {
    name: "Rechtsinformationsportal des Bundes (Testphase)",
    adresse: "testphase.rechtsinformationen.bund.de",
    inhalt: "Rechtsprechung des Bundes",
    hinweis: "Testphase, ohne Gewähr, kein amtlicher Text.",
  },
  {
    name: "Rechtsprechung im Internet",
    adresse: "rechtsprechung-im-internet.de",
    inhalt: "Entscheidungen der Bundesgerichte",
    hinweis: "Gesendet werden nur die eingegebenen Suchbegriffe.",
  },
  {
    name: "XRepository",
    adresse: "xrepository.de",
    inhalt: "Codeliste der Gerichte (XJustiz)",
    hinweis: "Nur Schlüssel und Namen der Gerichte.",
  },
  {
    name: "Orts- und Gerichtsverzeichnis der Justiz",
    adresse: "justizadressen.nrw.de",
    inhalt: "Anschriften und Zuständigkeiten der Gerichte",
    hinweis: "Abgefragt werden nur Postleitzahl und Ort.",
  },
  {
    name: "Nachrichten-Feeds",
    adresse: "nur die in den Einstellungen eingetragenen Adressen",
    inhalt: "Überschriften und Anreißer, z. B. von LTO, beck-aktuell, BGH, BAG",
    hinweis: "Die Beiträge gehören ihren Anbietern. Ohne eingetragenen Feed lädt advOrdo nichts.",
  },
];

/** Bestandteile Dritter mit ihrer Lizenz. Neue Abhängigkeiten hier ergänzen (siehe CONTRIBUTING.md). */
export const BESTANDTEILE: { name: string; zweck: string; lizenz: string }[] = [
  { name: "Tauri 2 mit den Erweiterungen Dialog und Mitteilungen", zweck: "Programmfenster", lizenz: "MIT oder Apache-2.0" },
  { name: "React", zweck: "Oberfläche", lizenz: "MIT" },
  { name: "serde, serde_json", zweck: "Datenaustausch zwischen Fenster und Kern", lizenz: "MIT oder Apache-2.0" },
  { name: "Python", zweck: "Analysekern (im Installer enthalten)", lizenz: "PSF License" },
  { name: "pypdfium2 mit PDFium", zweck: "PDF lesen und für die Texterkennung aufbereiten", lizenz: "Apache-2.0 oder BSD-3-Clause; PDFium: BSD-3-Clause" },
  { name: "truststore", zweck: "Zertifikate des Systems für sichere Verbindungen", lizenz: "MIT" },
  { name: "keyring", zweck: "API-Schlüssel im Schlüsselbund des Systems", lizenz: "MIT" },
  { name: "Liberation Sans 2.1.5", zweck: "Schrift der PDF-Ausgabe; © 2010 Google, © 2012 Red Hat", lizenz: "SIL Open Font License 1.1" },
  { name: "Adobe Core14 AFM (Helvetica)", zweck: "Zeichenbreiten für PDF-Standardschriften; die Schrift selbst wird nicht mitgeliefert", lizenz: "Nutzungsbedingungen von Adobe für die AFM-Dateien" },
  { name: "Tesseract OCR", zweck: "Texterkennung für Scans, separat installiert", lizenz: "Apache-2.0" },
];

function jahre(): string {
  const jetzt = new Date().getFullYear();
  return jetzt > ERSTES_JAHR ? `${ERSTES_JAHR}–${jetzt}` : String(ERSTES_JAHR);
}

/** Einstellungen → Über advOrdo: Programm, Name, Grundsätze, Rechte, Quellen und Bestandteile Dritter. */
export default function Ueber() {
  const [version, setVersion] = useState<string>(__APP_VERSION__);
  const [tauri, setTauri] = useState<string | null>(null);

  useEffect(() => {
    if (!istDesktop) return;
    void getVersion().then(setVersion, () => undefined);
    void getTauriVersion().then(setTauri, () => undefined);
  }, []);

  return (
    <div className="ueber">
      <section className="karte ueber-kopf">
        <div className="ueber-logo">
          <img src={logo} alt="advOrdo" />
        </div>
        <div>
          <h2>advOrdo</h2>
          <p className="ueber-leitsatz">Ordnung für die Anwaltsarbeit</p>
          <dl className="ueber-daten">
            <dt>Version</dt>
            <dd>{version}</dd>
            {tauri && (
              <>
                <dt>Tauri</dt>
                <dd>{tauri}</dd>
              </>
            )}
            <dt>Lizenz</dt>
            <dd>EUPL-1.2</dd>
            <dt>Kontakt</dt>
            <dd>{KONTAKT}</dd>
          </dl>
        </div>
      </section>

      <section className="karte">
        <h2>Was advOrdo ist</h2>
        <p>
          advOrdo analysiert, vergleicht und fasst Schriftsätze, Schreiben und Urteile zusammen und führt Akten, Fristen,
          Termine und Zeiten. Grundlage ist eine versionierte Wissensbasis aus Gesetzen und Rechtsprechung.
        </p>
        <p>
          <strong>Der Name:</strong> „advO“ steht für <i lang="la">advocatus</i>, lateinisch für den Anwalt, „Ordo“ für
          lateinisch <i lang="la">ordo</i>, die Ordnung. Das große O ist doppelt besetzt: Es schließt „Advo“ ab und
          beginnt „Ordo“. advOrdo bringt also Ordnung in die Anwaltsarbeit: Akten, Fristen, Belege und Rechtsquellen an
          einem Ort.
        </p>
        <h3>Grundsätze</h3>
        <ul>
          <li>
            <strong>Beleg vor Behauptung.</strong> Jede Aussage verweist auf eine Fundstelle im Dokument oder auf eine
            Norm mit Fassungsstand. Fehlt ein Beleg, sagt advOrdo das.
          </li>
          <li>
            <strong>Die Daten bleiben auf dem Gerät.</strong> Dokumentinhalte verlassen es nur, wenn Sie ausdrücklich
            eine externe KI einbinden. Ohne Rückfrage lädt advOrdo nur öffentliche Rechtsquellen. Der Kern öffnet keinen
            Netzwerkanschluss.
          </li>
          <li>
            <strong>Rechtsquellen bleiben unverändert.</strong> Jede geladene Fassung wird mit ihrer SHA-256-Prüfsumme
            archiviert; ältere Fassungen werden nie überschrieben.
          </li>
        </ul>
      </section>

      <section className="karte">
        <h2>Rechte und Lizenz</h2>
        <p>
          © {jahre()} {RECHTEINHABER}. advOrdo steht unter der <strong>Europäischen Union Public Licence, Version 1.2</strong>{" "}
          (EUPL-1.2). Sie dürfen das Programm nutzen, untersuchen, verändern und weitergeben; wer eine veränderte Fassung
          weitergibt, muss deren Quelltext unter der EUPL oder einer vereinbaren Lizenz zugänglich machen.
        </p>
        <p>
          Die EUPL ist in allen Amtssprachen der EU gleichermaßen verbindlich. Die deutsche Fassung steht im Amtsblatt
          der EU: Durchführungsbeschluss (EU) 2017/863 der Kommission vom 18. Mai 2017, ABl. L 128 vom 19.5.2017, S. 59
          (eur-lex.europa.eu/eli/dec_impl/2017/863/oj). Der Lizenztext liegt dem Programm als Datei <code>LICENSE</code>{" "}
          bei.
        </p>
        <p>
          <strong>Gewährleistung und Haftung:</strong> advOrdo wird ohne Gewähr bereitgestellt (Art. 7 EUPL); die Haftung
          ist nach Art. 8 EUPL ausgeschlossen, soweit das Gesetz es zulässt. advOrdo ersetzt keine anwaltliche Prüfung:
          Ergebnisse, insbesondere solche eines Sprachmodells, sind vor ihrer Verwendung an den genannten Fundstellen zu
          prüfen.
        </p>
        <p>
          <strong>Name und Logo:</strong> „advOrdo“ und das Logo sind von der Lizenz nicht umfasst (Art. 5 EUPL, Schutz
          der Rechte). Veränderte Fassungen bitte unter anderem Namen weitergeben.
        </p>
      </section>

      <section className="karte">
        <h2>Rechtsquellen und Daten aus dem Netz</h2>
        <p className="erklaerung">
          Welche Abrufe tatsächlich stattgefunden haben, zeigt das Netzprotokoll unter Einstellungen → Diagnose.
        </p>
        <div className="tabelle-rahmen">
          <table className="ueber-tabelle">
            <caption className="unsichtbar">Quellen, aus denen advOrdo Daten lädt</caption>
            <thead>
              <tr>
                <th scope="col">Quelle</th>
                <th scope="col">Inhalt</th>
                <th scope="col">Hinweis</th>
              </tr>
            </thead>
            <tbody>
              {QUELLEN.map((q) => (
                <tr key={q.name}>
                  <th scope="row">
                    {q.name}
                    <span className="ueber-adresse">{q.adresse}</span>
                  </th>
                  <td>{q.inhalt}</td>
                  <td>{q.hinweis}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="karte">
        <h2>Bestandteile Dritter</h2>
        <p className="erklaerung">Sie behalten ihre eigenen Lizenzen. Die wichtigsten:</p>
        <div className="tabelle-rahmen">
          <table className="ueber-tabelle">
            <caption className="unsichtbar">Bestandteile Dritter und ihre Lizenzen</caption>
            <thead>
              <tr>
                <th scope="col">Bestandteil</th>
                <th scope="col">Wofür</th>
                <th scope="col">Lizenz</th>
              </tr>
            </thead>
            <tbody>
              {BESTANDTEILE.map((b) => (
                <tr key={b.name}>
                  <th scope="row">{b.name}</th>
                  <td>{b.zweck}</td>
                  <td>{b.lizenz}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="erklaerung">
          Eine vollständige Liste aller eingebundenen Bibliotheken mit ihren Lizenztexten liegt noch nicht bei; sie
          folgt mit dem Installer.
        </p>
      </section>

      <section className="karte">
        <h2>Kontakt</h2>
        <p>
          Fragen, Hinweise und Fehlermeldungen an <strong>{KONTAKT}</strong>. Sicherheitslücken bitte nicht öffentlich
          melden, sondern vertraulich an dieselbe Adresse (siehe <code>SECURITY.md</code>).
        </p>
      </section>
    </div>
  );
}
