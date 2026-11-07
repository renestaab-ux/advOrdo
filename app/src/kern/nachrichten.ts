// --- Nachrichten auf der Startseite (RSS/Atom) --------------------------------------------------------

export interface NachrichtenFeed {
  id: string;
  titel: string;
  url: string;
  hinzugefuegt: string;
}

export interface NachrichtenVorschlag {
  titel: string;
  url: string;
  hinweis: string;
  eingetragen: boolean;
}

export interface NachrichtenEinstellungen {
  feeds: NachrichtenFeed[];
  vorschlaege: NachrichtenVorschlag[];
}

export interface Nachricht {
  titel: string;
  link: string | null;
  datum: string | null;
  auszug: string;
  quelle: string;
  feed_id: string;
}

export interface NachrichtenListe {
  feeds: number;
  eintraege: Nachricht[];
  gesamt: number;
  stand: string | null;
  laeuft: boolean;
  fehler: { feed_id: string; titel: string; text: string }[];
}

/** „vor 5 Min.“, „vor 3 Std.“, „gestern“ bzw. das Datum: wann eine Nachricht erschienen ist. */
export function nachrichtAlter(iso: string | null, jetzt: Date = new Date()): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const minuten = Math.round((jetzt.getTime() - d.getTime()) / 60000);
  if (minuten < 1) return "gerade eben";
  if (minuten < 60) return `vor ${minuten} Min.`;
  if (minuten < 60 * 24 && d.getDate() === jetzt.getDate()) return `vor ${Math.round(minuten / 60)} Std.`;
  const gestern = new Date(jetzt);
  gestern.setDate(jetzt.getDate() - 1);
  if (d.toDateString() === gestern.toDateString()) return "gestern";
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}
