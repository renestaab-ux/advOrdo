"""Diagnose: verständliche Meldungen, ohne echtes Netz."""

import socket
import ssl
import urllib.error

import pytest

from juracore import diagnose
from juracore.rpc import Kern


@pytest.fixture
def kern(tmp_path):
    return Kern(tmp_path / "wissensbasis.sqlite", tmp_path / "archiv")


class Antwort:
    status = 206

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, n):
        return b"<xml/>"[:n]


def test_liste_und_lokale_pruefungen(kern):
    ids = [p["id"] for p in kern.methoden["diagnose.liste"]()]
    assert ids[:2] == ["kern", "datenbanken"] and "gii" in ids and "neuris" in ids
    k = kern.methoden["diagnose.pruefen"](pruef_id="kern")
    assert k["stand"] == "ok" and any(d.startswith("Freier Speicher") for d in k["details"])
    db = kern.methoden["diagnose.pruefen"](pruef_id="datenbanken")
    assert db["stand"] == "warnung" and "keine Gesetze" in db["meldung"]
    assert kern.methoden["diagnose.pruefen"](pruef_id="archiv")["stand"] == "ok"
    assert kern.methoden["diagnose.pruefen"](pruef_id="programme")["stand"] == "ok"
    assert kern.methoden["diagnose.pruefen"](pruef_id="ki_extern")["stand"] == "aus"
    assert kern.methoden["diagnose.pruefen"](pruef_id="neuris")["stand"] == "aus"
    with pytest.raises(ValueError):
        kern.methoden["diagnose.pruefen"](pruef_id="gibt-es-nicht")


def test_archiv_erkennt_veraenderte_datei(kern, tmp_path):
    datei = tmp_path / "BGB.zip"
    datei.write_bytes(b"original")
    gid = kern.con.execute("INSERT INTO gesetz (abk) VALUES ('BGB')").lastrowid
    kern.con.execute("INSERT INTO fassung (gesetz_id, sha256, quelle, abgerufen_am, roharchiv) VALUES (?, ?, ?, ?, ?)",
                     (gid, "0" * 64, "test", "2026-10-22", str(datei)))
    e = kern.methoden["diagnose.pruefen"](pruef_id="archiv")
    assert e["stand"] == "fehler" and "Verändert: BGB" in e["details"]


def test_lokales_modell_nicht_erreichbar(kern):
    e = kern.methoden["diagnose.pruefen"](pruef_id="ki_lokal")
    # Im Test läuft kein Modellprogramm; die Meldung sagt, was zu tun ist.
    assert e["stand"] == "fehler" and "starten" in e["hilfe"]


def test_quellen_erreichbar_und_fehler_verstaendlich(kern):
    kern.diagnose_oeffnen = lambda anfrage, timeout: Antwort()
    e = kern.methoden["diagnose.pruefen"](pruef_id="gii")
    assert e["stand"] == "ok" and e["details"][0].endswith("gii-toc.xml")

    def ohne_dns(anfrage, timeout):
        raise urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))
    kern.diagnose_oeffnen = ohne_dns
    e = kern.methoden["diagnose.pruefen"](pruef_id="rii")
    assert e["stand"] == "fehler" and "lässt sich nicht auflösen" in e["meldung"] and "DNS" in e["hilfe"]


@pytest.mark.parametrize(("fehler", "teil"), [
    (urllib.error.HTTPError("https://x.de", 503, "x", {}, None), "Störung bei x.de (HTTP 503)"),
    (urllib.error.HTTPError("https://x.de", 403, "x", {}, None), "verweigert den Zugriff"),
    (urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed")), "sichere Verbindung"),
    (urllib.error.URLError(TimeoutError()), "antwortet nicht innerhalb"),
    (TimeoutError(), "antwortet nicht innerhalb"),
    (urllib.error.URLError(OSError("Tunnel connection failed: 403 Forbidden")), "Der Proxy lässt keine Verbindung"),
])
def test_netzfehler(fehler, teil):
    meldung, hilfe = diagnose.netzfehler(fehler, "https://x.de/pfad")
    assert teil in meldung and hilfe
