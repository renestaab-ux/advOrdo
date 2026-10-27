import { describe, expect, it } from "vitest";
import {
  dokumentName,
  Beteiligung,
  empfaengerVorschlag,
  nachrichtAlter,
  Akte,
  SammlungEintrag,
  erkanntText,
  sammlungPasst,
  urteilTitel,
  FeldDef,
  bearbeitetText,
  kiModusName,
  zuletztGeoeffnet,
  abstandText,
  aktenzeichenSchluessel,
  sortiert,
  diagnoseBericht,
  faelligeErinnerungen,
  datumLang,
  akteTitel,
  aktePasst,
  betragAnzeige,
  betragNormalisieren,
  aktiveUmgebung,
  feldText,
  personName,
  startwerte,
  abgleichZusammenfassung,
  auswahlText,
  datumDe,
  dokumentDatum,
  euro,
  heuteIso,
  prozent,
  satzDe,
  dauerText,
  groesseText,
  veraltet,
  formatiereBuilddate,
  fundstelle,
  istZitat,
  lesartText,
  rechtsprechungUmfang,
  renderBreite,
  markiereBegriffe,
  rnHinweis,
  segmente,
  tagsAusText,
  tagUebersicht,
  urteilHerkunft,
  offeneUebernahmen,
  programmName,
  optionPasst,
  type Arbeitskopie,
  exportTeile,
  rechercheFelder,
  riiOnline,
  trefferTitel,
} from "./kern";

describe("istZitat", () => {
  it("erkennt Normzitate", () => {
    expect(istZitat("§ 280 Abs. 1 S. 2 BGB")).toBe(true);
    expect(istZitat("§ 253 ZPO")).toBe(true);
    expect(istZitat("Art. 3 GG")).toBe(true);
  });
  it("behandelt Suchbegriffe nicht als Zitat", () => {
    expect(istZitat("Verjährung")).toBe(false);
    expect(istZitat("§ 280")).toBe(false);
  });
});

describe("formatiereBuilddate", () => {
  it("formatiert den Quellstempel", () => {
    expect(formatiereBuilddate("20260901120000")).toBe("01.09.2026");
    expect(formatiereBuilddate(null)).toBe("unbekannt");
  });
});

describe("fundstelle", () => {
  it("nennt Seite und Randnummer", () => {
    expect(fundstelle({ seite: 2, seite_bis: 3, rn: 5 })).toBe("S. 2–3, Rn. 5");
    expect(fundstelle({ seite: null, rn: 4 })).toBe("Rn. 4");
    expect(fundstelle({ seite: null, rn: null, nr: 12 })).toBe("Abschn. 12");
  });
});

describe("segmente", () => {
  const z = (start: number, ende: number) =>
    ({ start, ende, zitat: "x", status: "belegt" }) as unknown as import("./kern").NormZitat;
  it("schneidet Zitate aus dem Text", () => {
    const text = "aus §§ 280 Abs. 1, 281 BGB folgt";
    const s = segmente(text, [z(19, 22), z(7, 17)]);
    expect(s.map((x) => x.text)).toEqual(["aus §§ ", "280 Abs. 1", ", ", "281", " BGB folgt"]);
    expect(s.filter((x) => x.zitat).length).toBe(2);
  });
  it("ignoriert überlappende Angaben", () => {
    expect(segmente("abcdef", [z(0, 4), z(2, 5)]).map((x) => x.text)).toEqual(["abcd", "ef"]);
  });
});

describe("lesartText", () => {
  it("beschreibt die Herkunft des Textes", () => {
    expect(lesartText({ lesart: "ocr", ocr_konfidenz: 94.2, format: "pdf" })).toBe("Scan (Texterkennung, Erkennung 94 %)");
    expect(lesartText({ lesart: "datei", ocr_konfidenz: null, format: "docx" })).toBe("Word");
  });
});

describe("tagsAusText", () => {
  it("trennt an Komma und Semikolon und entfernt Dubletten", () => {
    expect(tagsAusText(" Kläger,  Anlage   K 1; kläger, ")).toEqual(["Kläger", "Anlage K 1"]);
    expect(tagsAusText("")).toEqual([]);
  });
});

describe("tagUebersicht", () => {
  it("zählt Tags und stellt Beteiligte voran", () => {
    const d = (...namen: string[]) => ({ tags: namen.map((name) => ({ name, quelle: "manuell" as const })) });
    expect(tagUebersicht([d("Anlagen", "Kläger"), d("Gericht"), d("Kläger"), d()])).toEqual([
      { name: "Kläger", anzahl: 2 },
      { name: "Gericht", anzahl: 1 },
      { name: "Anlagen", anzahl: 1 },
    ]);
  });
});

