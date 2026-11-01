"""Wait until the RNDIS interface has an IPv4 address."""
from __future__ import annotations

import subprocess
import time

from vibeflow.targets.python.sdk import node

from usb_tablet_display.nodes.stream import session


@node(
    id="usb.wait_usb_address", node_type="vibeflow.node",
    display_name="等待网络地址",
    description="平板插上后，等它从电脑分配到 USB 网络地址；长时间等不到就明确报错。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    implementation_files=["session.py"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.device", "cardinality": "exactly_one", "display_name": "USB device"},
        ],
        "provides": [{"key": "usb_address", "type": "usb.usb_address", "display_name": "USB host address"}],
        "params_schema": {"timeout_ms": {"type": "integer"}},
        "params_defaults": {"timeout_ms": 30000},
        "input_semantics": {
            "usb.settings": ["Configured tablet identity and NetworkManager profile."],
            "usb.device": ["Interface that carries the RNDIS address."],
        },
        "output_semantics": {"usb_address": ["Assigned IPv4 host address or an empty string on timeout."]},
    },
)
class WaitUsbAddress:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        device = inputs["usb.device"]["value"]
        interface = device.get("interface", "")
        deadline = time.monotonic() + max(int(params["timeout_ms"]), 1000) / 1000.0
        address = session.usb_address(interface)
        while not address and time.monotonic() < deadline:
            try:
                subprocess.run(["nmcli", "--wait", "5", "connection", "up", settings["connection"],
                                "ifname", interface], capture_output=True, text=True, timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                pass
            time.sleep(0.5)
            address = session.usb_address(interface)
        if not address:
            raise RuntimeError("Waiting for RNDIS IPv4 address")
        return {"usb_address": {"address": address, "interface": interface}}
