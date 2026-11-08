"""Die Methoden des Kerns, je Bereich registriert. ``Kern`` fügt sie in ``Kern.methoden`` zusammen."""

from . import akten, anmerkungen, einstellungen, kanzlei, ki, rechtsquellen

TEILE = (einstellungen, rechtsquellen, akten, anmerkungen, ki, kanzlei)
