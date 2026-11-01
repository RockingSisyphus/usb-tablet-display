"""Report the ADB transport state for the configured tablet."""
from __future__ import annotations

import subprocess

from vibeflow.targets.python.sdk import node


@node(
    id="usb.adb_state", node_type="vibeflow.node",
    display_name="ADB transport state",
    description="Queries adb get-state for the configured serial and classifies the transport.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [{"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"}],
        "provides": [{"key": "adb_state", "type": "usb.adb_state", "display_name": "ADB transport state"}],
        "params_schema": {"timeout_ms": {"type": "integer"}},
        "params_defaults": {"timeout_ms": 5000},
        "input_semantics": {"usb.settings": ["Configuration carrying the ADB binary and serial."]},
        "output_semantics": {"adb_state": ["Normalized ADB transport state and detail text."]},
    },
)
class AdbState:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        argv = [settings["adb"], "-s", settings["serial"], "get-state"]
        try:
            done = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=max(int(params["timeout_ms"]), 1) / 1000.0)
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"adb_state": {"state": "unavailable", "detail": str(error)}}
        out = (done.stdout or "").strip()
        err = (done.stderr or "").strip()
        if "unauthorized" in err.lower():
            return {"adb_state": {"state": "unauthorized", "detail": err[:200]}}
        if out == "device":
            return {"adb_state": {"state": "device", "detail": ""}}
        state = "offline" if "offline" in err.lower() else "unavailable"
        return {"adb_state": {"state": state, "detail": (err or out)[:200]}}
