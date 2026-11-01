"""Structural terminal nodes for the three workflows."""
from __future__ import annotations

from vibeflow.targets.python.sdk import node


@node(
    id="usb.start", node_type="vibeflow.node",
    display_name="开始", description="表示这个流程从这里开始，本身不做任何事。",
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
    display_name="结束", description="表示这个流程到此结束，本身不做任何事。",
    version="0.1.0", flow_kind="terminal",
    rulesets=["vibeflow.process"],
    contract={"requires": [], "provides": [], "params_schema": {},
              "params_defaults": {}, "input_semantics": {}, "output_semantics": {}},
)
class EndNode:
    def run_pure(self, inputs, params):
        return {}
