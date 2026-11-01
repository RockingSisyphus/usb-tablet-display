"""Advance one daemon tick and publish the merged runtime state."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from vibeflow.targets.python.sdk import node

DEFAULT_STATE_PATH = "/tmp/usb-tablet-display/state.json"
DEFAULT_SHUTDOWN_PATH = "/tmp/usb-tablet-display/shutdown"


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


@node(
    id="usb.tick_merge", node_type="vibeflow.node",
    display_name="Advance tick",
    description="Waits one tick interval, merges probe results into the runtime state and publishes it.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [
            {"type": "usb.state", "cardinality": "exactly_one", "display_name": "Runtime state"},
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.device", "cardinality": "exactly_one", "display_name": "USB device"},
            {"type": "usb.adb_state", "cardinality": "exactly_one", "display_name": "ADB transport state"},
        ],
        "provides": [{"key": "stop", "type": "usb.shutdown", "display_name": "Stop flag"}],
        "params_schema": {
            "state_path": {"type": "string"},
            "shutdown_path": {"type": "string"},
            "tick_ms": {"type": "integer"},
            "max_ticks": {"type": "integer"},
        },
        "params_defaults": {
            "state_path": DEFAULT_STATE_PATH,
            "shutdown_path": DEFAULT_SHUTDOWN_PATH,
            "tick_ms": 200,
            "max_ticks": 0,
        },
        "input_semantics": {
            "usb.state": ["State carried from the previous iteration."],
            "usb.settings": ["Configuration for the current run."],
            "usb.device": ["USB presence and RNDIS interface from this iteration."],
            "usb.adb_state": ["ADB transport state from this iteration."],
        },
        "output_semantics": {"stop": ["True when the daemon should leave its loop."]},
    },
)
class TickMerge:
    def run_pure(self, inputs, params):
        state = dict(inputs["usb.state"]["value"])
        device = inputs["usb.device"]["value"]
        adb = inputs["usb.adb_state"]["value"]
        settings = inputs["usb.settings"]["value"]
        time.sleep(max(int(params["tick_ms"]), 1) / 1000.0)
        state.update({
            "ticks": int(state.get("ticks") or 0) + 1,
            "updated_at": time.time(),
            "serial": settings["serial"],
            "device_present": bool(device.get("present")),
            "usb_interface": device.get("interface", ""),
            "adb": adb.get("state", "unavailable"),
            "adb_detail": adb.get("detail", ""),
        })
        _write_json(Path(params["state_path"]), state)
        limit = int(params["max_ticks"] or 0)
        stop = Path(params["shutdown_path"]).exists() or (limit > 0 and state["ticks"] >= limit)
        return {"stop": bool(stop)}
