"""Abbrechen eines KI-Auftrags wirkt sofort, auch während das Modell an einer Antwort rechnet."""

from __future__ import annotations

import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from juracore import netzprotokoll
from juracore.ki import anbieter
from juracore.ki.analyse import Abgebrochen
from juracore.ki.apple import AppleIntelligence
from juracore.ki.auftraege import Auftraege


def _warte(abfrage, bis=3.0):
    ende = time.monotonic() + bis
    while time.monotonic() < ende:
        stand = abfrage()
        if stand["status"] != "laeuft":
            return stand
        time.sleep(0.02)
    raise AssertionError("Auftrag läuft zu lange")


class _Rechnet(BaseHTTPRequestHandler):
    """Ein Modell, das nie fertig wird: nimmt die Anfrage an und merkt, wenn der Client die Verbindung trennt."""

    angefragt = threading.Event()
    getrennt = threading.Event()

    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers["Content-Length"]))
        _Rechnet.angefragt.set()
        self.connection.settimeout(10)
        try:
            if self.connection.recv(1) == b"":  # Client hat getrennt, wie LM Studio es bemerkt
                _Rechnet.getrennt.set()
        except OSError:
            _Rechnet.getrennt.set()

    def log_message(self, *args):
        pass


@pytest.fixture
def rechnendes_modell():
    _Rechnet.angefragt.clear()
    _Rechnet.getrennt.clear()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Rechnet)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_abbruch_trennt_laufende_anfrage_an_das_modell(rechnendes_modell):
    auftraege = Auftraege()
    modell = anbieter.OpenAIKompatibel(rechnendes_modell, "mistral-small", 8192)
    a = auftraege.starte("chat", lambda auftrag: modell.chat("System", "Frage", {"type": "object"}))
    assert _Rechnet.angefragt.wait(3)
    beginn = time.monotonic()
    stand = auftraege.abbrechen(a["auftrag_id"])
    assert stand["abbruch"] is True and stand["text"] == "Wird abgebrochen …"
    stand = _warte(lambda: auftraege.status(a["auftrag_id"]))
    assert stand["status"] == "abgebrochen" and stand["fehler"] is None and stand["abbruch"] is False
    assert time.monotonic() - beginn < 2
    assert _Rechnet.getrennt.wait(2), "das Modell hat den Abbruch nicht bemerkt"


def test_abbruch_waehrend_mehrerer_anfragen_stellt_keine_weitere(rechnendes_modell):
    """Wie die Klauselprüfung je Paragraph: Ein Fehler der einen Anfrage wird abgefangen, die nächste folgt."""
    auftraege = Auftraege()
    modell = anbieter.OpenAIKompatibel(rechnendes_modell, "mistral-small", 8192)
    gestellt = []

    def arbeit(auftrag):
        for nr in range(5):
            gestellt.append(nr)
            try:
                modell.chat("System", f"Klausel {nr}", {"type": "object"})
            except anbieter.KiFehler:
                continue
        return {"fertig": True}

    a = auftraege.starte("chat", arbeit)
    assert _Rechnet.angefragt.wait(3)
    auftraege.abbrechen(a["auftrag_id"])
    assert _warte(lambda: auftraege.status(a["auftrag_id"]))["status"] == "abgebrochen"
    assert gestellt == [0]


def test_fehler_nach_dem_abbruch_gilt_als_abbruch():
    auftraege = Auftraege()
    weiter = threading.Event()

    def arbeit(auftrag):
        weiter.wait(3)
        raise RuntimeError("Folgefehler")

    a = auftraege.starte("test", arbeit)
    auftraege.abbrechen(a["auftrag_id"])
    weiter.set()
    stand = _warte(lambda: auftraege.status(a["auftrag_id"]))
    assert stand["status"] == "abgebrochen" and stand["fehler"] is None


def test_ergebnis_nach_dem_abbruch_wird_verworfen():
    auftraege = Auftraege()
    weiter = threading.Event()
    a = auftraege.starte("test", lambda auftrag: weiter.wait(3) and {"ok": True})
    auftraege.abbrechen(a["auftrag_id"])
    weiter.set()
    stand = _warte(lambda: auftraege.status(a["auftrag_id"]))
    assert stand["status"] == "abgebrochen" and stand["ergebnis"] is None


def test_verbindung_nach_dem_trennen_wird_sofort_getrennt():
    leitungen = netzprotokoll.Leitungen()
    leitungen.trennen()
    a, b = socket.socketpair()
    with a, b:
        leitungen.merken(a)
        assert b.recv(1) == b""


def test_warten_endet_beim_abbruch():
    leitungen = netzprotokoll.Leitungen()
    abgebrochen = threading.Event()

    def pruefe():
        if abgebrochen.is_set():
            raise Abgebrochen()

    def abbrechen():
        time.sleep(0.1)
        abgebrochen.set()
        leitungen.trennen()

    threading.Thread(target=abbrechen, daemon=True).start()
    beginn = time.monotonic()
    with netzprotokoll.abbrechbar(pruefe, leitungen), pytest.raises(Abgebrochen):
        netzprotokoll.warten(30)
    assert time.monotonic() - beginn < 2


@pytest.mark.skipif(sys.platform == "win32", reason="Hilfsprogramm als Shell-Skript")
def test_abbruch_beendet_das_hilfsprogramm_von_apple_intelligence(tmp_path):
    hilfe = tmp_path / "advordo-apple-ki"
    hilfe.write_text("#!/bin/sh\nexec sleep 30\n")
    hilfe.chmod(0o755)
    modell = AppleIntelligence(pfad=hilfe)
    auftraege = Auftraege()
    a = auftraege.starte("chat", lambda auftrag: modell.chat("System", "Frage", {"type": "object"}))
    time.sleep(0.3)
    beginn = time.monotonic()
    auftraege.abbrechen(a["auftrag_id"])
    assert _warte(lambda: auftraege.status(a["auftrag_id"]))["status"] == "abgebrochen"
    assert time.monotonic() - beginn < 2