describe("abgleichZusammenfassung", () => {
  it("zählt Abweichungen und Übereinstimmungen", () => {
    expect(abgleichZusammenfassung({ dokumente: 9, zaehlung: { abweichend: 7, uebereinstimmend: 4, einzeln: 0 } })).toBe(
      "7 mögliche Abweichungen, 4 Übereinstimmungen in 9 Dokumenten",
    );
    expect(abgleichZusammenfassung({ dokumente: 1, zaehlung: { abweichend: 1, uebereinstimmend: 1, einzeln: 2 } })).toBe(
      "1 mögliche Abweichung, 1 Übereinstimmung in 1 Dokument",
    );
  });
});

describe("Sprachmodell", () => {
  it("zeigt Laufzeiten und Größen lesbar", () => {
    expect(dauerText(45)).toBe("45 s");
    expect(dauerText(185)).toBe("3:05 min");
    expect(groesseText(9_300_000_000)).toBe("9,3 GB");
    expect(groesseText(null)).toBe("");
  });
  it("erkennt, ob sich die Akte seit dem Ergebnis geändert hat", () => {
    const ergebnis = { dokumente: [{ dokument_id: 2 }, { dokument_id: 1 }] };
    expect(veraltet(ergebnis, [1, 2])).toBe(false);
    expect(veraltet(ergebnis, [1, 2, 3])).toBe(true);
    expect(veraltet(ergebnis, [1])).toBe(true);
    expect(veraltet(null, [1])).toBe(false);
  });
});

describe("Rechtsprechung", () => {
  it("beschreibt den Umfang des Verzeichnisses, größtes Gericht zuerst", () => {
    expect(
      rechtsprechungUmfang({
        gerichte: { BVerfG: { anzahl: 5, von: "1998-01-02", bis: null }, BGH: { anzahl: 40, von: "2010-01-04", bis: null } },
      }),
    ).toBe("BGH ab 2010, BVerfG ab 1998");
  });
});

describe("Sammlung der Entscheidungen", () => {
  const e: SammlungEintrag = {
    id: 3,
    akte_id: null,
    zitat: null,
    gericht: "BGH",
    aktenzeichen: "VIII ZR 103/15",
    datum: "2016-10-12",
    quelle: "rii",
    herkunft: "rechtsprechung-im-internet.de",
    dateiname: "jb-KORE301892016.zip",
    format: "rii",
    sha256: "ab",
    lesart: "datei",
    hinzugefuegt_am: "2026-10-26T12:00:00",
    hinweise: [],
    doknr: "KORE301892016",
    kopf: { spruchkoerper: "8. Zivilsenat", doktyp: "Urteil", normen: "§ 476 BGB", vorinstanz: [], titel: null },
    akten: [{ akte_id: 1, name: "Brückner ./. Autohaus", urteil_id: 3, zitat: null }],
    zugeordnet: true,
  };

  it("nennt Gericht, Spruchkörper, Art, Datum und Aktenzeichen", () => {
    expect(urteilTitel(e)).toBe("BGH 8. Zivilsenat, Urteil vom 12.10.2016 – VIII ZR 103/15");
    expect(urteilTitel({ gericht: "OLG Hamm", datum: null, aktenzeichen: null, kopf: null })).toBe("OLG Hamm");
  });

  it("nennt die Fundstelle eines erkannten Werts", () => {
    expect(erkanntText({ wert: "28 U 12/21", fundstelle: { abschnitt: 3, seite: 1, text: "Aktenzeichen: 28 U 12/21" } })).toBe(
      "S. 1: „Aktenzeichen: 28 U 12/21“",
    );
    expect(erkanntText({ wert: "BGH", fundstelle: { abschnitt: 2, seite: null, text: "BUNDESGERICHTSHOF" } })).toBe(
      "Abs. 2: „BUNDESGERICHTSHOF“",
    );
  });

  it("filtert nach Zuordnung, Quelle und Text", () => {
    const alle = { zuordnung: "alle" as const, quelle: "alle" as const, text: "" };
    expect(sammlungPasst(e, alle)).toBe(true);
    expect(sammlungPasst(e, { ...alle, zuordnung: "frei" })).toBe(false);
    expect(sammlungPasst({ ...e, akten: [], zugeordnet: false }, { ...alle, zuordnung: "frei" })).toBe(true);
    expect(sammlungPasst(e, { ...alle, quelle: "manuell" })).toBe(false);
    expect(sammlungPasst(e, { ...alle, text: "viii zr brückner" })).toBe(true);
    expect(sammlungPasst(e, { ...alle, text: "476" })).toBe(true);
    expect(sammlungPasst(e, { ...alle, text: "OLG" })).toBe(false);
  });
});

