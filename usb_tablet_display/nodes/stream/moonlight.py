"""Bring up a Moonlight session on the tablet over the USB network."""
from __future__ import annotations

import json
import subprocess
import time
import xml.etree.ElementTree as ET

from vibeflow.targets.python.sdk import node

from usb_tablet_display.nodes.stream import session
from usb_tablet_display.nodes.stream.moonlight_ui import field, fresh_snapshot, stream_surface

UI_PATH = "/data/local/tmp/tablet-display-ui.xml"
PCVIEW = ".PcView"
TRAMPOLINE = ".ShortcutTrampoline"


def _adb(settings, args, timeout=10):
    try:
        return subprocess.run([settings["adb"], "-s", settings["serial"], "shell", *args],
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _host_address(interface):
    if not interface:
        return ""
    try:
        done = subprocess.run(["ip", "-j", "-4", "addr", "show", "dev", interface],
                              capture_output=True, text=True, timeout=5)
        rows = json.loads(done.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return ""
    for row in rows:
        for addr in row.get("addr_info", []):
            if addr.get("scope") == "global":
                return str(addr.get("local", ""))
    return ""


def _dump_ui(settings, shared_snapshot):
    if shared_snapshot:
        result = _adb(settings, ["stat", "-c", "%Y", shared_snapshot, "&&", "date", "+%s",
                                 "&&", "cat", shared_snapshot])
        xml = fresh_snapshot(result.stdout) if result and result.returncode == 0 else None
        if xml:
            return xml
    dumped = _adb(settings, ["uiautomator", "dump", UI_PATH])
    if dumped is None:
        return None
    return (_adb(settings, ["cat", UI_PATH]) or subprocess.CompletedProcess([], 1, "", "")).stdout


def _tap(settings, point):
    _adb(settings, ["input", "tap", point[0], point[1]])


def _register_address(settings, address, deadline):
    entered = submitted = opened = False
    while time.monotonic() < deadline:
        if session.connected(settings):
            return True
        xml = _dump_ui(settings, settings.get("shared_ui_snapshot"))
        if not xml:
            time.sleep(0.5)
            continue
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            time.sleep(0.5)
            continue
        if stream_surface(root, settings["moonlight_package"]):
            return True
        edit = field(xml, settings["moonlight_package"], "hostTextView")
        add = field(xml, settings["moonlight_package"], "manuallyAddPc")
        confirm = field(xml, settings["moonlight_package"], "addPcButton")
        if edit and not entered:
            _tap(settings, edit[0])
            if edit[1]:
                _adb(settings, ["input", "keyevent", "123", *(["67"] * len(edit[1]))])
            _adb(settings, ["input", "text", address])
            entered = True
        elif entered and confirm and not submitted:
            _tap(settings, confirm[0])
            submitted = True
        elif add and not opened:
            _tap(settings, add[0])
            opened = True
        time.sleep(0.5)
    return session.connected(settings)


def _server_info(address):
    done = subprocess.run(["curl", "-fsS", "--max-time", "3",
                           f"http://{address}:47989/serverinfo"],
                          capture_output=True, text=True, timeout=5)
    root = ET.fromstring(done.stdout)
    return root.findtext("hostname") or "", root.findtext("uniqueid") or ""


def _launch_shortcut(settings, address):
    hostname, server_id = _server_info(address)
    if hostname != settings["host_name"]:
        raise RuntimeError("Sunshine hostname does not match the configured Moonlight target")
    done = _adb(settings, ["am", "start", "-n", settings["moonlight_package"] + TRAMPOLINE,
                           "--es", "UUID", server_id, "--es", "AppId", str(int(settings["app_id"])),
                           "--es", "AppName", settings["app_name"]], timeout=15)
    return done is not None and done.returncode == 0


def _try_launch(settings, address):
    try:
        return _launch_shortcut(settings, address)
    except (OSError, subprocess.TimeoutExpired, ET.ParseError, RuntimeError, ValueError):
        return False


@node(
    id="usb.moonlight_connect", node_type="vibeflow.node",
    display_name="Start Moonlight session",
    description="Registers the USB host address when needed and launches Moonlight on the tablet.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    implementation_files=["moonlight_ui.py", "session.py"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.device", "cardinality": "exactly_one", "display_name": "USB device"},
            {"type": "usb.stream_state", "cardinality": "exactly_one", "display_name": "Stream state"},
        ],
        "provides": [{"key": "launch_state", "type": "usb.launch_state", "display_name": "Launch state"}],
        "params_schema": {"timeout_ms": {"type": "integer"}},
        "params_defaults": {"timeout_ms": 45000},
        "input_semantics": {
            "usb.settings": ["ADB binary, serial, Moonlight package and configured app."],
            "usb.device": ["Interface used to resolve the current USB host address."],
            "usb.stream_state": ["Sunshine readiness before Moonlight is launched."],
        },
        "output_semantics": {"launch_state": ["Host address, launch attempts and stream connectivity."]},
    },
)
class MoonlightConnect:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        device = inputs["usb.device"]["value"]
        address = _host_address(device.get("interface", ""))
        package = settings["moonlight_package"]
        if not address:
            return {"launch_state": {"connected": False, "address": "", "reason": "no usb address"}}
        _adb(settings, ["am", "force-stop", package])
        _adb(settings, ["am", "start", "-n", package + PCVIEW, "--activity-clear-top"])
        if session.connected(settings):
            return {"launch_state": {"connected": True, "address": address, "stage": "already"}}
        launched = _try_launch(settings, address)
        budget = time.monotonic() + max(int(params["timeout_ms"]), 5000) / 1000.0
        while time.monotonic() < budget and launched and not session.connected(settings):
            time.sleep(1)
        if session.connected(settings):
            return {"launch_state": {"connected": True, "address": address, "stage": "shortcut"}}
        registered = _register_address(settings, address, time.monotonic() + 25)
        launched = _try_launch(settings, address) or launched
        while time.monotonic() < budget and launched and not session.connected(settings):
            time.sleep(1)
        return {"launch_state": {"connected": session.connected(settings), "address": address,
                                 "stage": "registered" if registered else "shortcut",
                                 "launched": launched}}
