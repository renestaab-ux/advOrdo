"""Diagnose: prüft Programmteile, Sprachmodelle und die Online-Rechtsquellen einzeln und erklärt Fehler verständlich.

Jede Prüfung liefert einen Stand (``ok``, ``warnung``, ``fehler`` oder ``aus`` für Abgeschaltetes), eine kurze
Meldung, Einzelheiten und bei Problemen einen Hinweis, was zu tun ist. Ins Netz gehen nur Abrufe öffentlicher
Rechtsquellen (die ersten Bytes der Startseite bzw. des Verzeichnisses) und, wenn die externe KI eingebunden ist,
die Modellliste des Anbieters. Dokumentinhalte werden nie übertragen.
"""

from __future__ import annotations

import hashlib
import platform
import shutil
import socket
import sqlite3
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import __version__, gerichte, programme, verschluesselung, zertifikate
from .dokumente import ocr
from .gesetze import quelle
from .ki import anbieter as ki_anbieter
from .rechtsprechung import bayern, neuris, online, verzeichnis

USER_AGENT = "advOrdo/0.1 (Diagnose; advordo@staab.legal)"
NETZ_TIMEOUT = 10
FREI_WARNUNG = 1024**3  # unter 1 GB freiem Speicher warnen

GRUPPEN = {"programm": "Programm und Daten", "ki": "Sprachmodelle", "netz": "Rechtsquellen im Internet"}


def _ergebnis(stand: str, meldung: str, details: list[str] | None = None, hilfe: str | None = None) -> dict:
    return {"stand": stand, "meldung": meldung, "details": details or [], "hilfe": hilfe}


# --------------------------------------------------------------------------- Programm und Daten

def _kern(k: Any) -> dict:
    ordner = Path(k.ki_datei).parent
    details = [f"advOrdo-Kern {__version__}, Python {platform.python_version()}",
               f"System: {platform.system()} {platform.release()} ({platform.machine()})",
               f"Datenordner: {ordner}", f"Arbeitsumgebung: {k.umgebungen.ordner()}",
               "Zertifikate: " + ("Speicher des Systems" if zertifikate.aktiv() else "eigene Liste von Python "
                                  "(truststore fehlt)")]
    try:
        probe = ordner / ".diagnose-schreibprobe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as fehler:
        return _ergebnis("fehler", "Der Datenordner ist nicht beschreibbar.", details + [str(fehler)],
                         "Rechte des Ordners prüfen; bei Cloud-Ordnern (OneDrive, iCloud) die Synchronisierung "
                         "pausieren oder den Datenordner lokal anlegen.")
    frei = shutil.disk_usage(ordner).free
    details.append(f"Freier Speicher: {frei / 1024**3:.1f} GB")
    if frei < FREI_WARNUNG:
        return _ergebnis("warnung", "Auf dem Laufwerk ist weniger als 1 GB frei.", details,
                         "Speicher freigeben; Akten, Rechtsquellen und Analysen brauchen Platz.")
    return _ergebnis("ok", "Kern läuft, Datenordner beschreibbar.", details)


def _datenbanken(k: Any) -> dict:
    details, fehlerhaft = [], []
    for titel, con in (("Wissensbasis", k.con), ("Akten der Umgebung", k.akten)):
        try:
            befund = con.execute("PRAGMA quick_check").fetchone()[0]
        except sqlite3.DatabaseError as fehler:
            befund = str(fehler)
        if befund == "ok":
            details.append(f"{titel}: in Ordnung")
        else:
            fehlerhaft.append(titel)
            details.append(f"{titel}: {befund}")
    gesetze = k.con.execute("SELECT COUNT(*) FROM gesetz").fetchone()[0]
    akten = k.akten.execute("SELECT COUNT(*) FROM akte").fetchone()[0]
    details.append(f"{gesetze} Gesetze in der Wissensbasis, {akten} Akten in dieser Umgebung")
    if fehlerhaft:
        return _ergebnis("fehler", f"Beschädigt: {', '.join(fehlerhaft)}.", details,
                         "App beenden und die Datensicherung zurückspielen. Die Datei nicht von Hand ändern.")
    if gesetze == 0:
        return _ergebnis("warnung", "Datenbanken in Ordnung, aber noch keine Gesetze geladen.", details,
                         "Unter „Gesetze“ die Voreinstellung laden.")
    return _ergebnis("ok", "Datenbanken in Ordnung.", details)


