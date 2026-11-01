"""Manage the Sunshine screen-cast service and its streaming ports."""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from vibeflow.targets.python.sdk import node

PORTS = (47984, 47989, 47990, 48010)


def _systemctl(action: str, unit: str, timeout_s: float = 10.0) -> dict:
    try:
        done = subprocess.run(["systemctl", "--user", action, unit], capture_output=True,
                              text=True, timeout=timeout_s)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"unit": unit, "ok": False, "detail": str(error)}
    return {"unit": unit, "ok": done.returncode == 0,
            "detail": ((done.stderr or done.stdout) or "").strip()[:200]}


def _active(unit: str) -> bool:
    try:
        done = subprocess.run(["systemctl", "--user", "is-active", unit], capture_output=True,
                              text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.stdout.strip() == "active"


def _missing_ports() -> list[str]:
    try:
        done = subprocess.run(["ss", "-H", "-ltnp"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return [str(port) for port in PORTS]
    missing = []
    for port in PORTS:
        rows = [row for row in done.stdout.splitlines() if re.search(rf":{port}\s", row)]
        if not rows:
            missing.append(str(port))
    return missing


def _usb_address(interface: str) -> str:
    if not interface:
        return ""
    try:
        done = subprocess.run(["ip", "-j", "-4", "addr", "show", "dev", interface],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    import json
    try:
        rows = json.loads(done.stdout)
    except ValueError:
        return ""
    for row in rows:
        for addr in row.get("addr_info", []):
            if addr.get("scope") == "global":
                return str(addr.get("local", ""))
    return ""


@node(
    id="usb.sunshine_configure", node_type="vibeflow.node",
    display_name="Configure Sunshine",
    description="Points Sunshine capture at the virtual connector with the configured encoder and USB address.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.device", "cardinality": "exactly_one", "display_name": "USB device"},
        ],
        "provides": [{"key": "config_result", "type": "usb.config_result", "display_name": "Sunshine config result"}],
        "params_schema": {},
        "params_defaults": {},
        "input_semantics": {
            "usb.settings": ["Connector, encoder and adapter values."],
            "usb.device": ["Interface used to resolve the USB host address."],
        },
        "output_semantics": {"config_result": ["Whether sunshine.conf changed and the resolved host address."]},
    },
)
class SunshineConfigure:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        device = inputs["usb.device"]["value"]
        host_ip = _usb_address(device.get("interface", ""))
        values = {"capture": "portal", "output_name": settings["connector"],
                  "encoder": settings["sunshine_encoder"], "stream_audio": "false"}
        if host_ip:
            values.update(bind_address=host_ip, address_family="ipv4")
        if settings["sunshine_adapter"]:
            values["adapter_name"] = settings["sunshine_adapter"]
        path = Path.home() / ".config/sunshine/sunshine.conf"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        original = text
        for key, value in values.items():
            pattern = rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=.*$"
            line = f"{key} = {value}"
            text = re.sub(pattern, line, text) if re.search(pattern, text) else text + f"\n{line}\n"
        if text != original:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return {"config_result": {"changed": text != original, "host_ip": host_ip,
                                  "connector": settings["connector"]}}


@node(
    id="usb.sunshine_start", node_type="vibeflow.node",
    display_name="Start Sunshine stream",
    description="Resets a failed unit, starts Sunshine and waits for its streaming ports.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.config_result", "cardinality": "exactly_one", "display_name": "Sunshine config result"},
        ],
        "provides": [{"key": "stream_state", "type": "usb.stream_state", "display_name": "Stream state"}],
        "params_schema": {"timeout_ms": {"type": "integer"}},
        "params_defaults": {"timeout_ms": 20000},
        "input_semantics": {
            "usb.settings": ["Configuration carrying the Sunshine unit name."],
            "usb.config_result": ["Whether sunshine.conf changed and needs a restart."],
        },
        "output_semantics": {"stream_state": ["Unit state and whether all streaming ports are listening."]},
    },
)
class SunshineStart:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        changed = bool(inputs["usb.config_result"]["value"].get("changed"))
        unit = settings["sunshine_unit"]
        budget = max(int(params["timeout_ms"]), 1000) / 1000.0
        _systemctl("reset-failed", unit)
        if changed and _active(unit):
            _systemctl("stop", unit)
        result = _systemctl("start", unit)
        deadline = time.monotonic() + budget
        missing = _missing_ports()
        while missing and time.monotonic() < deadline:
            time.sleep(0.5)
            missing = _missing_ports()
        return {"stream_state": {"unit": unit, "state": "active" if _active(unit) else "inactive",
                                 "ports_missing": missing, "ok": not missing,
                                 "detail": result["detail"]}}


