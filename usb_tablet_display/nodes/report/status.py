"""Render the published status document from the current probe results."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from vibeflow.targets.python.sdk import node

DEFAULT_STATE_PATH = "/tmp/usb-tablet-display/state.json"
PENDING = ("stream", "internet", "power", "battery", "portal", "sunshine", "moonlight", "vpn")


def _unit_active(unit: str) -> bool:
    done = subprocess.run(["systemctl", "--user", "is-active", unit],
                          capture_output=True, text=True, timeout=5)
    return done.stdout.strip() == "active"


def _adb(settings, args, timeout=8):
    try:
        return subprocess.run([settings["adb"], "-s", settings["serial"], "shell", *args],
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _stream_state(settings) -> str:
    unit = settings["sunshine_unit"]
    if not _unit_active(unit):
        return "idle"
    shown = subprocess.run(["systemctl", "--user", "show", unit, "-P", "InvocationID"],
                           capture_output=True, text=True, timeout=5)
    invocation = shown.stdout.strip()
    server = False
    if invocation:
        log = subprocess.run(["journalctl", "--user", f"_SYSTEMD_INVOCATION_ID={invocation}",
                              "--grep", "CLIENT (CONNECTED|DISCONNECTED)", "-n", "1",
                              "--no-pager", "-o", "cat"], capture_output=True, text=True, timeout=5)
        events = re.findall(r"CLIENT (CONNECTED|DISCONNECTED)", log.stdout)
        server = bool(events) and events[-1] == "CONNECTED"
    done = _adb(settings, ["dumpsys", "activity", "activities"])
    client = bool(done and re.search(
        r"(?:topResumedActivity|mResumedActivity)=.*" + re.escape(settings["moonlight_package"]) + r"/\.Game\b",
        done.stdout))
    return "connected" if server and client else "connecting"


def _internet_state(settings) -> str:
    if not _unit_active(settings["vpn_unit"]):
        return "disconnected"
    done = _adb(settings, ["dumpsys", "connectivity"], 10)
    present = bool(done and any("VPN:com.genymobile.gnirehtet" in row and "InterfaceName: tun0" in row
                                for row in done.stdout.splitlines()))
    if not present:
        return "unavailable"
    for url in settings["probe_urls"]:
        probe = _adb(settings, ["/system/bin/curl", "-4", "--interface", "tun0", "-fsS",
                                "-o", "/dev/null", "--connect-timeout", "3", "--max-time", "5", url], 9)
        if probe is not None and probe.returncode == 0:
            return "ok"
    return "unavailable"


def _display_state(check: dict) -> str:
    target = str(check.get("target", "enable"))
    if check.get("matches"):
        return "enabled" if target == "enable" else "disabled"
    return "pending"


@node(
    id="usb.build_status", node_type="vibeflow.node",
    display_name="Build status",
    description="Composes the published status document from settings, state, probe and layout results.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.state", "cardinality": "exactly_one", "display_name": "Runtime state"},
            {"type": "usb.device", "cardinality": "exactly_one", "display_name": "USB device"},
            {"type": "usb.adb_state", "cardinality": "exactly_one", "display_name": "ADB transport state"},
            {"type": "usb.display_check", "cardinality": "exactly_one", "display_name": "Display match result"},
        ],
        "provides": [{"key": "status", "type": "usb.status", "display_name": "Status document"}],
        "params_schema": {"state_path": {"type": "string"}},
        "params_defaults": {"state_path": DEFAULT_STATE_PATH},
        "input_semantics": {
            "usb.settings": ["Configuration for the published status."],
            "usb.state": ["Persisted runtime state from earlier ticks."],
            "usb.device": ["USB presence and interface."],
            "usb.adb_state": ["ADB transport state."],
            "usb.display_check": ["Whether the layout currently matches the target."],
        },
        "output_semantics": {"status": ["Status document using the historical field names."]},
    },
)
class BuildStatus:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        state = inputs["usb.state"]["value"]
        device = inputs["usb.device"]["value"]
        adb = inputs["usb.adb_state"]["value"]
        check = inputs["usb.display_check"]["value"]
        status = {
            "usb": "present" if device.get("present") else "absent",
            "adb": adb.get("state", "unavailable"),
            "display": _display_state(check),
            "stream": _stream_state(settings),
            "internet": _internet_state(settings),
            "power": "unknown",
            "battery": "unknown",
            "host_ip": "",
            "usb_interface": device.get("interface", ""),
            "serial": settings["serial"],
            "auto_enabled": bool(state.get("auto_enabled", False)),
            "ticks": int(state.get("ticks") or 0),
            "updated_at": state.get("updated_at"),
            "pending_migration": list(PENDING),
        }
        path = Path(params["state_path"])
        merged = {**state, "status": status}
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return {"status": status}
