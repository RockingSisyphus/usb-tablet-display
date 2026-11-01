"""Start and stop the Sunshine screen-cast service."""
from __future__ import annotations

import subprocess
import time

from vibeflow.targets.python.sdk import node


def _systemctl(action: str, unit: str, timeout_s: float) -> dict:
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
        result = _systemctl("stop", unit, max(int(params["timeout_ms"]), 1) / 1000.0)
        for _ in range(20):
            if not _active(unit):
                return {"stream_state": {"unit": unit, "state": "stopped",
                                         "ok": True, "detail": result["detail"]}}
            time.sleep(0.1)
        return {"stream_state": {"unit": unit, "state": "active",
                                 "ok": False, "detail": result["detail"]}}


@node(
    id="usb.sunshine_start", node_type="vibeflow.node",
    display_name="Start Sunshine stream",
    description="Starts the Sunshine unit after the virtual output exists again.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [{"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"}],
        "provides": [{"key": "stream_state", "type": "usb.stream_state", "display_name": "Stream state"}],
        "params_schema": {"timeout_ms": {"type": "integer"}},
        "params_defaults": {"timeout_ms": 8000},
        "input_semantics": {"usb.settings": ["Configuration carrying the Sunshine unit name."]},
        "output_semantics": {"stream_state": ["Whether the Sunshine unit is now active."]},
    },
)
class SunshineStart:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        unit = settings["sunshine_unit"]
        result = _systemctl("start", unit, max(int(params["timeout_ms"]), 1) / 1000.0)
        for _ in range(30):
            if _active(unit):
                return {"stream_state": {"unit": unit, "state": "active",
                                         "ok": True, "detail": result["detail"]}}
            time.sleep(0.1)
        return {"stream_state": {"unit": unit, "state": "inactive",
                                 "ok": False, "detail": result["detail"]}}