def _archiv(k: Any) -> dict:
    """Jede archivierte Rechtsquelle muss vorhanden und unverändert sein (SHA-256 wie beim Abruf)."""
    zeilen = k.con.execute("""SELECT g.abk, f.sha256, f.roharchiv FROM fassung f JOIN gesetz g ON g.id = f.gesetz_id
                              WHERE f.roharchiv IS NOT NULL ORDER BY g.abk, f.id""").fetchall()
    fehlend, veraendert = [], []
    for z in zeilen:
        pfad = Path(z["roharchiv"])
        if not pfad.is_file():
            fehlend.append(z["abk"])
            continue
        h = hashlib.sha256()
        with pfad.open("rb") as datei:
            for stueck in iter(lambda: datei.read(1 << 20), b""):
                h.update(stueck)
        if h.hexdigest() != z["sha256"]:
            veraendert.append(z["abk"])
    details = [f"{len(zeilen)} archivierte Fassungen geprüft"]
    if veraendert:
        details.append("Verändert: " + ", ".join(sorted(set(veraendert))))
    if fehlend:
        details.append("Fehlt: " + ", ".join(sorted(set(fehlend))))
    if veraendert:
        return _ergebnis("fehler", "Archivierte Rechtsquellen wurden verändert.", details,
                         "Das betroffene Gesetz unter „Gesetze“ neu laden; die veränderte Datei nicht verwenden.")
    if fehlend:
        return _ergebnis("warnung", "Einzelne archivierte Rechtsquellen fehlen.", details,
                         "Das Gesetz unter „Gesetze“ neu laden, dann wird das Original wieder abgelegt.")
    return _ergebnis("ok", "Alle archivierten Rechtsquellen sind unverändert." if zeilen
                     else "Noch keine Rechtsquellen archiviert.", details)


VERSCHLUESSELUNG_HILFE = (
    "Akten und Originale liegen im Datenordner unverschlüsselt. Für Verschwiegenheit (§ 43a Abs. 2 BRAO, § 2 BORA) "
    "und Datensicherheit (Art. 32 DSGVO) die Festplatte verschlüsseln: Windows BitLocker bzw. Geräteverschlüsselung "
    "(Einstellungen → Datenschutz und Sicherheit), macOS FileVault (Systemeinstellungen → Datenschutz & Sicherheit), "
    "Linux LUKS (bei der Installation wählen)."
)


def _verschluesselung(k: Any) -> dict:
    ordner = Path(k.ki_datei).parent
    b = verschluesselung.pruefe(ordner)
    details = [*b.details, f"Datenordner: {ordner}"]
    if b.stand == verschluesselung.AN:
        return _ergebnis("ok", f"Der Datenordner liegt auf einem verschlüsselten Laufwerk ({b.verfahren}).", details)
    if b.stand == verschluesselung.AUS:
        return _ergebnis("warnung", "Das Laufwerk mit dem Datenordner ist nicht verschlüsselt.", details,
                         VERSCHLUESSELUNG_HILFE)
    return _ergebnis("warnung", "Ob das Laufwerk verschlüsselt ist, ließ sich nicht feststellen.", details,
                     "Bitte selbst prüfen. " + VERSCHLUESSELUNG_HILFE)


def _ocr(_k: Any) -> dict:
    s = ocr.status()
    if s["verfuegbar"]:
        return _ergebnis("ok", "Texterkennung für gescannte PDFs verfügbar.",
                         [f"Tesseract {s['version']}, Sprache {s['sprache']}", s["programm"]])
    return _ergebnis("warnung", "Gescannte PDFs können nicht gelesen werden.", [s["hinweis"]],
                     "Tesseract mit deutschem Sprachpaket installieren (siehe README, Abschnitt Texterkennung). "
                     "PDFs mit Textebene und Word-Dateien lassen sich auch ohne lesen.")


