"""Track the background session job started by the daemon."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from vibeflow.targets.python.sdk import node

JOB_PATH = "/tmp/usb-tablet-display/job.json"
EXIT_PATH = "/tmp/usb-tablet-display/job.exit"
LOG_PATH = "/tmp/usb-tablet-display/job.log"
TIMEOUT_SECONDS = 600


def _clean():
    for name in (JOB_PATH, EXIT_PATH):
        Path(name).unlink(missing_ok=True)


def job_state():
    job = Path(JOB_PATH)
    if not job.is_file():
        return {"action": "none", "code": None, "running": False, "detail": ""}
    try:
        data = json.loads(job.read_text(encoding="utf-8"))
        pid = int(data.get("pid") or 0)
        started = float(data.get("started_at") or 0)
    except (OSError, ValueError):
        _clean()
        return {"action": "none", "code": None, "running": False, "detail": "invalid job file"}
    action = str(data.get("action", "none"))
    exit_file = Path(EXIT_PATH)
    if exit_file.is_file():
        try:
            code = int(exit_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            code = -1
        detail = ""
        try:
            detail = Path(LOG_PATH).read_text(encoding="utf-8", errors="replace")[-300:]
        except OSError:
            pass
        _clean()
        return {"action": action, "code": code, "running": False, "detail": detail}
    alive = pid > 0 and Path(f"/proc/{pid}").exists()
    if alive and time.time() - started < TIMEOUT_SECONDS:
        return {"action": action, "code": None, "running": True, "detail": ""}
    if alive:
        try:
            subprocess.run(["kill", "-TERM", f"-{pid}"], capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
    _clean()
    return {"action": action, "code": -1, "running": False,
            "detail": "job ended without exit code" if not alive else "job timed out"}


@node(
    id="usb.collect_job", node_type="vibeflow.node",
    display_name="Collect background job",
    description="Reports whether the background session job is running and its exit code once finished.",
    version="0.2.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [],
        "provides": [{"key": "job", "type": "usb.job", "display_name": "Background job"}],
        "params_schema": {},
        "params_defaults": {},
        "input_semantics": {},
        "output_semantics": {"job": ["Action, running flag, exit code and log tail."]},
    },
)
class CollectJob:
    def run_pure(self, inputs, params):
        return {"job": job_state()}
