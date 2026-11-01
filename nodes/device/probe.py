"""Locate the configured tablet on the USB bus through sysfs."""
from __future__ import annotations

from pathlib import Path

from vibeflow.targets.python.sdk import node

USB_DEVICES_PATH = "/sys/bus/usb/devices"
NET_CLASS_PATH = "/sys/class/net"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _net_interface(sys_path: str) -> str:
    for entry in Path(NET_CLASS_PATH).iterdir():
        try:
            device = (entry / "device").resolve()
        except OSError:
            continue
        if str(device).startswith(sys_path + "/"):
            return entry.name
    return ""


@node(
    id="usb.probe_device", node_type="vibeflow.node",
    display_name="查找平板",
    description="在电脑的 USB 设备里查找这台平板，判断是否已经插上，并找到它对应的网络接口。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [{"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"}],
        "provides": [{"key": "device", "type": "usb.device", "display_name": "USB device"}],
        "params_schema": {},
        "params_defaults": {},
        "input_semantics": {"usb.settings": ["Configuration carrying the target USB serial."]},
        "output_semantics": {"device": ["Presence, sysfs identity and RNDIS interface of the tablet."]},
    },
)
class ProbeDevice:
    def run_pure(self, inputs, params):
        serial = str(inputs["usb.settings"]["value"]["serial"])
        for entry in sorted(Path(USB_DEVICES_PATH).glob("*")):
            if _read(entry / "serial") != serial:
                continue
            sys_path = str(entry.resolve())
            return {"device": {
                "present": True,
                "serial": serial,
                "sys_path": sys_path,
                "devnum": _read(entry / "devnum"),
                "interface": _net_interface(sys_path),
            }}
        return {"device": {"present": False, "serial": serial, "sys_path": "", "devnum": "", "interface": ""}}
