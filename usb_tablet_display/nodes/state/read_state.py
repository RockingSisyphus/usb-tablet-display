"""Read the daemon runtime state document without mutating it."""
from __future__ import annotations

import json
from pathlib import Path

from vibeflow.targets.python.sdk import node

DEFAULT_STATE_PATH = "/tmp/usb-tablet-display/state.json"


@node(
    id="usb.read_state", node_type="vibeflow.node",
    display_name="Read state",
    description="Loads the runtime state document; a missing or invalid file yields a baseline state.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [],
        "provides": [{"key": "loaded_state", "type": "usb.state", "display_name": "Runtime state"}],
        "params_schema": {"state_path": {"type": "string"}},
        "params_defaults": {"state_path": DEFAULT_STATE_PATH},
        "input_semantics": {},
        "output_semantics": {"loaded_state": ["Current runtime state or a baseline when absent."]},
    },
)
class ReadState:
    def run_pure(self, inputs, params):
        path = Path(params["state_path"])
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {"ticks": 0}
        if not isinstance(state, dict):
            state = {"ticks": 0}
        return {"loaded_state": state}