describe("Randnummern", () => {
  it("sagt, ob die zitierte Randnummer im Volltext steht", () => {
    expect(rnHinweis({ rn_zitiert: 22, rn_vorhanden: true }, 67)).toBe("Rn. 22 zitiert");
    expect(rnHinweis({ rn_zitiert: 99, rn_vorhanden: false }, 67)).toBe("Rn. 99 zitiert, die Entscheidung hat nur Rn. 1–67");
    expect(rnHinweis({ rn_zitiert: null, rn_vorhanden: null }, 67)).toBeNull();
  });
});

describe("Ergänzte Urteile", () => {
  it("nennt Quelle und Datei", () => {
    expect(urteilHerkunft({ herkunft: "juris", dateiname: "BGH VIII ZR 999-20.pdf" })).toBe("juris, BGH VIII ZR 999-20.pdf");
    expect(urteilHerkunft({ herkunft: null, dateiname: "urteil.pdf" })).toBe("urteil.pdf");
  });
});

describe("Original-Ansicht", () => {
  it("rendert in gerundeter Breite, scharf auch bei hoher Pixeldichte", () => {
    expect(renderBreite(700, 1)).toBe(800);
    expect(renderBreite(700, 2)).toBe(1400);
    expect(renderBreite(100, 1)).toBe(400);
    expect(renderBreite(3000, 2)).toBe(2400);
  });
});

describe("Suche", () => {
  it("markiert Begriffe ohne Rücksicht auf Groß- und Kleinschreibung", () => {
    expect(markiereBegriffe("Der Rücktritt und der rücktritt.", ["Rücktritt"])).toEqual([
      { text: "Der ", treffer: false },
      { text: "Rücktritt", treffer: true },
      { text: " und der ", treffer: false },
      { text: "rücktritt", treffer: true },
      { text: ".", treffer: false },
    ]);
  });
  it("nimmt Sonderzeichen wörtlich und den längeren Begriff zuerst", () => {
    expect(markiereBegriffe("VIII ZR 103/15 (a+b)", ["ZR 103/15", "ZR", "(a+b)"]).filter((t) => t.treffer)).toEqual([
      { text: "ZR 103/15", treffer: true },
      { text: "(a+b)", treffer: true },
    ]);
    expect(markiereBegriffe("ohne", [])).toEqual([{ text: "ohne", treffer: false }]);
  });
});

describe("auswahlText", () => {
  it("nennt, was dem Modell vorlag", () => {
    expect(auswahlText({ vollstaendig: true, absaetze: 40, von: 40, dokumente: 3, dokumente_von: 3 })).toBe(
      "alle 3 Dokumente vollständig",
    );
    expect(auswahlText({ vollstaendig: true, absaetze: 12, von: 12, dokumente: 1, dokumente_von: 1 })).toBe(
      "das Dokument vollständig",
    );
    expect(auswahlText({ vollstaendig: false, absaetze: 120, von: 450, dokumente: 6, dokumente_von: 8 })).toBe(
      "120 von 450 Absätzen aus 6 von 8 Dokumenten, ausgewählt nach den Begriffen der Frage",
    );
    expect(auswahlText({ vollstaendig: false, absaetze: 30, von: 90, dokumente: 1, dokumente_von: 1 })).toBe(
      "30 von 90 Absätzen, ausgewählt nach den Begriffen der Frage",
    );
  });
});

describe("Toolbox-Formate", () => {
  it("schreibt Beträge, Sätze und Daten deutsch", () => {
    expect(euro("1234.5")).toBe("1.234,50 €");
    expect(euro("74.7611", 4)).toBe("74,7611 €");
    expect(prozent("8.62")).toBe("8,62 %");
    expect(prozent("-0.88")).toBe("-0,88 %");
    expect(satzDe("1.3")).toBe("1,3");
    expect(satzDe("3")).toBe("3,0");
    expect(datumDe("2026-10-17")).toBe("17.10.2026");
    expect(heuteIso(new Date(2026, 0, 5))).toBe("2026-01-05");
  });
});