def _programme(k: Any) -> dict:
    eingestellt = programme.lade(k.programme_datei)
    details, fehlend = [], []
    for e in eingestellt.values():
        if not e["programm"]:
            details.append(f"{e['titel']}: Standardprogramm des Systems")
        elif programme._vorhanden(e["programm"]):
            details.append(f"{e['titel']}: {e['programm']}")
        else:
            fehlend.append(e["titel"])
            details.append(f"{e['titel']}: {e['programm']} (nicht gefunden)")
    if fehlend:
        return _ergebnis("fehler", f"Programm nicht gefunden: {', '.join(fehlend)}.", details,
                         "Unter Einstellungen → Programme das Programm neu wählen oder auf „Standardprogramm“ "
                         "zurückstellen.")
    return _ergebnis("ok", "Programme zum Öffnen und Bearbeiten sind vorhanden.", details)


# --------------------------------------------------------------------------- Sprachmodelle

def _ki_lokal(k: Any) -> dict:
    e = ki_anbieter.lade_einstellungen(k.ki_datei)
    if e.abgeschaltet:
        return _ergebnis("aus", "Die KI ist ausgeschaltet; die App fragt kein Sprachmodell.")
    s = ki_anbieter.status(e)
    netz = ki_anbieter.lokal_ort(e) == ki_anbieter.NETZWERK
    ort = s["anbieter_titel"] if e.anbieter == ki_anbieter.APPLE else f"{s['anbieter_titel']} unter {s['endpunkt']}"
    details = [ort
               + (" (anderer Rechner im eigenen Netzwerk)" if netz else " (dieser Rechner)"),
               f"Gewähltes Modell: {s['modell'] or '–'}"]
    if s["modelle"]:
        details.append(f"{len(s['modelle'])} Modelle verfügbar")
    if not s["erreichbar"]:
        return _ergebnis("fehler" if not e.extern else "warnung",
                         f"{s['anbieter_titel']} ist nicht erreichbar.", details + [s["hinweis"] or ""],
                         ("LM Studio starten, ein Modell laden und den lokalen Server einschalten (Developer → Start "
                          "Server, Port 1234)." if e.anbieter == ki_anbieter.OPENAI else
                          "Ollama starten (unter Windows über das Startmenü; das Symbol erscheint im Infobereich).")
                         + (" Auf dem anderen Rechner muss das Programm Verbindungen aus dem Netzwerk annehmen (LM "
                            "Studio: „Serve on Local Network“; Ollama: OLLAMA_HOST=0.0.0.0), und dessen Firewall "
                            "muss den Port freigeben." if netz else "")
                         + " Ist ein anderes Programm gemeint, Anbieter und Adresse unter Einstellungen ändern.")
    if not s["bereit"]:
        return _ergebnis("warnung", s["hinweis"] or "Das lokale Modell ist nicht bereit.", details,
                         "Unter Einstellungen ein installiertes Modell auswählen.")
    return _ergebnis("ok", f"{s['anbieter_titel']} antwortet, Modell {s['modell']} ist bereit.", details)


def _ki_extern(k: Any) -> dict:
    e = ki_anbieter.lade_einstellungen(k.ki_datei)
    if not e.extern_freigegeben:
        return _ergebnis("aus", "Externe KI ist nicht eingebunden; Dokumente bleiben auf dem Gerät.")
    if e.abgeschaltet:
        return _ergebnis("aus", "Die KI ist ausgeschaltet; Dokumente bleiben auf dem Gerät.")
    s = ki_anbieter.status_extern(e, k._schluessel(e), verbindung=True)
    details = [f"Anbieter: {s['anbieter_titel']}", f"Modell: {s['modell'] or '–'}",
               "Gewählt für Analyse und Chat" if e.extern else "Hinterlegt, aber „Lokal“ ist gewählt",
               "Abgefragt wurde nur die Modellliste, keine Inhalte."]
    if s["bereit"]:
        return _ergebnis("ok", f"{s['anbieter_titel']} ist erreichbar, der Schlüssel gilt.", details)
    hinweis = s["hinweis"] or "Nicht bereit."
    hilfe = "Unter Einstellungen → Externe KI Schlüssel und Modell prüfen."
    if any(t in hinweis for t in ("401", "403", "API key", "API-Schlüssel", "api_key", "x-api-key")):
        hilfe = "Der Anbieter lehnt den Schlüssel ab. Einen gültigen Schlüssel hinterlegen (Konto beim Anbieter)."
    elif "429" in hinweis:
        hilfe = "Kontingent oder Abrechnung beim Anbieter prüfen; später erneut versuchen."
    return _ergebnis("fehler" if e.extern else "warnung", hinweis, details, hilfe)


