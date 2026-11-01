"""Consume one pending CLI request from the spool directory."""
from __future__ import annotations

import json
from pathlib import Path

from vibeflow.targets.python.sdk import node

REQUESTS_PATH = "/tmp/usb-tablet-display/requests"


@node(
    id="usb.take_request", node_type="vibeflow.node",
    display_name="处理用户命令",
    description="检查用户在电脑上执行过什么命令（例如开关副屏），每次只取一条来处理。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [],
        "provides": [{"key": "request", "type": "usb.request", "display_name": "Pending request"}],
        "params_schema": {"requests_path": {"type": "string"}},
        "params_defaults": {"requests_path": REQUESTS_PATH},
        "input_semantics": {},
        "output_semantics": {"request": ["Claimed action and value, or none when the queue is empty."]},
    },
)
class TakeRequest:
    def run_pure(self, inputs, params):
        directory = Path(params["requests_path"])
        if not directory.is_dir():
            return {"request": {"action": "none", "value": None}}
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                path.unlink(missing_ok=True)
                continue
            path.unlink(missing_ok=True)
            return {"request": {"action": str(payload.get("action", "none")),
                                "value": payload.get("value")}}
        return {"request": {"action": "none", "value": None}}
