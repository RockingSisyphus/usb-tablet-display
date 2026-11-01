"""Decide the session action for one tick."""
from __future__ import annotations

from vibeflow.targets.python.sdk import node


def _value(inputs, key):
    return inputs[key]["value"]


@node(
    id="usb.decide_action", node_type="vibeflow.node",
    display_name="决定要做什么",
    description="根据平板是否插着、调试连接是否可用、是否开启自动模式以及当前投屏状态，决定连接、断开还是什么都不做。",
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
            {"type": "usb.session_result", "cardinality": "exactly_one", "display_name": "Session result"},
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
            "usb.session_result": ["Whether a background session is still running."],
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
        session = _value(inputs, "usb.session_result")
        auto = bool(state.get("auto_enabled", True))
        usable = bool(device.get("present")) and adb.get("state") == "device"
        if session.get("running"):
            return {"action": {"action": "none", "auto_enabled": auto,
                               "reason": "session job running"}}
        action = str(request.get("action", "none"))
        if action == "set-auto":
            enabled = bool(request.get("value"))
            return {"action": {"action": "policy", "auto_enabled": enabled,
                               "reason": "automatic session " + ("enabled" if enabled else "disabled")}}
        if action == "disable":
            return {"action": {"action": "disconnect", "auto_enabled": False,
                               "reason": "requested disable"}}
        if action == "enable":
            if usable:
                return {"action": {"action": "connect", "auto_enabled": True,
                                   "reason": "requested enable"}}
            return {"action": {"action": "none", "auto_enabled": True,
                               "reason": "requested enable but tablet unavailable"}}
        if action == "reconnect" and current.get("connected"):
            return {"action": {"action": "disconnect", "auto_enabled": True,
                               "reason": "requested reconnect"}}
        if usable and auto and not current.get("connected"):
            return {"action": {"action": "connect", "auto_enabled": auto,
                               "reason": "tablet present and stream idle"}}
        if not usable and str(state.get("last_action") or "") == "connect":
            return {"action": {"action": "disconnect", "auto_enabled": auto,
                               "reason": "tablet removed or adb unavailable"}}
        if current.get("connected") and not auto:
            return {"action": {"action": "disconnect", "auto_enabled": False,
                               "reason": "automatic session disabled"}}
        return {"action": {"action": "none", "auto_enabled": auto, "reason": "no change"}}