@node(
    id="usb.stream_verify", node_type="vibeflow.node",
    display_name="Verify stream",
    description="Checks Sunshine client events and the Moonlight activity on the tablet.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.stream_state", "cardinality": "exactly_one", "display_name": "Stream state"},
        ],
        "provides": [{"key": "stream_check", "type": "usb.stream_check", "display_name": "Stream check"}],
        "params_schema": {"timeout_ms": {"type": "integer"}},
        "params_defaults": {"timeout_ms": 5000},
        "input_semantics": {
            "usb.settings": ["ADB binary, serial and Moonlight package."],
            "usb.stream_state": ["Unit and port readiness from the start step."],
        },
        "output_semantics": {"stream_check": ["Sunshine server events and Moonlight client activity."]},
    },
)
class StreamVerify:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        unit = settings["sunshine_unit"]
        timeout = max(int(params["timeout_ms"]), 500) / 1000.0
        server = False
        try:
            invocation = subprocess.run(["systemctl", "--user", "show", unit, "-P", "InvocationID"],
                                        capture_output=True, text=True, timeout=5).stdout.strip()
            if invocation:
                done = subprocess.run(["journalctl", "--user", f"_SYSTEMD_INVOCATION_ID={invocation}",
                                       "--grep", "CLIENT (CONNECTED|DISCONNECTED)", "-n", "1",
                                       "--no-pager", "-o", "cat"],
                                      capture_output=True, text=True, timeout=5)
                events = re.findall(r"CLIENT (CONNECTED|DISCONNECTED)", done.stdout)
                server = bool(events) and events[-1] == "CONNECTED"
        except (OSError, subprocess.TimeoutExpired):
            server = False
        client = False
        try:
            done = subprocess.run([settings["adb"], "-s", settings["serial"], "shell", "dumpsys",
                                   "activity", "activities"], capture_output=True, text=True,
                                  timeout=timeout)
            client = bool(re.search(r"(?:topResumedActivity|mResumedActivity)=.*" +
                                    re.escape(settings["moonlight_package"]) + r"/\.Game\b",
                                    done.stdout))
        except (OSError, subprocess.TimeoutExpired):
            client = False
        return {"stream_check": {"server_connected": server, "client_connected": client,
                                 "connected": server and client}}


@node(
    id="usb.sunshine_stop", node_type="vibeflow.node",
    display_name="Stop Sunshine stream",
    description="Stops the Sunshine unit so no screen cast targets the virtual output before it is removed.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [{"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"}],
        "provides": [{"key": "stream_state", "type": "usb.stream_state", "display_name": "Stream state"}],
        "params_schema": {"timeout_ms": {"type": "integer"}},
        "params_defaults": {"timeout_ms": 8000},
        "input_semantics": {"usb.settings": ["Configuration carrying the Sunshine unit name."]},
        "output_semantics": {"stream_state": ["Whether the Sunshine unit is now stopped."]},
    },
)
class SunshineStop:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        unit = settings["sunshine_unit"]
        result = _systemctl("stop", unit, max(int(params["timeout_ms"]), 1000) / 1000.0)
        deadline = time.monotonic() + max(int(params["timeout_ms"]), 1000) / 1000.0
        while _active(unit) and time.monotonic() < deadline:
            time.sleep(0.1)
        return {"stream_state": {"unit": unit, "state": "stopped" if not _active(unit) else "active",
                                 "ok": not _active(unit), "detail": result["detail"]}}