describe("Datum eines Dokuments", () => {
  const leer = { datum_seite: null, datum_text: null, gespeichert_am: null, gespeichert_quelle: null } as const;

  it("nennt bei der Datumszeile die Fundstelle", () => {
    const d = dokumentDatum({
      ...leer,
      datum: "2025-06-23",
      datum_quelle: "dokument",
      datum_seite: 1,
      datum_text: "Freiburg, den 23.06.2025",
      gespeichert_am: "2026-10-11T12:58:57+02:00",
      gespeichert_quelle: "datei",
    });
    expect(d.text).toBe("23.06.2025");
    expect(d.herkunft).toBe("aus dem Dokument");
    expect(d.erklaerung).toBe(
      "Datumszeile auf S. 1: „Freiburg, den 23.06.2025“. Zuletzt gespeichert: 11.10.2026, 12:58 (Dateidatum).",
    );
  });

  it("weist beim Word-Entwurf auf den Speicherstand hin", () => {
    const d = dokumentDatum({
      ...leer,
      datum: "2026-10-17",
      datum_quelle: "word",
      gespeichert_am: "2026-10-17T23:30:00+02:00",
      gespeichert_quelle: "word",
    });
    expect(d.herkunft).toBe("zuletzt gespeichert");
    expect(d.erklaerung).toBe("Keine Datumszeile im Dokument. Zuletzt gespeichert: 17.10.2026, 23:30 (laut Word).");
  });

  it("zeigt einen Strich, wenn nichts bekannt ist", () => {
    expect(dokumentDatum({ ...leer, datum: null, datum_quelle: "unbekannt" }).text).toBe("–");
    const vonHand = dokumentDatum({ ...leer, datum: "2026-08-28", datum_quelle: "manuell" });
    expect([vonHand.text, vonHand.herkunft]).toEqual(["28.08.2026", "von Hand"]);
  });

  it("zeigt den Titel vor dem Dateinamen", () => {
    expect(dokumentName({ titel: "Verfügung LG Freiburg", dateiname: "05_Verfuegung.docx" })).toBe("Verfügung LG Freiburg");
    expect(dokumentName({ titel: "  ", dateiname: "05_Verfuegung.docx" })).toBe("05_Verfuegung.docx");
    expect(dokumentName({ titel: null, dateiname: "05_Verfuegung.docx" })).toBe("05_Verfuegung.docx");
  });
});

describe("aktiveUmgebung", () => {
  const u = (id: string, aktiv = false) => ({ id, name: id.toUpperCase(), angelegt_am: null, standard: id === "standard", aktiv });
  it("zeigt nichts, solange es nur die Standardumgebung gibt", () => {
    expect(aktiveUmgebung({ aktiv: "standard", umgebungen: [u("standard", true)] })).toBeNull();
    expect(aktiveUmgebung(null)).toBeNull();
  });
  it("nennt die aktive Umgebung, sobald es mehrere gibt", () => {
    const liste = { aktiv: "test", umgebungen: [u("standard"), u("test", true)] };
    expect(aktiveUmgebung(liste)?.name).toBe("TEST");
  });
});

describe("Eigene Daten", () => {
  const f = (typ: FeldDef["typ"], extra: Partial<FeldDef> = {}): FeldDef => ({ schluessel: "x", titel: "X", typ, pflicht: false, ...extra });
  it("setzt Namen aus Titel, Vor- und Nachname zusammen", () => {
    expect(personName({ titel: "Dr.", vorname: "Erika", nachname: "Muster" })).toBe("Dr. Erika Muster");
    expect(personName({ titel: "", vorname: "Max", nachname: "Beispiel" })).toBe("Max Beispiel");
  });
  it("zeigt Feldwerte lesbar an", () => {
    expect(feldText(f("mehrfach"), ["Arbeitsrecht", "Erbrecht"])).toBe("Arbeitsrecht, Erbrecht");
    expect(feldText(f("ja_nein"), true)).toBe("ja");
    expect(feldText(f("ja_nein"), false)).toBe("");
    expect(feldText(f("datum"), "2026-03-01")).toBe("01.03.2026");
    expect(feldText(f("text"), undefined)).toBe("");
  });
  it("füllt Vorgaben nur in neue Formulare", () => {
    const felder = [f("text", { schluessel: "land", vorgabe: "Deutschland" }), f("mehrfach", { schluessel: "fa" })];
    expect(startwerte(felder, null)).toEqual({ land: "Deutschland", fa: [] });
    expect(startwerte(felder, { land: "" })).toEqual({ land: "", fa: [] });
  });
});

