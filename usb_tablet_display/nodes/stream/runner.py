"""Start the verified session workflow as a background job."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from vibeflow.targets.python.sdk import node

from usb_tablet_display.nodes.stream import jobs

ROOT = "/home/rockingsisyphus/projects/体验优化小项目/平板usb副屏"


def _configs():
    return {"connect": "connect.jsonc", "disconnect": "disconnect.jsonc"}


@node(
    id="usb.auto_session", node_type="vibeflow.node",
    display_name="Run session action",
    description="Starts the verified connect or disconnect workflow in the background so the loop keeps ticking.",
    version="0.2.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    implementation_files=["jobs.py"],
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
            "usb.settings": ["Configuration used by the started workflow."],
        },
        "output_semantics": {"action_result": ["Whether a job was started, was already running or was skipped."]},
    },
)
class AutoSession:
    def run_pure(self, inputs, params):
        action = inputs["usb.action"]["value"].get("action", "none")
        auto = inputs["usb.action"]["value"].get("auto_enabled")
        configs = _configs()
        if action not in configs:
            return {"action_result": {"action": "none", "code": 0, "detail": "", "auto_enabled": auto}}
        current = jobs.job_state()
        if current.get("running"):
            return {"action_result": {"action": "busy", "code": None, "detail": "",
                                      "auto_enabled": auto}}
        config = f"usb_tablet_display/configs/{configs[action]}"
        Path(jobs.JOB_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(jobs.EXIT_PATH).unlink(missing_ok=True)
        command = (f'cd "{ROOT}" && python3 run.py run --config {config} '
                   f'--input usb_tablet_display/probes/daemon.json '
                   f'> {jobs.LOG_PATH} 2>&1; code=$?; '
                   f'printf "%s" "$code" > {jobs.EXIT_PATH}.tmp; mv {jobs.EXIT_PATH}.tmp {jobs.EXIT_PATH}')
        process = subprocess.Popen(["/bin/sh", "-c", command], start_new_session=True,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        Path(jobs.JOB_PATH).write_text(
            json.dumps({"action": action, "pid": process.pid, "started_at": time.time()}),
            encoding="utf-8")
        return {"action_result": {"action": action, "code": None, "started": True,
                                  "pid": process.pid, "auto_enabled": auto}}
