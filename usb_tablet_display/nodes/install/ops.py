"""Install, quiesce, backup and restore operations for the new stack."""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

ROOT_PATH = "/home/rockingsisyphus/projects/体验优化小项目/平板usb副屏"
STATE_PATH = "/tmp/usb-tablet-display"
OLD_UNITS = ("android-tablet-controller.service", "android-tablet-internet.service")
NEW_UNIT = "usb-tablet-daemon.service"


def run(argv, timeout=20):
    try:
        done = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=timeout)
        return {"code": done.returncode, "out": (done.stdout or "").strip()[:400],
                "err": (done.stderr or "").strip()[:400]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"code": None, "out": "", "err": str(error)[:400]}


def user_files(home: Path):
    units = home / ".config/systemd/user"
    return [units / NEW_UNIT, units / OLD_UNITS[0], units / OLD_UNITS[1],
            home / ".local/bin/usb-tablet",
            home / ".config/android-usb-secondary-display/tablet.toml",
            home / ".config/sunshine/sunshine.conf"]


def backup(home: Path, runner=run):
    base = home / ".local/state/usb-tablet-display/backups" / time.strftime("%Y%m%d-%H%M%S")
    base.mkdir(parents=True, exist_ok=True)
    manifest = []
    for source in user_files(home):
        existed = source.is_file()
        manifest.append({"path": str(source), "existed": existed})
        if existed:
            target = base / "files" / str(source).lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    (base / "files.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    services = []
    for unit in (NEW_UNIT, *OLD_UNITS):
        enabled = runner(["systemctl", "--user", "is-enabled", unit])
        active = runner(["systemctl", "--user", "is-active", unit])
        services.append({"unit": unit, "enabled": enabled["out"], "active": active["out"]})
    (base / "services.json").write_text(json.dumps(services, indent=2), encoding="utf-8")
    return {"action": "backup", "backup_dir": str(base), "files": len(manifest)}


def quiesce(home: Path, runner=run):
    steps = []
    for unit in (NEW_UNIT, *OLD_UNITS):
        steps.append(runner(["systemctl", "--user", "stop", unit]))
    for unit in OLD_UNITS:
        steps.append(runner(["systemctl", "--user", "disable", unit]))
    return {"action": "quiesce", "steps": len(steps),
            "active": runner(["systemctl", "--user", "is-active", NEW_UNIT])["out"]}


def install(home: Path, runner=run):
    units = home / ".config/systemd/user"
    units.mkdir(parents=True, exist_ok=True)
    source = Path(ROOT_PATH) / "services" / NEW_UNIT
    text = source.read_text(encoding="utf-8").replace("@ROOT@", ROOT_PATH)
    target = units / NEW_UNIT
    target.write_text(text, encoding="utf-8")
    bin_home = home / ".local/bin"
    bin_home.mkdir(parents=True, exist_ok=True)
    wrapper = bin_home / "usb-tablet"
    wrapper.write_text(f'#!/bin/sh\nexec python3 "{ROOT_PATH}/cli/main.py" "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    config = home / ".config/android-usb-secondary-display/tablet.toml"
    if not config.is_file():
        template = Path(ROOT_PATH) / "install" / "tablet.toml.default"
        config.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, config)
    runner(["systemctl", "--user", "daemon-reload"])
    for unit in OLD_UNITS:
        runner(["systemctl", "--user", "disable", unit])
    enabled = runner(["systemctl", "--user", "enable", "--now", NEW_UNIT])
    return {"action": "install", "unit": str(target), "cli": str(wrapper),
            "enabled": enabled["code"] == 0, "detail": enabled["err"] or enabled["out"]}


def restore(home: Path, backup_dir: Path, runner=run):
    base = Path(backup_dir)
    manifest_path = base / "files.json"
    if not manifest_path.is_file():
        return {"action": "restore", "error": f"no manifest in {base}"}
    runner(["systemctl", "--user", "disable", "--now", NEW_UNIT])
    restored = 0
    for item in json.loads(manifest_path.read_text(encoding="utf-8")):
        destination = Path(item["path"])
        if item["existed"]:
            source = base / "files" / str(destination).lstrip("/")
            if source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                restored += 1
        elif destination.exists():
            destination.unlink(missing_ok=True)
    runner(["systemctl", "--user", "daemon-reload"])
    services_path = base / "services.json"
    if services_path.is_file():
        for item in json.loads(services_path.read_text(encoding="utf-8")):
            if item["enabled"] in ("enabled", "enabled-runtime"):
                runner(["systemctl", "--user", "enable", item["unit"]])
            if item["active"] == "active":
                runner(["systemctl", "--user", "start", item["unit"]])
    return {"action": "restore", "backup_dir": str(base), "restored": restored}


def verify(home: Path, runner=run):
    unit = home / ".config/systemd/user" / NEW_UNIT
    cli = home / ".local/bin/usb-tablet"
    checks = {
        "unit_file": unit.is_file(),
        "cli_wrapper": cli.is_file() and cli.stat().st_mode & 0o111 != 0,
        "unit_enabled": runner(["systemctl", "--user", "is-enabled", NEW_UNIT])["out"] == "enabled",
        "unit_active": runner(["systemctl", "--user", "is-active", NEW_UNIT])["out"] == "active",
        "state_present": (Path(STATE_PATH) / "state.json").is_file(),
    }
    return {"action": "verify", "checks": checks, "ok": all(checks.values())}
