"""Report whether the tablet is currently showing the PC screen."""
from __future__ import annotations

from vibeflow.targets.python.sdk import node

from usb_tablet_display.nodes.stream import session


def _value(inputs, key):
    return inputs[key]["value"]

@node(
    id="usb.session_status", node_type="vibeflow.node",
    display_name="检查是否正在投屏",
    description="综合串流程序、投屏程序与端口状态，判断平板现在是否真的在显示电脑画面。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    implementation_files=["session.py"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.device", "cardinality": "exactly_one", "display_name": "USB device"},
        ],
        "provides": [{"key": "session_status", "type": "usb.session_status", "display_name": "Session status"}],
        "params_schema": {},
        "params_defaults": {},
        "input_semantics": {
            "usb.settings": ["Sunshine unit, ADB serial and Moonlight package."],
            "usb.device": ["Interface used to resolve the current USB address."],
        },
        "output_semantics": {"session_status": ["Whether a client and the Moonlight game are both active."]},
    },
)
class SessionStatus:
    def run_pure(self, inputs, params):
        settings = _value(inputs, "usb.settings")
        address = session.usb_address(_value(inputs, "usb.device").get("interface", ""))
        return {"session_status": {"connected": session.connected(settings, address)}}
