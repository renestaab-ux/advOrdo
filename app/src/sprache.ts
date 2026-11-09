/**
 * Sprache eines Textes erkennen, damit Bildschirmleser fremdsprachige Dokumente und Absätze richtig vorlesen
 * (WCAG 3.1.2 „Sprache von Teilen“).
 *
 * Gezählt werden häufige Funktionswörter je Sprache. Das kommt ohne Bibliothek und ohne Netz aus und reicht, um
 * einen englischen Vertrag oder ein französisches Urteil von einem deutschen Schriftsatz zu unterscheiden. Bei
 * kurzen oder gemischten Texten bleibt das Ergebnis offen (null), dann gilt die Sprache der Umgebung.
 */

export type Sprache = "de" | "en" | "fr" | "it" | "es" | "nl" | "pt";

export const SPRACHNAMEN: Record<Sprache, string> = {
  de: "Deutsch",
  en: "Englisch",
  fr: "Französisch",
  it: "Italienisch",
  es: "Spanisch",
  nl: "Niederländisch",
  pt: "Portugiesisch",
};

const WOERTER: Record<Sprache, string> = {
  de: "der die das und ist nicht mit den von zu des auf für ein eine einer dem sich auch wird werden bei nach oder als aus dass im wurde sind hat haben",
  en: "the and of to is that for with on by this be are shall as or not which any from at it its was were has have such been",
  fr: "le la les et des du un une est que qui dans pour par sur au aux ne pas ce sont avec il elle cette être été ont",
  it: "il lo gli e di che un una per non con del della sono è nel nella alla dei delle da si questo essere stato hanno",
  es: "el los las y que en un una por con para es del se no al lo como su sus este esta ser fue han está",
  nl: "het een en van is dat op te niet met voor zijn die aan er door wordt ook bij naar deze werd hebben",
  pt: "o os as e do da que em um uma para com não por se dos das ao no na é foi ser são este esta",
};

const LISTE: [Sprache, Set<string>][] = (Object.keys(WOERTER) as Sprache[]).map((s) => [s, new Set(WOERTER[s].split(" "))]);

/**
 * Sprache des Textes oder null, wenn er zu kurz oder nicht eindeutig ist. ``mindestens``: so viele Wörter braucht
 * der Text; je weniger, desto eher irrt die Zählung.
 */
export function spracheErkennen(text: string, mindestens = 12): Sprache | null {
  const woerter = text.toLowerCase().match(/\p{L}+/gu) ?? [];
  if (woerter.length < mindestens) return null;
  const treffer = LISTE.map(([s, menge]) => [s, woerter.reduce((n, w) => n + (menge.has(w) ? 1 : 0), 0)] as const).sort(
    (a, b) => b[1] - a[1],
  );
  const [erste, zweite] = treffer;
  // Eindeutig: genug Funktionswörter überhaupt, und deutlich mehr als bei der nächstbesten Sprache.
  if (erste[1] < 4 || erste[1] / woerter.length < 0.12 || erste[1] < zweite[1] * 1.6) return null;
  return erste[0];
}

/**
 * Sprache des ganzen Dokuments und abweichende Absätze. Ohne eindeutiges Ergebnis gilt Deutsch, die Sprache der
 * Oberfläche. ``absaetze`` enthält je Absatz die Sprache, wenn sie von der des Dokuments abweicht, sonst undefined.
 */
export function sprachenImDokument(texte: string[]): { dokument: Sprache; absaetze: (Sprache | undefined)[] } {
  const dokument = spracheErkennen(texte.join("\n"), 30) ?? "de";
  return {
    dokument,
    absaetze: texte.map((t) => {
      const s = spracheErkennen(t);
      return s && s !== dokument ? s : undefined;
    }),
  };
}