describe("akteTitel", () => {
  it("zeigt das Aktenzeichen vor dem Namen", () => {
    expect(akteTitel({ name: "Brückner ./. Autohaus", aktenzeichen: "12/26" })).toBe("12/26 · Brückner ./. Autohaus");
    expect(akteTitel({ name: "Testakte Ordner", aktenzeichen: null })).toBe("Testakte Ordner");
  });
});

describe("betragAnzeige", () => {
  it("zeigt den Gegenstandswert deutsch, Freitext unverändert", () => {
    expect(betragAnzeige("250000.00")).toBe("250.000,00");
    expect(betragAnzeige("18450.5")).toBe("18.450,50");
    expect(betragAnzeige(null)).toBe("");
    expect(betragAnzeige("ca. 5.000")).toBe("ca. 5.000");
  });
});

describe("betragNormalisieren", () => {
  it("liest deutsche Schreibweisen", () => {
    expect(betragNormalisieren("250.000")).toBe("250.000,00");
    expect(betragNormalisieren("18450,5 €")).toBe("18.450,50");
    expect(betragNormalisieren("1500")).toBe("1.500,00");
    expect(betragNormalisieren("viel")).toBe("viel");
    expect(betragNormalisieren(" ")).toBe("");
  });
});

describe("Aktenübersicht", () => {
  const jetzt = new Date("2026-10-21T15:00:00");
  it("schreibt „bearbeitet“ als heute, gestern oder Datum", () => {
    expect(bearbeitetText("2026-10-21T09:12:00", jetzt)).toBe("heute");
    expect(bearbeitetText("2026-10-20T23:00:00", jetzt)).toBe("gestern");
    expect(bearbeitetText("2026-10-02T10:00:00", jetzt)).toBe("02.10.");
    expect(bearbeitetText("2025-12-30", jetzt)).toBe("30.12.2025");
    expect(bearbeitetText(null, jetzt)).toBe("–");
  });

  it("listet zuletzt geöffnete Akten, neueste zuerst, ohne nie geöffnete", () => {
    const akte = (id: number, geoeffnet_am: string | null) => ({ id, geoeffnet_am }) as Akte;
    const liste = [akte(1, "2026-10-19T10:00:00"), akte(2, null), akte(3, "2026-10-21T08:00:00"), akte(4, "2026-10-20T08:00:00")];
    expect(zuletztGeoeffnet(liste, 2).map((a) => a.id)).toEqual([3, 4]);
  });
});

describe("externe Programme und Arbeitskopien", () => {
  it("zeigt den Programmnamen ohne Pfad und Endung", () => {
    expect(programmName("C:\\Program Files\\LibreOffice\\program\\soffice.exe")).toBe("soffice");
    expect(programmName("/Applications/LibreOffice.app/")).toBe("LibreOffice");
    expect(programmName("/usr/bin/okular")).toBe("okular");
    expect(programmName("")).toBe("Standardprogramm");
  });

  it("fragt nach geänderten Kopien, bis „Später“ gewählt wurde, und wieder nach dem nächsten Speichern", () => {
    const kopie = (id: number, status: Arbeitskopie["status"], geaendert_am: string): Arbeitskopie => ({
      dokument_id: id, dateiname: `d${id}.docx`, pfad: "", basis_nr: 1, angelegt_am: "", geaendert_am, status,
    });
    const kopien = [kopie(1, "geaendert", "t1"), kopie(2, "unveraendert", "t1"), kopie(3, "gesperrt", "t1")];
    expect(offeneUebernahmen(kopien, new Set()).map((k) => k.dokument_id)).toEqual([1]);
    expect(offeneUebernahmen(kopien, new Set(["1|t1"]))).toEqual([]);
    expect(offeneUebernahmen([kopie(1, "geaendert", "t2")], new Set(["1|t1"]))).toHaveLength(1);
  });
});

describe("Fristen-Anzeige", () => {
  it("zeigt Datum mit Wochentag", () => {
    expect(datumLang("2026-09-29")).toBe("Di, 29.09.2026");
    expect(datumLang(null)).toBe("–");
  });

  it("beschreibt den Abstand zum Datum", () => {
    const e = { art: "frist" as const, erledigt_am: null };
    expect(abstandText({ ...e, in_tagen: 0 })).toBe("heute");
    expect(abstandText({ ...e, in_tagen: 1 })).toBe("morgen");
    expect(abstandText({ ...e, in_tagen: 4 })).toBe("in 4 Tagen");
    expect(abstandText({ ...e, in_tagen: -1 })).toBe("seit gestern abgelaufen");
    expect(abstandText({ ...e, art: "termin", in_tagen: -3 })).toBe("seit 3 Tagen vorbei");
    expect(abstandText({ ...e, in_tagen: 5, erledigt_am: "2026-09-20T10:00:00" })).toBe("erledigt");
  });
});

