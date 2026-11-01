"""Run one prepared workflow as the daemon's session action."""
from __future__ import annotations

import subprocess

from vibeflow.targets.python.sdk import node

ROOT = "/home/rockingsisyphus/projects/体验优化小项目/平板usb副屏"
def _configs():
    return {"connect": "connect.jsonc", "disconnect": "disconnect.jsonc"}


@node(
    id="usb.auto_session", node_type="vibeflow.node",
    display_name="Run session action",
    description="Invokes the verified connect or disconnect workflow for the decided action.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [
            {"type": "usb.action", "cardinality": "exactly_one", "display_name": "Session action"},
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
        ],
        "provides": [{"key": "action_result", "type": "usb.action_result", "display_name": "Action result"}],
        "params_schema": {"timeout_ms": {"type": "integer"}},
        "params_defaults": {"timeout_ms": 240000},
        "input_semantics": {
            "usb.action": ["connect, disconnect or none."],
            "usb.settings": ["Configuration path used by the invoked workflow."],
        },
        "output_semantics": {"action_result": ["Action taken, exit code and a short diagnostic tail."]},
    },
)
class AutoSession:
    def run_pure(self, inputs, params):
        action = inputs["usb.action"]["value"].get("action", "none")
        configs = _configs()
        if action not in configs:
            return {"action_result": {"action": "none", "code": 0, "detail": "",
                                      "auto_enabled": inputs["usb.action"]["value"].get("auto_enabled")}}
        config = f"usb_tablet_display/configs/{configs[action]}"
        try:
            done = subprocess.run(
                ["python3", "run.py", "run", "--config", config,
                 "--input", "usb_tablet_display/probes/daemon.json"],
                cwd=ROOT, capture_output=True, text=True,
                timeout=max(int(params["timeout_ms"]), 5000) / 1000.0)
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"action_result": {"action": action, "code": None, "detail": str(error)[:300]}}
        tail = ((done.stderr or "") + (done.stdout or "")).strip()[-400:]
        return {"action_result": {"action": action, "code": done.returncode, "detail": tail,
                                  "auto_enabled": inputs["usb.action"]["value"].get("auto_enabled")}}
