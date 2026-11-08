/**
 * Markieren im Dokumenttext nur mit der Tastatur.
 *
 * Text, der nicht bearbeitet werden kann, hat im Browser keine Einfügemarke; Umschalt + Pfeil wirkt dort erst, wenn
 * schon eine Auswahl besteht. Diese Helfer setzen eine unsichtbare Einfügemarke in den Text und bewegen oder erweitern
 * sie mit ``Selection.modify`` (wie die Textcursor-Navigation des Browsers).
 */

export type Schritt = { art: "move" | "extend"; richtung: "forward" | "backward"; einheit: string };

/** Taste → Bewegung der Einfügemarke; null = keine Taste für die Marke. */
export function auswahlSchritt(taste: string, umschalt: boolean, strg: boolean): Schritt | null {
  const art = umschalt ? "extend" : "move";
  switch (taste) {
    case "ArrowLeft":
      return { art, richtung: "backward", einheit: strg ? "word" : "character" };
    case "ArrowRight":
      return { art, richtung: "forward", einheit: strg ? "word" : "character" };
    case "ArrowUp":
      return { art, richtung: "backward", einheit: strg ? "paragraphboundary" : "line" };
    case "ArrowDown":
      return { art, richtung: "forward", einheit: strg ? "paragraphboundary" : "line" };
    case "Home":
      return { art, richtung: "backward", einheit: strg ? "documentboundary" : "lineboundary" };
    case "End":
      return { art, richtung: "forward", einheit: strg ? "documentboundary" : "lineboundary" };
    default:
      return null;
  }
}

/** Nächster Vorfahre, der senkrecht blättert. */
function blaetterRahmen(el: HTMLElement): HTMLElement | null {
  for (let p = el.parentElement; p; p = p.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(p).overflowY)) return p;
  }
  return null;
}

function sichtbereich(root: HTMLElement): { oben: number; unten: number } {
  const r = blaetterRahmen(root)?.getBoundingClientRect();
  return { oben: Math.max(r?.top ?? 0, 0), unten: Math.min(r?.bottom ?? innerHeight, innerHeight) };
}

/** Einfügemarke an den Anfang des obersten sichtbaren Absatzes setzen. */
export function markeOben(root: HTMLElement) {
  const { oben } = sichtbereich(root);
  const absaetze = [...root.querySelectorAll<HTMLElement>("p[data-beginn]")];
  const p = absaetze.find((x) => x.getBoundingClientRect().bottom > oben + 4) ?? absaetze[0];
  const sel = window.getSelection();
  if (!p || !sel) return;
  sel.collapse(p, 0);
}

/** Einfügemarke an die Zeichenstelle ``pos`` des Dokuments (wie ``data-beginn``) setzen. */
export function markeAn(root: HTMLElement, pos: number): boolean {
  const absaetze = [...root.querySelectorAll<HTMLElement>("p[data-beginn]")];
  const p = absaetze.filter((x) => Number(x.dataset.beginn) <= pos).pop();
  const sel = window.getSelection();
  if (!p || !sel) return false;
  let rest = pos - Number(p.dataset.beginn);
  const lauf = document.createTreeWalker(p, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement?.closest("[data-kein-text]") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  let letzter: Text | null = null;
  for (let n = lauf.nextNode() as Text | null; n; n = lauf.nextNode() as Text | null) {
    if (rest <= n.length) {
      sel.collapse(n, rest);
      return true;
    }
    rest -= n.length;
    letzter = n;
  }
  if (letzter) sel.collapse(letzter, letzter.length);
  else sel.collapse(p, 0);
  return true;
}

/** Liegt das bewegliche Ende der Auswahl im Rahmen? */
export function auswahlIn(root: HTMLElement): boolean {
  const sel = window.getSelection();
  return !!sel && sel.rangeCount > 0 && !!sel.focusNode && root.contains(sel.focusNode);
}

/** Bildschirmlage des beweglichen Endes der Auswahl. */
function markenLage(): DOMRect | null {
  const sel = window.getSelection();
  if (!sel?.focusNode) return null;
  const r = document.createRange();
  r.setStart(sel.focusNode, sel.focusOffset);
  r.collapse(true);
  const lage = r.getClientRects()[0] ?? r.getBoundingClientRect();
  if (lage && (lage.height > 0 || lage.top !== 0)) return lage;
  const el = sel.focusNode.nodeType === Node.ELEMENT_NODE ? (sel.focusNode as Element) : sel.focusNode.parentElement;
  return el?.getBoundingClientRect() ?? null;
}

/** Ist die Einfügemarke gerade zu sehen? */
export function markeSichtbar(root: HTMLElement): boolean {
  const lage = markenLage();
  if (!lage) return false;
  const { oben, unten } = sichtbereich(root);
  return lage.bottom > oben && lage.top < unten;
}

/** So blättern, dass das bewegliche Ende der Auswahl zu sehen ist. */
export function markeZeigen(root: HTMLElement) {
  const lage = markenLage();
  const rahmen = blaetterRahmen(root);
  if (!lage || !rahmen) return;
  const { oben, unten } = sichtbereich(root);
  const rand = 24;
  if (lage.top < oben + rand) rahmen.scrollTop -= oben + rand - lage.top;
  else if (lage.bottom > unten - rand) rahmen.scrollTop += lage.bottom - (unten - rand);
}

/**
 * Sichtbare Einfügemarke: Nicht bearbeitbarer Text zeigt keinen Cursor. Ein schmaler Strich an der Stelle der Marke
 * zeigt, wo Umschalt + Pfeil zu markieren beginnt. Beim Blättern oder Verlassen des Textes verschwindet er.
 */
let strich: HTMLElement | null = null;

function strichVerbergen() {
  if (strich) strich.hidden = true;
  window.removeEventListener("scroll", strichVerbergen, true);
}

export function strichZeigen() {
  const lage = markenLage();
  if (!lage) return strichVerbergen();
  if (!strich) {
    strich = document.createElement("div");
    strich.className = "text-marke";
    strich.setAttribute("aria-hidden", "true");
    document.body.appendChild(strich);
  }
  strich.hidden = false;
  strich.style.left = `${Math.round(lage.left) - 1}px`;
  strich.style.top = `${Math.round(lage.top)}px`;
  strich.style.height = `${Math.max(12, Math.round(lage.height))}px`;
  window.addEventListener("scroll", strichVerbergen, true);
}

export { strichVerbergen };
