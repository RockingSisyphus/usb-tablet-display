"""Manage the Sunshine screen-cast service and its streaming ports."""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from vibeflow.targets.python.sdk import node

from usb_tablet_display.nodes.stream import session

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
    display_name="配置串流程序",
    description="让电脑端的串流程序以虚拟副屏作为画面来源，并绑定到当前 USB 网络地址。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.usb_address", "cardinality": "exactly_one", "display_name": "USB host address"},
        ],
        "provides": [{"key": "config_result", "type": "usb.config_result", "display_name": "Sunshine config result"}],
        "params_schema": {},
        "params_defaults": {},
        "input_semantics": {
            "usb.settings": ["Connector, encoder and adapter values."],
            "usb.usb_address": ["Assigned USB host address used for bind_address."],
        },
        "output_semantics": {"config_result": ["Whether sunshine.conf changed and the resolved host address."]},
    },
)
class SunshineConfigure:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        host_ip = str(inputs["usb.usb_address"]["value"].get("address", ""))
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
    display_name="启动串流程序",
    description="启动电脑端的串流程序，并等它把接收连接的端口准备好。",
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
    display_name="确认画面在传输",
    description="等待平板端的投屏程序连上，并确认电脑已经开始向平板推送画面。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    implementation_files=["session.py"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.stream_ready", "cardinality": "exactly_one", "display_name": "Stream readiness"},
            {"type": "usb.launch_state", "cardinality": "exactly_one", "display_name": "Launch state"},
        ],
        "provides": [{"key": "stream_check", "type": "usb.stream_check", "display_name": "Stream check"}],
        "params_schema": {"wait_ms": {"type": "integer"}},
        "params_defaults": {"wait_ms": 30000},
        "input_semantics": {
            "usb.settings": ["ADB binary, serial and Moonlight package."],
            "usb.stream_ready": ["Unit and port readiness from the start step."],
            "usb.launch_state": ["Launch attempt result from the Moonlight step."],
        },
        "output_semantics": {"stream_check": ["Sunshine server events and Moonlight client activity."]},
    },
)
class StreamVerify:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        deadline = time.monotonic() + max(int(params["wait_ms"]), 0) / 1000.0
        while True:
            server = session.server_connected(settings["sunshine_unit"])
            client = session.client_connected(settings)
            if server and client:
                return {"stream_check": {"server_connected": True, "client_connected": True,
                                         "connected": True}}
            if time.monotonic() >= deadline:
                return {"stream_check": {"server_connected": server, "client_connected": client,
                                         "connected": False}}
            time.sleep(1)


@node(
    id="usb.sunshine_stop", node_type="vibeflow.node",
    display_name="停止串流程序",
    description="停止电脑端的串流程序，确保移除虚拟屏幕时没有画面仍在传输。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [{"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"}],
        "provides": [{"key": "stream_state", "type": "usb.stream_state", "display_name": "Stream state"}],
        "params_schema": {"timeout_ms": {"type": "integer"}},
        "params_defaults": {"timeout_ms": 20000},
        "input_semantics": {"usb.settings": ["Configuration carrying the Sunshine unit name."]},
        "output_semantics": {"stream_state": ["Unit identity and whether it is stopped."]},
    },
)
class SunshineStop:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        unit = settings["sunshine_unit"]
        deadline = time.monotonic() + max(int(params["timeout_ms"]), 1000) / 1000.0
        _systemctl("stop", unit)
        while _active(unit) and time.monotonic() < deadline:
            time.sleep(0.1)
        return {"stream_state": {"unit": unit, "state": "stopped" if not _active(unit) else "active",
                                 "ok": not _active(unit)}}


@node(
    id="usb.sunshine_ready", node_type="vibeflow.node",
    implementation_files=["session.py"],
    display_name="让串流程序就绪",
    description="如果录屏授权刚刚发生变化，就重启一次串流程序，并重新等它准备好。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.stream_state", "cardinality": "exactly_one", "display_name": "Stream state"},
            {"type": "usb.portal_state", "cardinality": "exactly_one", "display_name": "Portal state"},
        ],
        "provides": [{"key": "stream_ready", "type": "usb.stream_ready", "display_name": "Stream readiness"}],
        "params_schema": {"timeout_ms": {"type": "integer"}, "restart_if_unconnected": {"type": "boolean"}},
        "params_defaults": {"timeout_ms": 20000, "restart_if_unconnected": True},
        "input_semantics": {
            "usb.settings": ["Sunshine unit name."],
            "usb.stream_state": ["Current unit and port state."],
            "usb.portal_state": ["Whether portal authorization changed."],
        },
        "output_semantics": {"stream_ready": ["Unit state and whether every streaming port is listening."]},
    },
)
class SunshineReady:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        portal = inputs["usb.portal_state"]["value"]
        unit = settings["sunshine_unit"]
        restart = bool(portal.get("changed"))
        if params.get("restart_if_unconnected", True) and not restart:
            if not session.connected(settings):
                restart = True
        if restart:
            _systemctl("stop", unit)
            _systemctl("start", unit)
        deadline = time.monotonic() + max(int(params["timeout_ms"]), 1000) / 1000.0
        missing = _missing_ports()
        while missing and time.monotonic() < deadline:
            time.sleep(0.5)
            missing = _missing_ports()
        return {"stream_ready": {"unit": unit, "restarted": restart,
                                 "ports_missing": missing, "ok": not missing}}
