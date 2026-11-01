"""Install workflow operations against a sandboxed home directory."""
from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from usb_tablet_maintenance.nodes.install import ops


def fake_runner(active=True, enabled=True):
    def run(argv):
        if "--user" in argv and "is-active" in argv:
            return {"code": 0, "out": "active" if active else "inactive", "err": ""}
        if "--user" in argv and "is-enabled" in argv:
            return {"code": 0, "out": "enabled" if enabled else "disabled", "err": ""}
        return {"code": 0, "out": "", "err": ""}
    return run


@pytest.fixture()
def home(tmp_path):
    home = tmp_path / "home"
    (home / ".config/systemd/user").mkdir(parents=True)
    (home / ".config/systemd/user/usb-tablet-daemon.service").write_text("OLD UNIT\n")
    (home / ".config/usb-tablet-display").mkdir(parents=True)
    (home / ".config/usb-tablet-display/tablet.toml").write_text('serial = "X"\n')
    return home


def test_backup_writes_manifest_and_copies_existing_files(home):
    result = ops.backup(home, runner=fake_runner())
    base = Path(result["backup_dir"])
    manifest = json.loads((base / "files.json").read_text())
    paths = {item["path"] for item in manifest}
    assert str(home / ".config/systemd/user/usb-tablet-daemon.service") in paths
    copied = base / "files" / str(home / ".config/systemd/user/usb-tablet-daemon.service").lstrip("/")
    assert copied.read_text() == "OLD UNIT\n"


def test_install_writes_unit_cli_and_template(home):
    result = ops.install(home, runner=fake_runner())
    unit = home / ".config/systemd/user/usb-tablet-daemon.service"
    assert "ExecStart" in unit.read_text()
    desktop = home / ".local/share/applications/usb-tablet-display.desktop"
    assert desktop.is_file() and "gui/app.py" in desktop.read_text()
    assert result["enabled"] is True
    wrapper = home / ".local/bin/usb-tablet"
    assert wrapper.is_file() and wrapper.stat().st_mode & stat.S_IXUSR
    assert (home / ".config/usb-tablet-display/tablet.toml").read_text().strip().startswith("serial")


def test_autofill_uses_single_adb_device_and_hostname(home, monkeypatch):
    calls = []
    monkeypatch.setattr(ops, "_action_output", lambda argv, timeout=10: (
        "List of devices attached\nSER123\tdevice\n" if "devices" in argv else ""))
    result = ops.autofill_config(home)
    text = (home / ".config/usb-tablet-display/tablet.toml").read_text()
    assert 'serial = "SER123"' in text
    assert "host_name" in text
    assert result["filled"] is True


def test_verify_reports_all_checks(home):
    ops.install(home, runner=fake_runner())
    result = ops.verify(home, runner=fake_runner())
    assert set(result["checks"]) >= {"unit_file", "desktop_entry"}
    required = {"unit_file", "coordinator_unit", "internet_unit", "cli_wrapper",
                "unit_enabled", "unit_active", "coordinator_active", "tablet_serial",
                "python_3_11", "adb", "systemctl"}
    assert required <= set(result["checks"])
    assert isinstance(result["hints"], list)
    # 环境相关项（扩展是否加载、系统软件）由真实机器决定，这里只校验结构


def test_restore_returns_backed_up_unit(home):
    backup = ops.backup(home, runner=fake_runner())
    ops.install(home, runner=fake_runner())
    unit = home / ".config/systemd/user/usb-tablet-daemon.service"
    assert "OLD UNIT" not in unit.read_text()
    restored = ops.restore(home, Path(backup["backup_dir"]), runner=fake_runner())
    assert restored["restored"] >= 1
    assert unit.read_text() == "OLD UNIT\n"
