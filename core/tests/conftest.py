from pathlib import Path

import pytest

from juracore import db
from juracore.gesetze import quelle, wissensbasis

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def con(tmp_path):
    verbindung = db.oeffne(tmp_path / "test.sqlite")
    archiv = tmp_path / "archiv"
    for name, abk in (("bgb_auszug.xml", "BGB"), ("zpo_auszug.xml", "ZPO")):
        wissensbasis.importiere(verbindung, quelle.lies_datei(FIXTURES / name, archiv, abk))
    yield verbindung
    verbindung.close()