describe("faelligeErinnerungen", () => {
  const basis = {
    id: 7,
    akte_id: 3,
    verfahren_id: null,
    art: "frist" as const,
    art_text: "Frist",
    titel: "Klageerwiderung",
    datum: "2026-11-26",
    uhrzeit: null,
    ort: null,
    vorfrist: null,
    berechnung: null,
    dokument_id: null,
    dokument: null,
    fundstelle: null,
    notiz: null,
    erledigt_am: null,
    erledigt_vermerk: null,
    in_tagen: 10,
    lage: "offen" as const,
    akte: "Weber ./. Brückner",
    aktenzeichen: "12/26",
  };
  const leer = new Set<string>();

  it("erinnert bei Fristen an Vorfrist, Vortag, Ablauf und Überschreitung", () => {
    expect(faelligeErinnerungen([basis], leer)).toEqual([]);
    const vorfrist = faelligeErinnerungen([{ ...basis, in_tagen: 5, vorfrist: "2026-11-19", lage: "vorfrist" }], leer);
    expect(vorfrist[0].titel).toBe("Vorfrist erreicht: Klageerwiderung");
    expect(vorfrist[0].text).toBe("12/26 Weber ./. Brückner · Frist Do, 26.11.2026");
    expect(faelligeErinnerungen([{ ...basis, in_tagen: 1, lage: "bald" }], leer)[0].schluessel).toBe("7:morgen:2026-11-26");
    expect(faelligeErinnerungen([{ ...basis, in_tagen: 0, lage: "heute" }], leer)[0].titel).toBe(
      "Frist läuft heute ab: Klageerwiderung",
    );
    expect(faelligeErinnerungen([{ ...basis, in_tagen: -2, lage: "abgelaufen" }], leer)[0].titel).toBe(
      "Frist abgelaufen: Klageerwiderung",
    );
  });

  it("zeigt jede Stufe nur einmal und lässt erledigte aus", () => {
    const heute = { ...basis, in_tagen: 0, lage: "heute" as const };
    expect(faelligeErinnerungen([heute], new Set(["7:heute:2026-11-26"]))).toEqual([]);
    // Verschobenes Datum: neue Erinnerung.
    expect(faelligeErinnerungen([{ ...heute, datum: "2026-11-27" }], new Set(["7:heute:2026-11-26"]))).toHaveLength(1);
    expect(faelligeErinnerungen([{ ...heute, erledigt_am: "2026-11-25T09:00:00" }], leer)).toEqual([]);
  });

  it("erinnert an Termine am Vortag und am Tag, an Wiedervorlagen ab dem Tag", () => {
    const termin = { ...basis, art: "termin" as const, art_text: "Termin", titel: "Mündliche Verhandlung", uhrzeit: "10:30", ort: "Saal 2" };
    expect(faelligeErinnerungen([{ ...termin, in_tagen: 1 }], leer)[0]).toMatchObject({
      titel: "Termin morgen, 10:30 Uhr: Mündliche Verhandlung",
      text: "12/26 Weber ./. Brückner · Termin Do, 26.11.2026 · Saal 2",
    });
    expect(faelligeErinnerungen([{ ...termin, in_tagen: -1 }], leer)).toEqual([]);
    const wv = { ...basis, art: "wiedervorlage" as const, art_text: "Wiedervorlage", titel: "Zahlungseingang prüfen" };
    expect(faelligeErinnerungen([{ ...wv, in_tagen: 1 }], leer)).toEqual([]);
    expect(faelligeErinnerungen([{ ...wv, in_tagen: -3 }], leer)[0].titel).toBe("Wiedervorlage: Zahlungseingang prüfen");
  });
});

