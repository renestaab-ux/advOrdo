"""Zertifikatsprüfung über den Zertifikatsspeicher des Betriebssystems.

Python prüft TLS-Zertifikate sonst mit einer eigenen Liste und lädt fehlende
Zwischenzertifikate nicht nach. Manche Server liefern ihre Kette unvollständig aus,
Virenscanner und Firmen-Proxys setzen eigene Stammzertifikate ein; der Browser kommt
damit zurecht, Python meldet „unable to get local issuer certificate“. Mit
``truststore`` prüft der Kern wie der Browser: über Windows, macOS bzw. die
Zertifikate des Linux-Systems.
"""

from __future__ import annotations

_aktiv = False


def systemzertifikate_nutzen() -> bool:
    """Stellt die Prüfung für alle Abrufe des Kerns auf den Systemspeicher um; ``False``, wenn truststore fehlt."""
    global _aktiv
    if _aktiv:
        return True
    try:
        import truststore
    except ImportError:
        return False
    truststore.inject_into_ssl()
    _aktiv = True
    return True


def aktiv() -> bool:
    return _aktiv
