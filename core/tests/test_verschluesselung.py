import sys

import pytest

from juracore import verschluesselung as v

MOUNTINFO = (
    "22 1 253:1 / / rw,relatime shared:1 - ext4 /dev/mapper/vgzorin-root rw\n"
    "30 22 259:2 / /boot rw,relatime shared:2 - ext4 /dev/nvme0n1p2 rw\n"
    "40 22 0:50 / /home/rene/Privat rw shared:3 - ecryptfs /home/rene/.Private rw\n"
)


def _sys(tmp_path):
    """/sys/dev/block mit LVM (253:1) auf LUKS (dm-0) auf nvme0n1p3 und einer unverschlüsselten Partition.

    Im echten sysfs sind die Einträge unter slaves Verweise auf das Gerät; hier sind es gleich die Ordner
    (Verweise braucht unter Windows Sonderrechte)."""
    block = tmp_path / "block"
    lvm = block / "253:1"
    luks = lvm / "slaves" / "dm-0"
    for ordner, uuid in ((lvm, "LVM-xyz"), (luks, "CRYPT-LUKS2-abc-luks")):
        (ordner / "dm").mkdir(parents=True)
        (ordner / "dm" / "uuid").write_text(uuid + "\n")
    (luks / "slaves" / "nvme0n1p3").mkdir(parents=True)
    (block / "259:2").mkdir()
    return block


GERAETE = {"/dev/mapper/vgzorin-root": (253, 1), "/dev/nvme0n1p2": (259, 2)}


NUR_UNIX = pytest.mark.skipif(sys.platform == "win32", reason="Ordnernamen wie 253:1 (sysfs) sind unter Windows unzulässig")


@NUR_UNIX
def test_linux_luks_unter_lvm(tmp_path):
    b = v._linux(tmp_path / "x", _sys(tmp_path), MOUNTINFO.replace(" / / ", f" / {tmp_path} ", 1),
                 GERAETE.__getitem__)
    assert b.stand == v.AN and "LUKS" in b.verfahren


@NUR_UNIX
def test_linux_unverschluesselt_und_ecryptfs(tmp_path):
    block = _sys(tmp_path)
    from pathlib import Path
    b = v._linux(Path("/boot/efi"), block, MOUNTINFO, GERAETE.__getitem__)
    assert b.stand == v.AUS
    # Der Pfad liegt unter tmp_path: _linux löst Verweise auf, und unter macOS ist /home ein Verweis.
    privat = tmp_path / "Privat"
    b = v._linux(privat / "advOrdo", block, MOUNTINFO.replace("/home/rene/Privat", str(privat)),
                 GERAETE.__getitem__)
    assert b.stand == v.AN and b.verfahren == "ecryptfs"


def test_windows_bitlocker(monkeypatch, tmp_path):
    from pathlib import PureWindowsPath
    aufrufe = []
    for wert, stand in (("1", v.AN), ("2", v.AUS), ("5", v.AUS), ("", v.UNBEKANNT)):
        monkeypatch.setattr(v, "_ausfuehren", lambda befehl, w=wert: aufrufe.append(befehl) or w)
        assert v._windows(PureWindowsPath(r"C:\Users\x\AppData\Roaming\jb")).stand == stand
    assert aufrufe[0][0].lower().endswith("powershell.exe") and "'C:\\'" in aufrufe[0][-1]
    assert v._windows(PureWindowsPath(r"\\server\freigabe\jb")).stand == v.UNBEKANNT


def test_macos_filevault(monkeypatch, tmp_path):
    monkeypatch.setattr(v, "_ausfuehren", lambda befehl: "FileVault is On.")
    assert v.pruefe(tmp_path, "darwin").stand == v.AN
    monkeypatch.setattr(v, "_ausfuehren", lambda befehl: "FileVault is Off.")
    assert v.pruefe(tmp_path, "darwin").stand == v.AUS
