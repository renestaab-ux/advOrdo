import os

from juracore import verschluesselung as v

MOUNTINFO = (
    "22 1 253:1 / / rw,relatime shared:1 - ext4 /dev/mapper/vgzorin-root rw\n"
    "30 22 259:2 / /boot rw,relatime shared:2 - ext4 /dev/nvme0n1p2 rw\n"
    "40 22 0:50 / /home/rene/Privat rw shared:3 - ecryptfs /home/rene/.Private rw\n"
)


def _sys(tmp_path):
    """/sys/dev/block mit LVM (253:1) auf LUKS (253:0) auf nvme0n1p3 und einer unverschlüsselten Partition."""
    block = tmp_path / "block"
    for name, uuid in (("253:0", "CRYPT-LUKS2-abc-luks"), ("253:1", "LVM-xyz"), ("259:2", None), ("259:3", None)):
        (block / name).mkdir(parents=True)
        if uuid:
            (block / name / "dm").mkdir()
            (block / name / "dm" / "uuid").write_text(uuid + "\n")
    (block / "253:1" / "slaves").mkdir()
    os.symlink(block / "253:0", block / "253:1" / "slaves" / "dm-0")
    (block / "253:0" / "slaves").mkdir()
    os.symlink(block / "259:3", block / "253:0" / "slaves" / "nvme0n1p3")
    return block


GERAETE = {"/dev/mapper/vgzorin-root": os.makedev(253, 1), "/dev/nvme0n1p2": os.makedev(259, 2)}


def test_linux_luks_unter_lvm(tmp_path):
    b = v._linux(tmp_path / "x", _sys(tmp_path), MOUNTINFO.replace(" / / ", f" / {tmp_path} ", 1),
                 GERAETE.__getitem__)
    assert b.stand == v.AN and "LUKS" in b.verfahren


def test_linux_unverschluesselt_und_ecryptfs(tmp_path):
    block = _sys(tmp_path)
    from pathlib import Path
    b = v._linux(Path("/boot/efi"), block, MOUNTINFO, GERAETE.__getitem__)
    assert b.stand == v.AUS
    b = v._linux(Path("/home/rene/Privat/JuraBox"), block, MOUNTINFO, GERAETE.__getitem__)
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
