"""Run one install action requested from the command line."""
from __future__ import annotations

import json
from pathlib import Path

from vibeflow.targets.python.sdk import node

from usb_tablet_display.nodes.install import ops

REQUEST_PATH = "/tmp/usb-tablet-display/install-request.json"
RESULT_PATH = "/tmp/usb-tablet-display/install-result.json"


def _request():
    try:
        return json.loads(Path(REQUEST_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"action": "verify", "backup_dir": ""}


@node(
    id="usb.install_run", node_type="vibeflow.node",
    display_name="Run install action",
    description="Runs the requested backup, quiesce, install, restore or verify action for this stack.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    implementation_files=["ops.py"],
    contract={
        "requires": [],
        "provides": [{"key": "install_result", "type": "usb.install_result", "display_name": "Install result"}],
        "params_schema": {"request_path": {"type": "string"}, "result_path": {"type": "string"}},
        "params_defaults": {"request_path": REQUEST_PATH, "result_path": RESULT_PATH},
        "input_semantics": {},
        "output_semantics": {"install_result": ["Action outcome, paths and verification checks."]},
    },
)
class InstallRun:
    def run_pure(self, inputs, params):
        request = _request()
        action = str(request.get("action", "verify"))
        home = Path.home()
        backup_dir = str(request.get("backup_dir") or "")
        if action == "backup":
            result = ops.backup(home)
        elif action == "quiesce":
            result = ops.quiesce(home)
        elif action == "install":
            result = ops.install(home)
        elif action == "restore":
            if not backup_dir:
                result = {"action": "restore", "error": "backup_dir required"}
            else:
                result = ops.restore(home, Path(backup_dir))
        else:
            result = ops.verify(home)
        Path(params["result_path"]).parent.mkdir(parents=True, exist_ok=True)
        Path(params["result_path"]).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
        Path(REQUEST_PATH).unlink(missing_ok=True)
        return {"install_result": result}
