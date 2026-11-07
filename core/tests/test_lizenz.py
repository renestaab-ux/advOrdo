from pathlib import Path

CORE = Path(__file__).resolve().parents[1]


def test_lizenz_im_paket_gleich_der_im_hauptordner():
    """core/LICENSE kommt ins Python-Paket; sie muss dem Lizenztext im Hauptordner entsprechen."""
    haupt = CORE.parent / "LICENSE"
    assert (CORE / "LICENSE").read_bytes() == haupt.read_bytes()
    assert haupt.read_text(encoding="utf-8").startswith("EUROPEAN UNION PUBLIC LICENCE v. 1.2")
