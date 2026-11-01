"""Read, mutate and publish the daemon runtime state document."""
from __future__ import annotations

import json
import os
from pathlib import Path

from vibeflow.targets.python.sdk import node

DEFAULT_STATE_PATH = "/tmp/usb-tablet-display/state.json"
DEFAULT_SHUTDOWN_PATH = "/tmp/usb-tablet-display/shutdown"


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


@node(
    id="usb.tick_step", node_type="vibeflow.node",
    display_name="Daemon tick", description="Advance one daemon tick: wait, update and publish state.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [],
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
        "input_semantics": {},
        "output_semantics": {"stop": ["True when the daemon should leave its loop."]},
    },
)
class TickStep:
    def run_pure(self, inputs, params):
        import time

        state_path = Path(params["state_path"])
        shutdown_path = Path(params["shutdown_path"])
        time.sleep(max(int(params["tick_ms"]), 1) / 1000.0)
        state = _read_json(state_path, {"ticks": 0, "updated_at": None})
        state["ticks"] = int(state.get("ticks") or 0) + 1
        state["updated_at"] = time.time()
        _write_json(state_path, state)
        stop = shutdown_path.exists()
        limit = int(params["max_ticks"] or 0)
        if limit and state["ticks"] >= limit:
            stop = True
        return {"stop": bool(stop)}