# --------------------------------------------------------------------------- Rechtsquellen im Internet

def netzfehler(fehler: BaseException, adresse: str) -> tuple[str, str]:
    """Übersetzt einen Verbindungsfehler in Meldung und Hinweis für Menschen."""
    host = urlsplit(adresse).hostname or adresse
    grund = fehler.reason if isinstance(fehler, urllib.error.URLError) and not isinstance(
        fehler, urllib.error.HTTPError) else fehler
    if isinstance(fehler, urllib.error.HTTPError):
        code = fehler.code
        if code in (401, 403):
            return (f"{host} verweigert den Zugriff (HTTP {code}).",
                    "Der Dienst blockiert die Anfrage, etwa wegen einer Sperre im Firmennetz oder einer "
                    "Änderung beim Anbieter. Im Browser prüfen, ob die Seite aufgeht.")
        if code in (404, 410):
            return (f"{host} meldet die Adresse als {'abgeschaltet' if code == 410 else 'nicht vorhanden'} "
                    f"(HTTP {code}).",
                    "Der Anbieter hat die Schnittstelle verlegt. advOrdo braucht dafür ein Update; bitte melden.")
        if code == 429:
            return (f"{host} meldet zu viele Anfragen (HTTP 429).", "Einige Minuten warten und erneut prüfen.")
        if code >= 500:
            return (f"Störung bei {host} (HTTP {code}).",
                    "Das liegt beim Anbieter, nicht an advOrdo. Später erneut versuchen.")
        return (f"{host} antwortet mit HTTP {code}.", "Die Adresse hat sich womöglich geändert; bitte melden.")
    if isinstance(grund, socket.gaierror):
        return (f"Der Name {host} lässt sich nicht auflösen.",
                "Keine Internetverbindung oder der Namensdienst (DNS) antwortet nicht. Verbindung prüfen; in "
                "Firmennetzen nach dem Proxy fragen.")
    if isinstance(grund, ssl.SSLCertVerificationError) or isinstance(grund, ssl.SSLError):
        return (f"Die sichere Verbindung zu {host} lässt sich nicht prüfen ({getattr(grund, 'reason', grund)}).",
                ("" if zertifikate.aktiv() else
                 "Der Kern prüft noch nicht mit den Zertifikaten des Systems: im Ordner von advOrdo "
                 "„pip install -e core[dev]“ ausführen und die App neu starten. Sonst ") +
                "häufige Ursachen: falsche Uhrzeit am Rechner, oder ein Virenscanner bzw. eine Firewall, die "
                "HTTPS-Verbindungen aufbricht. Datum und Uhrzeit prüfen; im Virenscanner die HTTPS-Prüfung "
                "für diese Seite ausnehmen.")
    if isinstance(grund, (TimeoutError, socket.timeout)):
        return (f"{host} antwortet nicht innerhalb von {NETZ_TIMEOUT} Sekunden.",
                "Langsame oder unterbrochene Verbindung, oder der Dienst ist überlastet. Später erneut prüfen.")
    if isinstance(grund, ConnectionRefusedError):
        return (f"{host} lehnt die Verbindung ab.", "Eine Firewall oder ein Proxy blockiert den Zugriff.")
    if isinstance(grund, OSError) and "Tunnel connection failed" in str(grund):
        return (f"Der Proxy lässt keine Verbindung zu {host} zu ({grund}).",
                "Ein Proxy im Netz (Firma, Behörde) sperrt diese Adresse. Die IT bitten, sie freizugeben.")
    if isinstance(grund, OSError):
        return (f"Keine Verbindung zu {host} ({grund}).", "Internetverbindung und Firewall prüfen.")
    return (f"Keine Verbindung zu {host} ({grund}).", "Internetverbindung prüfen.")


