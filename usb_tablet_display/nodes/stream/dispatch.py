"""Decide and run the automatic session from the daemon loop."""
from __future__ import annotations

import subprocess

from vibeflow.targets.python.sdk import node

from usb_tablet_display.nodes.stream import session

ROOT = "/home/rockingsisyphus/projects/体验优化小项目/平板usb副屏"


def _value(inputs, key):
    return inputs[key]["value"]


@node(
    id="usb.session_status", node_type="vibeflow.node",
    display_name="Read session status",
    description="Reads Sunshine and Moonlight state so the loop can decide whether a session exists.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    implementation_files=["session.py"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.device", "cardinality": "exactly_one", "display_name": "USB device"},
        ],
        "provides": [{"key": "session_status", "type": "usb.session_status", "display_name": "Session status"}],
        "params_schema": {},
        "params_defaults": {},
        "input_semantics": {
            "usb.settings": ["Sunshine unit, ADB serial and Moonlight package."],
            "usb.device": ["Interface used to resolve the current USB address."],
        },
        "output_semantics": {"session_status": ["Whether a client and the Moonlight game are both active."]},
    },
)
class SessionStatus:
    def run_pure(self, inputs, params):
        settings = _value(inputs, "usb.settings")
        address = session.usb_address(_value(inputs, "usb.device").get("interface", ""))
        return {"session_status": {"connected": session.connected(settings, address)}}


@node(
    id="usb.decide_action", node_type="vibeflow.node",
    display_name="Decide session action",
    description="Chooses connect, disconnect or no action from presence, ADB state, auto policy and session status.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.process"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.state", "cardinality": "exactly_one", "display_name": "Runtime state"},
            {"type": "usb.device", "cardinality": "exactly_one", "display_name": "USB device"},
            {"type": "usb.adb_state", "cardinality": "exactly_one", "display_name": "ADB transport state"},
            {"type": "usb.session_status", "cardinality": "exactly_one", "display_name": "Session status"},
            {"type": "usb.request", "cardinality": "exactly_one", "display_name": "Pending request"},
        ],
        "provides": [{"key": "action", "type": "usb.action", "display_name": "Session action"}],
        "params_schema": {},
        "params_defaults": {},
        "input_semantics": {
            "usb.settings": ["Configured tablet identity."],
            "usb.state": ["Persisted state carrying the auto policy."],
            "usb.device": ["USB presence resolved from sysfs."],
            "usb.adb_state": ["ADB transport state."],
            "usb.session_status": ["Current Sunshine/Moonlight session state."],
            "usb.request": ["Action requested from the command line interface."],
        },
        "output_semantics": {"action": ["connect, disconnect or none with a reason."]},
    },
)
class DecideAction:
    def run_pure(self, inputs, params):
        settings = _value(inputs, "usb.settings")
        state = _value(inputs, "usb.state")
        device = _value(inputs, "usb.device")
        adb = _value(inputs, "usb.adb_state")
        current = _value(inputs, "usb.session_status")
        request = _value(inputs, "usb.request")
        auto = bool(state.get("auto_enabled", True))
        action = str(request.get("action", "none"))
        if action == "set-auto":
            enabled = bool(request.get("value"))
            return {"action": {"action": "policy", "auto_enabled": enabled,
                               "reason": "automatic session " + ("enabled" if enabled else "disabled")}}
        if action == "disable":
            return {"action": {"action": "disconnect", "auto_enabled": False,
                               "reason": "requested disable"}}
        if action == "enable":
            return {"action": {"action": "connect", "auto_enabled": True,
                               "reason": "requested enable"}} if usable else \
                   {"action": {"action": "none", "reason": "requested enable but tablet unavailable"}}
        if action == "reconnect" and current.get("connected"):
            return {"action": {"action": "disconnect", "auto_enabled": True,
                               "reason": "requested reconnect"}}
        usable = bool(device.get("present")) and adb.get("state") == "device"
        if usable and auto and not current.get("connected"):
            return {"action": {"action": "connect", "reason": "tablet present and stream idle"}}
        if not usable and str(state.get("last_action") or "") == "connect":
            return {"action": {"action": "disconnect", "reason": "tablet removed or adb unavailable"}}
        if current.get("connected") and not auto:
            return {"action": {"action": "disconnect", "reason": "automatic session disabled"}}
        return {"action": {"action": "none", "reason": "no change"}}
