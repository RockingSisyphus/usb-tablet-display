"""Install, quiesce, backup and restore operations for the new stack."""
from __future__ import annotations

import importlib.util
import json
import socket
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT_PATH = "/home/rockingsisyphus/projects/体验优化小项目/平板usb副屏"
STATE_PATH = "/tmp/usb-tablet-display"
NEW_UNIT = "usb-tablet-daemon.service"
NEW_INTERNET_UNIT = "usb-tablet-internet.service"
NEW_COORDINATOR_UNIT = "usb-tablet-coordinator.service"
EXTENSION = "android-tablet-auto-keep-display@rockingsisyphus.local"


def run(argv, timeout=20):
    try:
        done = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=timeout)
        return {"code": done.returncode, "out": (done.stdout or "").strip()[:400],
                "err": (done.stderr or "").strip()[:400]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"code": None, "out": "", "err": str(error)[:400]}


def user_files(home: Path):
    units = home / ".config/systemd/user"
    return [units / NEW_UNIT, units / NEW_INTERNET_UNIT, units / NEW_COORDINATOR_UNIT,
            home / ".local/bin/usb-tablet",
            home / ".config/usb-tablet-display/tablet.toml",
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
    for unit in (NEW_UNIT, NEW_INTERNET_UNIT, NEW_COORDINATOR_UNIT):
        enabled = runner(["systemctl", "--user", "is-enabled", unit])
        active = runner(["systemctl", "--user", "is-active", unit])
        services.append({"unit": unit, "enabled": enabled["out"], "active": active["out"]})
    (base / "services.json").write_text(json.dumps(services, indent=2), encoding="utf-8")
    return {"action": "backup", "backup_dir": str(base), "files": len(manifest)}


def quiesce(home: Path, runner=run):
    steps = []
    for unit in (NEW_UNIT, NEW_INTERNET_UNIT, NEW_COORDINATOR_UNIT):
        steps.append(runner(["systemctl", "--user", "stop", unit]))
    return {"action": "quiesce", "steps": len(steps),
            "active": runner(["systemctl", "--user", "is-active", NEW_UNIT])["out"]}


def install(home: Path, runner=run):
    units = home / ".config/systemd/user"
    units.mkdir(parents=True, exist_ok=True)
    for name in (NEW_UNIT, NEW_INTERNET_UNIT, NEW_COORDINATOR_UNIT):
        source = Path(ROOT_PATH) / "services" / name
        text = source.read_text(encoding="utf-8")
        if "@ROOT@" not in text:
            raise RuntimeError(f"{name} lost its @ROOT@ placeholder")
        (units / name).write_text(text.replace("@ROOT@", ROOT_PATH), encoding="utf-8")
    target = units / NEW_UNIT
    extension_source = Path(ROOT_PATH) / "gnome-shell-ext" / EXTENSION
    extension_target = home / ".local/share/gnome-shell/extensions" / EXTENSION
    if extension_source.is_dir():
        extension_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(extension_source, extension_target, dirs_exist_ok=True)
        runner(["gnome-extensions", "enable", EXTENSION])
    bin_home = home / ".local/bin"
    bin_home.mkdir(parents=True, exist_ok=True)
    wrapper = bin_home / "usb-tablet"
    wrapper.write_text(f'#!/bin/sh\nexec python3 "{ROOT_PATH}/cli/main.py" "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    config = home / ".config/usb-tablet-display/tablet.toml"
    if not config.is_file():
        template = Path(ROOT_PATH) / "install" / "tablet.toml.default"
        config.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, config)
    autofill = autofill_config(home)
    runner(["systemctl", "--user", "daemon-reload"])
    enabled = runner(["systemctl", "--user", "enable", "--now", NEW_UNIT])
    return {"action": "install", "autofill": autofill, "unit": str(target), "internet_unit": str(units / NEW_INTERNET_UNIT),
            "extension": str(extension_target), "cli": str(wrapper),
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


def _which(name):
    return shutil.which(name) is not None


def _action_output(argv, timeout=10):
    try:
        done = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=timeout)
        return done.stdout or ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _tablet_serial(home: Path):
    config = home / ".config/usb-tablet-display/tablet.toml"
    if not config.is_file():
        return ""
    for line in config.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("serial"):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def _adb_serials():
    lines = _action_output(["adb", "devices"]).splitlines()[1:]
    return [line.split("\t")[0].strip() for line in lines if line.endswith("device")]


def _set_toml_value(text, key, value):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith(key + " ") or line.strip().startswith(key + "="):
            lines[index] = f'{key} = "{value}"'
            return "\n".join(lines) + "\n"
    return "\n".join(lines) + f'\n{key} = "{value}"\n'


def autofill_config(home: Path):
    config = home / ".config/usb-tablet-display/tablet.toml"
    if not config.is_file():
        return {"filled": False, "reason": "配置不存在"}
    text = config.read_text(encoding="utf-8")
    filled = []
    serials = _adb_serials()
    if len(serials) == 1:
        text = _set_toml_value(text, "serial", serials[0])
        filled.append(f"serial={serials[0]}")
    host = socket.gethostname().split(".")[0]
    if host:
        text = _set_toml_value(text, "host_name", host)
        filled.append(f"host_name={host}")
    config.write_text(text, encoding="utf-8")
    return {"filled": True, "fields": filled,
            "reason": "" if len(serials) == 1 else "未检测到唯一的平板，保持原有序列号"}


def _device_apps():
    if not _which("adb"):
        return {"installed": False, "reason": "adb 不可用"}
    state = _action_output(["adb", "get-state"]).strip()
    if state != "device":
        return {"installed": False, "reason": f"平板未连接（adb 状态：{state or '未知'}）"}
    listed = _action_output(["adb", "shell", "pm", "list", "packages", "com.genymobile.gnirehtet"])
    if "com.genymobile.gnirehtet" in listed:
        return {"installed": True, "reason": "已安装"}
    apk = Path(ROOT_PATH) / "vendor" / "gnirehtet" / "gnirehtet.apk"
    if not apk.is_file():
        return {"installed": False, "reason": "项目内缺少 gnirehtet.apk"}
    result = run(["adb", "install", "-r", str(apk)], timeout=120)
    return {"installed": result["code"] == 0, "reason": result["out"] or result["err"]}


def _network_hint():
    names = _action_output(["nmcli", "-t", "-f", "NAME", "connection", "show"]).splitlines()
    if "android-usb-direct" in names:
        return {"present": True, "hint": ""}
    hint = ("nmcli connection add type ethernet ifname '*' con-name android-usb-direct "
            "ipv4.method auto ipv4.never-default yes ipv4.ignore-auto-routes yes "
            "ipv4.ignore-auto-dns yes ipv6.method disabled")
    return {"present": False, "hint": hint}


def verify(home: Path, runner=run):
    unit = home / ".config/systemd/user" / NEW_UNIT
    cli = home / ".local/bin/usb-tablet"
    extension = home / ".local/share/gnome-shell/extensions" / EXTENSION
    checks = {
        "python_3_11": sys.version_info >= (3, 11),
        "pygobject": importlib.util.find_spec("gi") is not None,
        "adb": _which("adb"),
        "systemctl": _which("systemctl"),
        "gnome_extensions": _which("gnome-extensions"),
        "network_manager": _which("nmcli"),
        "unit_file": unit.is_file(),
        "coordinator_unit": (home / ".config/systemd/user" / NEW_COORDINATOR_UNIT).is_file(),
        "internet_unit": (home / ".config/systemd/user" / NEW_INTERNET_UNIT).is_file(),
        "cli_wrapper": cli.is_file() and bool(cli.stat().st_mode & 0o111),
        "extension_installed": extension.is_dir(),
        "unit_enabled": runner(["systemctl", "--user", "is-enabled", NEW_UNIT])["out"] == "enabled",
        "unit_active": runner(["systemctl", "--user", "is-active", NEW_UNIT])["out"] == "active",
        "coordinator_active": runner(["systemctl", "--user", "is-active", NEW_COORDINATOR_UNIT])["out"] == "active",
        "sunshine_installed": "app-dev.lizardbyte.app.Sunshine.service" in _action_output(
            ["systemctl", "--user", "list-unit-files", "--no-legend"]),
        "network_profile": _network_hint()["present"],
        "tablet_serial": bool(_tablet_serial(home)),
        "state_present": (Path(STATE_PATH) / "state.json").is_file(),
    }
    hints = []
    if not checks["network_profile"]:
        hints.append("缺少 NetworkManager 连接 android-usb-direct：" + _network_hint()["hint"])
    if not checks["sunshine_installed"]:
        hints.append("未安装 Sunshine，串流无法启动")
    if not checks["tablet_serial"]:
        hints.append("tablet.toml 缺少 serial")
    if not checks["pygobject"]:
        hints.append("缺少 PyGObject（python3-gi）")
    return {"action": "verify", "checks": checks, "hints": hints, "ok": all(checks.values())}


def install_all(home: Path, runner=run):
    installed = install(home, runner)
    device = _device_apps()
    network = _network_hint()
    verified = verify(home, runner)
    return {"action": "all", "install": installed, "device": device,
            "network": network, "verify": verified, "ok": verified["ok"]}
