"""Render the published status document from the current probe results."""
from __future__ import annotations

import json
import os
from pathlib import Path

from vibeflow.targets.python.sdk import node

DEFAULT_STATE_PATH = "/tmp/usb-tablet-display/state.json"
PENDING = ("stream", "internet", "power", "battery", "portal", "sunshine", "moonlight", "vpn")


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
            "stream": "unknown",
            "internet": "unknown",
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
