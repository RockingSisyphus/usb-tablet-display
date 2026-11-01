"""Track the background session job started by the daemon."""
from __future__ import annotations

import json
import time
from pathlib import Path

from vibeflow.targets.python.sdk import node

JOB_PATH = "/tmp/usb-tablet-display/job.json"
EXIT_PATH = "/tmp/usb-tablet-display/job.exit"
LOG_PATH = "/tmp/usb-tablet-display/job.log"


def job_state():
    job = Path(JOB_PATH)
    if not job.is_file():
        return {"action": "none", "code": None, "running": False, "detail": ""}
    try:
        data = json.loads(job.read_text(encoding="utf-8"))
        pid = int(data.get("pid") or 0)
    except (OSError, ValueError):
        return {"action": "none", "code": None, "running": False, "detail": ""}
    alive = pid > 0 and Path(f"/proc/{pid}").exists()
    if alive:
        return {"action": str(data.get("action", "none")), "code": None,
                "running": True, "detail": ""}
    code = None
    for _attempt in range(12):
        try:
            code = int(Path(EXIT_PATH).read_text(encoding="utf-8").strip())
            break
        except (OSError, ValueError):
            code = None
            time.sleep(0.25)
    if code is None:
        return {"action": str(data.get("action", "none")), "code": None,
                "running": True, "detail": ""}
    detail = ""
    try:
        detail = Path(LOG_PATH).read_text(encoding="utf-8", errors="replace")[-300:]
    except OSError:
        pass
    for path in (JOB_PATH, EXIT_PATH):
        Path(path).unlink(missing_ok=True)
    return {"action": str(data.get("action", "none")), "code": code,
            "running": False, "detail": detail}


@node(
    id="usb.collect_job", node_type="vibeflow.node",
    display_name="Collect background job",
    description="Reports whether the background session job is running and its exit code once finished.",
    version="0.1.0", flow_kind="process",
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
