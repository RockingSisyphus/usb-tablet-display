"""Structural terminal nodes for the three workflows."""
from __future__ import annotations

from vibeflow.targets.python.sdk import node


@node(
    id="usb.start", node_type="vibeflow.node",
    display_name="Start", description="Marks the structural start of a USB display workflow.",
    version="0.1.0", flow_kind="terminal",
    rulesets=["vibeflow.process"],
    contract={"requires": [], "provides": [], "params_schema": {},
              "params_defaults": {}, "input_semantics": {}, "output_semantics": {}},
)
class StartNode:
    def run_pure(self, inputs, params):
        return {}


@node(
    id="usb.end", node_type="vibeflow.node",
    display_name="End", description="Marks the structural end of a USB display workflow.",
    version="0.1.0", flow_kind="terminal",
    rulesets=["vibeflow.process"],
    contract={"requires": [], "provides": [], "params_schema": {},
              "params_defaults": {}, "input_semantics": {}, "output_semantics": {}},
)
class EndNode:
    def run_pure(self, inputs, params):
        return {}
