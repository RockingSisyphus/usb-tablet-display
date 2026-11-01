"""Install workflow operations against a sandboxed home directory."""
from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from usb_tablet_display.nodes.install import ops


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
    assert result["enabled"] is True
    wrapper = home / ".local/bin/usb-tablet"
    assert wrapper.is_file() and wrapper.stat().st_mode & stat.S_IXUSR
    assert (home / ".config/usb-tablet-display/tablet.toml").read_text().strip().startswith("serial")


def test_verify_reports_all_checks(home):
    ops.install(home, runner=fake_runner())
    result = ops.verify(home, runner=fake_runner())
    assert result["ok"] is True
    assert set(result["checks"]) == {"unit_file", "cli_wrapper", "unit_enabled",
                                     "unit_active", "state_present"}


def test_restore_returns_backed_up_unit(home):
    backup = ops.backup(home, runner=fake_runner())
    ops.install(home, runner=fake_runner())
    unit = home / ".config/systemd/user/usb-tablet-daemon.service"
    assert "OLD UNIT" not in unit.read_text()
    restored = ops.restore(home, Path(backup["backup_dir"]), runner=fake_runner())
    assert restored["restored"] >= 1
    assert unit.read_text() == "OLD UNIT\n"