def abrufen(adresse: str, oeffnen: Callable[..., Any] = urllib.request.urlopen) -> tuple[int, float]:
    """Holt nur die ersten Bytes einer öffentlichen Adresse; liefert HTTP-Status und Dauer in Sekunden."""
    anfrage = urllib.request.Request(adresse, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-2047"})
    beginn = time.monotonic()
    with oeffnen(anfrage, timeout=NETZ_TIMEOUT) as antwort:
        antwort.read(2048)
        return antwort.status, time.monotonic() - beginn


def _quelle(titel: str, adresse: str, wofuer: str) -> Callable[[Any], dict]:
    def pruefen(k: Any) -> dict:
        try:
            status, dauer = abrufen(adresse, k.diagnose_oeffnen)
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            meldung, hilfe = netzfehler(fehler, adresse)
            return _ergebnis("fehler", meldung, [adresse, f"Benötigt für: {wofuer}"], hilfe)
        details = [adresse, f"Antwort in {dauer:.1f} s (HTTP {status})", f"Benötigt für: {wofuer}"]
        if dauer > 5:
            return _ergebnis("warnung", f"{titel} ist erreichbar, antwortet aber langsam.", details)
        return _ergebnis("ok", f"{titel} ist erreichbar.", details)
    return pruefen


def _neuris(k: Any) -> dict:
    if not online.einstellungen(k.quellen_datei)["neuris"]:
        return _ergebnis("aus", "NeuRIS ist ausgeschaltet (Bereich Rechtsprechung).")
    return _quelle("NeuRIS", neuris.BASIS + "/rechtsprechung?size=1", "Bundesgerichte, die im Verzeichnis fehlen")(k)


PRUEFUNGEN: list[tuple[str, str, str, Callable[[Any], dict]]] = [
    ("kern", "programm", "Kern und Datenordner", _kern),
    ("datenbanken", "programm", "Datenbanken", _datenbanken),
    ("archiv", "programm", "Archiv der Rechtsquellen (SHA-256)", _archiv),
    ("verschluesselung", "programm", "Verschlüsselung der Festplatte", _verschluesselung),
    ("ocr", "programm", "Texterkennung (Tesseract)", _ocr),
    ("programme", "programm", "Externe Programme", _programme),
    ("ki_lokal", "ki", "Lokales Sprachmodell", _ki_lokal),
    ("ki_extern", "ki", "Externe KI", _ki_extern),
    ("gii", "netz", "Gesetze im Internet",
     _quelle("Gesetze im Internet", quelle.BASIS_URL + "/gii-toc.xml", "Bundesgesetze laden und aktualisieren")),
    ("eurlex", "netz", "EUR-Lex",
     _quelle("EUR-Lex", "https://eur-lex.europa.eu/homepage.html?locale=de", "Unionsrecht (DSGVO, EuGVVO, Rom I/II)")),
    ("rii", "netz", "Rechtsprechung im Internet",
     _quelle("Rechtsprechung im Internet", verzeichnis.URL, "Verzeichnis und Volltexte der Bundesgerichte")),
    ("bayern", "netz", "Gesetze Bayern (Rechtsprechung)",
     _quelle("gesetze-bayern.de", bayern.BASIS + "/", "Entscheidungen bayerischer Gerichte")),
    ("neuris", "netz", "NeuRIS (Testphase)", _neuris),
    ("xrepository", "netz", "XRepository (Gerichtsverzeichnis)",
     _quelle("XRepository", gerichte.VERSION_URL, "Gerichtsverzeichnis (XJustiz-Codeliste GDS.Gerichte)")),
]


def liste() -> list[dict]:
    return [{"id": i, "gruppe": g, "gruppe_titel": GRUPPEN[g], "titel": t} for i, g, t, _ in PRUEFUNGEN]


def pruefe(k: Any, pruef_id: str) -> dict:
    eintrag = next((p for p in PRUEFUNGEN if p[0] == pruef_id), None)
    if eintrag is None:
        raise ValueError(f"Unbekannte Prüfung: {pruef_id}")
    beginn = time.monotonic()
    try:
        ergebnis = eintrag[3](k)
    except Exception as fehler:
        ergebnis = _ergebnis("fehler", f"Die Prüfung ist mit einem Fehler abgebrochen: {fehler}",
                             [f"{type(fehler).__name__}"], "Bitte diesen Bericht kopieren und melden.")
    ergebnis.update(id=pruef_id, gruppe=eintrag[1], titel=eintrag[2],
                    dauer_ms=round((time.monotonic() - beginn) * 1000))
    ergebnis["details"] = [d for d in ergebnis["details"] if d]
    return ergebnis
