"""Run one external command and return a structured result."""
from __future__ import annotations

import subprocess

from vibeflow.targets.python.sdk import node


@node(
    id="usb.run_command", node_type="vibeflow.node",
    display_name="Run command",
    description="Runs one external command with a bounded timeout and returns its exit status and output.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [],
        "provides": [{"key": "command_result", "type": "usb.command_result", "display_name": "Command result"}],
        "params_schema": {
            "argv": {"type": "array", "items": {"type": "string"}},
            "timeout_ms": {"type": "integer"},
        },
        "params_defaults": {"argv": [], "timeout_ms": 10000},
        "input_semantics": {},
        "output_semantics": {"command_result": ["Exit code, stdout and stderr of the executed command."]},
    },
)
class RunCommand:
    def run_pure(self, inputs, params):
        argv = list(params["argv"])
        timeout_s = max(int(params["timeout_ms"]), 1) / 1000.0
        if not argv:
            return {"command_result": {"argv": [], "returncode": None, "stdout": "", "stderr": "no argv"}}
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
            return {"command_result": {"argv": argv, "returncode": done.returncode,
                                       "stdout": done.stdout, "stderr": done.stderr}}
        except subprocess.TimeoutExpired:
            return {"command_result": {"argv": argv, "returncode": None, "stdout": "", "stderr": "timeout"}}
        except OSError as error:
            return {"command_result": {"argv": argv, "returncode": None, "stdout": "", "stderr": str(error)}}