describe("diagnoseBericht", () => {
  it("listet Ergebnisse je Gruppe mit Hinweis, ungeprüfte ausdrücklich", () => {
    const pruefungen = [
      { id: "kern", gruppe: "programm", gruppe_titel: "Programm und Daten", titel: "Kern" },
      { id: "gii", gruppe: "netz", gruppe_titel: "Rechtsquellen im Internet", titel: "Gesetze im Internet" },
    ];
    const bericht = diagnoseBericht(
      pruefungen,
      {
        gii: {
          id: "gii", gruppe: "netz", titel: "Gesetze im Internet", stand: "fehler", meldung: "Keine Verbindung.",
          details: ["https://www.gesetze-im-internet.de/gii-toc.xml"], hilfe: "Verbindung prüfen.", dauer_ms: 12,
        },
      },
      new Date(2026, 9, 22, 18, 0),
    );
    expect(bericht).toContain("## Programm und Daten\n- Kern: nicht geprüft");
    expect(bericht).toContain("- [FEHLER] Gesetze im Internet: Keine Verbindung.\n    https://www.gesetze-im-internet.de/gii-toc.xml\n    Was tun: Verbindung prüfen.");
  });
});

describe("sortiert", () => {
  const liste = [
    { az: "10/26", n: 3 },
    { az: "2/26", n: null },
    { az: "101/25", n: 1 },
    { az: null, n: 2 },
  ];
  const werte = { az: (x: (typeof liste)[0]) => aktenzeichenSchluessel(x.az), n: (x: (typeof liste)[0]) => x.n };
  it("sortiert Aktenzeichen nach Jahr und Nummer, leere Werte am Ende", () => {
    expect(sortiert(liste, { spalte: "az", absteigend: false }, werte).map((x) => x.az)).toEqual(["101/25", "2/26", "10/26", null]);
    expect(sortiert(liste, { spalte: "az", absteigend: true }, werte).map((x) => x.az)).toEqual(["10/26", "2/26", "101/25", null]);
  });
  it("sortiert Zahlen und lässt unbekannte Spalten unverändert", () => {
    expect(sortiert(liste, { spalte: "n", absteigend: true }, werte).map((x) => x.n)).toEqual([3, 2, 1, null]);
    expect(sortiert(liste, { spalte: "gibtsnicht", absteigend: false }, werte)).toBe(liste);
  });
});

describe("aktePasst", () => {
  const a = {
    aktenzeichen: "388/26",
    name: "Brückner ./. Weber",
    gegenstand: "Heizungsanlage",
    mandanten: ["Dr. Lena Brückner"],
    gegner: ["Weber Haustechnik GmbH"],
    gerichte: [{ name: "Landgericht Freiburg im Breisgau", aktenzeichen: "2 O 233/26" }],
  };
  it("findet nach Aktenzeichen, Partei und Gericht, auch ohne Umlaut und Großschreibung", () => {
    expect(aktePasst(a, "")).toBe(true);
    expect(aktePasst(a, "388")).toBe(true);
    expect(aktePasst(a, "bruckner weber")).toBe(true);
    expect(aktePasst(a, "2 O 233")).toBe(true);
    expect(aktePasst(a, "freiburg müller")).toBe(false);
  });
});

describe("optionPasst", () => {
  const kammer = "Rechtsanwaltskammer für den Oberlandesgerichtsbezirk München";
  it("findet Teilwörter an beliebiger Stelle, auch mit umschriebenem Umlaut", () => {
    expect(optionPasst(kammer, "")).toBe(true);
    expect(optionPasst(kammer, "münchen")).toBe(true);
    expect(optionPasst(kammer, "Muen")).toBe(true);
    expect(optionPasst(kammer, "muenchen")).toBe(true);
    expect(optionPasst(kammer, "kammer münchen")).toBe(true);
    expect(optionPasst(kammer, "nürnberg")).toBe(false);
    expect(optionPasst("Rechtsanwaltskammer Köln", "koeln")).toBe(true);
  });
});

describe("exportTeile", () => {
  it("bietet nur Teile mit gespeichertem Ergebnis an, mit Anzahl", () => {
    const teile = exportTeile({
      zusammenfassung_akte: null,
      widersprueche: null,
      chronologie: { ereignisse: [{}, {}] } as never,
      dokumente: { "3": {} as never },
    });
    expect(teile.map((t) => [t.id, t.vorhanden])).toEqual([
      ["widersprueche", false],
      ["chronologie", true],
      ["zusammenfassung_akte", false],
      ["dokumente", true],
    ]);
    expect(teile[1].titel).toBe("Chronologie (2)");
    expect(teile[3].titel).toBe("Zusammenfassungen der Dokumente (1)");
  });
});

describe("kiModusName", () => {
  it("unterscheidet eigenen Rechner, lokales Netzwerk und externen Anbieter", () => {
    expect(kiModusName(null)).toBe("Eigener Rechner");
    expect(kiModusName({ aktiv: "lokal", titel: null, modell: "m", ort: "geraet" })).toBe("Eigener Rechner");
    expect(kiModusName({ aktiv: "lokal", titel: null, modell: "m", ort: "netzwerk" })).toBe("Lokales Netzwerk");
    expect(kiModusName({ aktiv: "extern", titel: "Google Gemini", modell: "m", ort: null })).toBe(
      "Externer Anbieter (Google Gemini)",
    );
  });
});

describe("Online-Recherche", () => {
  const leer = { gericht: "", gerichtsbarkeit: "", aktenzeichen: "", volltext: "", norm: "", von: "", bis: "" };

  it("sucht bei rechtsprechung-im-internet.de nur mit Volltext, Norm oder ECLI auf der Seite", () => {
    expect(riiOnline({ ...leer, aktenzeichen: "VIII ZR 103/15" })).toBe(false);
    expect(riiOnline({ ...leer, aktenzeichen: " ecli:DE:BGH:2016" })).toBe(true);
    expect(riiOnline({ ...leer, norm: "§ 476 BGB" })).toBe(true);
    expect(riiOnline({ ...leer, volltext: "Gebrauchtwagen" })).toBe(true);
  });

  it("sendet nur ausgefüllte Felder, die die Maske der Quelle hat", () => {
    const f = { ...leer, gericht: "BGH", gerichtsbarkeit: "Ordentliche Gerichtsbarkeit", norm: "§ 1 BGB", volltext: " x " };
    expect(rechercheFelder("rii", f)).toEqual({ gericht: "BGH", norm: "§ 1 BGB", volltext: "x" });
    expect(rechercheFelder("bayern", f)).toEqual({ gerichtsbarkeit: "Ordentliche Gerichtsbarkeit", volltext: "x" });
    expect(rechercheFelder("neuris", f)).toEqual({ gericht: "BGH", volltext: "x" });
  });

  it("betitelt Treffer wie gespeicherte Entscheidungen", () => {
    const t = {
      quelle: "rii" as const,
      doknr: "KORE301892016",
      gericht: "BGH",
      spruchkoerper: "8. Zivilsenat",
      datum: "2016-10-12",
      aktenzeichen: "VIII ZR 103/15",
      doktyp: "Urteil",
      titel: null,
      ausschnitt: null,
      link: null,
      urteil_id: null,
    };
    expect(trefferTitel(t)).toBe("BGH 8. Zivilsenat, Urteil vom 12.10.2016 – VIII ZR 103/15");
    expect(trefferTitel({ ...t, doktyp: null, spruchkoerper: null })).toBe("BGH, Entscheidung vom 12.10.2016 – VIII ZR 103/15");
  });
});

describe("nachrichtAlter", () => {
  const jetzt = new Date(2026, 9, 26, 18, 0);
  it("nennt Minuten und Stunden am selben Tag", () => {
    expect(nachrichtAlter(new Date(2026, 9, 26, 17, 55).toISOString(), jetzt)).toBe("vor 5 Min.");
    expect(nachrichtAlter(new Date(2026, 9, 26, 15, 0).toISOString(), jetzt)).toBe("vor 3 Std.");
  });
  it("nennt gestern bzw. das Datum", () => {
    expect(nachrichtAlter(new Date(2026, 9, 25, 9, 0).toISOString(), jetzt)).toBe("gestern");
    expect(nachrichtAlter(new Date(2026, 9, 20, 9, 0).toISOString(), jetzt)).toBe("20.10.2026");
    expect(nachrichtAlter(null, jetzt)).toBe("");
  });
});

describe("empfaengerVorschlag", () => {
  const b = (id: number, rolle: string) =>
    ({ id, rolle, rolle_text: rolle, seite: "neutral", gruppe: "neutral", name: `B${id}`, quelle: "verzeichnis",
       beteiligter_id: id, art: "person", aktenzeichen: "" }) as Beteiligung;
  const liste = [b(1, "mandant"), b(2, "gegner"), b(3, "gericht"), b(4, "bevollmaechtigter_gegner")];
  it("Schriftsatz an das Gericht, Brief an den Gegnervertreter", () => {
    expect(empfaengerVorschlag(liste, "schriftsatz")).toBe(3);
    expect(empfaengerVorschlag(liste, "brief")).toBe(4);
    expect(empfaengerVorschlag(liste.slice(0, 2), "eigen")).toBe(2);
    expect(empfaengerVorschlag([], "brief")).toBeNull();
  });
});
