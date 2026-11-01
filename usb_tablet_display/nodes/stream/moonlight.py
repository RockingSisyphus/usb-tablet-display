"""Bring up a Moonlight session on the tablet over the USB network."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from vibeflow.targets.python.sdk import node

from usb_tablet_display.nodes.stream import session
from usb_tablet_display.nodes.stream.moonlight_ui import (dialog_error, field, fresh_snapshot,
                                                          stream_surface)

UI_PATH = "/data/local/tmp/tablet-display-ui.xml"
PCVIEW = ".PcView"
TRAMPOLINE = ".ShortcutTrampoline"


def _adb(settings, args, timeout=10):
    command = [settings["adb"], "-s", settings["serial"], "shell", *[str(a) for a in args]]
    try:
        return subprocess.run(command,
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _host_address(interface):
    return session.usb_address(interface)


def _dump_ui_once(settings, shared_snapshot):
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


def _dump_ui(settings, shared_snapshot):
    for _attempt in range(3):
        xml = _dump_ui_once(settings, shared_snapshot)
        if xml:
            return xml
        time.sleep(0.4)
    return None


def _foreground(settings, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        xml = _dump_ui(settings, settings.get("shared_ui_snapshot"))
        if xml:
            try:
                root = ET.fromstring(xml)
            except ET.ParseError:
                root = None
            if root is not None:
                packages = {n.get("package") for n in root.iter() if n.get("package")}
                if settings["moonlight_package"] in packages:
                    return True
        time.sleep(0.6)
    return False


def _read_state(path):
    try:
        import json as _json
        return _json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_registered(path, address):
    data = _read_state(path)
    data["registered_address"] = address
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _tap(settings, point):
    _adb(settings, ["input", "tap", point[0], point[1]])


def _list_has_host(settings, host_name):
    xml = _dump_ui(settings, settings.get("shared_ui_snapshot"))
    if not xml:
        return False, None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return False, xml
    texts = " ".join(((n.get("text") or "") + " " + (n.get("content-desc") or "")) for n in root.iter())
    return host_name in texts, xml


def _register_address(settings, address, deadline):
    entered = submitted = opened = False
    package = settings["moonlight_package"]
    while time.monotonic() < deadline:
        if session.connected(settings):
            return True, ""
        xml = _dump_ui(settings, settings.get("shared_ui_snapshot"))
        if not xml:
            time.sleep(0.6)
            continue
        try:
            error = dialog_error(xml, package)
        except ET.ParseError:
            time.sleep(0.6)
            continue
        if error:
            return False, "Moonlight rejected the USB address: " + error
        root = ET.fromstring(xml)
        if stream_surface(root, package):
            return True, ""
        edit = field(xml, package, "hostTextView")
        add = field(xml, package, "manuallyAddPc")
        confirm = field(xml, package, "addPcButton")
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
        elif submitted:
            present, _xml = _list_has_host(settings, settings["host_name"])
            if present:
                return True, ""
        time.sleep(0.6)
    return session.connected(settings), "address registration timed out"


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
    done = _am_start(settings, settings["moonlight_package"], TRAMPOLINE,
                     ("--es", "UUID", server_id, "--es", "AppId", str(int(settings["app_id"])),
                      "--es", "AppName", settings["app_name"]))
    return done is not None and done.returncode == 0


def _am_start(settings, package, activity, extra=()):
    last = None
    for _attempt in range(3):
        done = subprocess.run([settings["adb"], "-s", settings["serial"], "shell", "am", "start",
                               "-n", f"{package}/{activity}", *extra],
                              capture_output=True, text=True, timeout=15)
        last = done
        if done.returncode == 0 and "Error" not in (done.stdout or "") + (done.stderr or ""):
            return done
        time.sleep(0.6)
    return last


def _reachable(settings, address):
    done = _adb(settings, ["/system/bin/curl", "-sS", "--max-time", "4", "-o", "/dev/null",
                           "-w", "%{http_code}", f"http://{address}:47989/serverinfo"], 8)
    return bool(done and done.returncode == 0 and "200" in (done.stdout or ""))


def _try_launch(settings, address):
    try:
        return _launch_shortcut(settings, address)
    except (OSError, subprocess.TimeoutExpired, ET.ParseError, RuntimeError, ValueError):
        return False


def _observe(settings, address):
    ports_ok, detail = session.ports_ready(settings, address)
    return session.connected(settings) and ports_ok, detail


def _sunshine_log():
    try:
        done = subprocess.run(["journalctl", "--user", "-u", "app-dev.lizardbyte.app.Sunshine.service",
                               "--since", "-4 min", "--no-pager"], capture_output=True,
                              text=True, timeout=10)
        return (done.stdout or "")[-8000:]
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _append_trace(trace):
    path = Path("/tmp/usb-tablet-display/moonlight-failure.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data["trace"] = trace
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _save_failure(stage, address, xml, detail):
    path = Path("/tmp/usb-tablet-display/moonlight-failure.json")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"stage": stage, "address": address, "detail": detail,
                                    "ui_file": "/tmp/usb-tablet-display/moonlight-failure.xml"},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        (path.parent / "moonlight-failure.xml").write_text(xml or "", encoding="utf-8")
        (path.parent / "moonlight-failure-sunshine.log").write_text(_sunshine_log(), encoding="utf-8")
    except OSError:
        pass


def _register_address(settings, address, deadline):
    entered = submitted = opened = False
    while time.monotonic() < deadline:
        if session.connected(settings):
            return True, ""
        xml = _dump_ui(settings, settings.get("shared_ui_snapshot"))
        if not xml:
            time.sleep(0.5)
            continue
        try:
            error = dialog_error(xml, settings["moonlight_package"])
        except ET.ParseError:
            time.sleep(0.5)
            continue
        if error:
            return False, "Moonlight rejected the USB address: " + error
        root = ET.fromstring(xml)
        if stream_surface(root, settings["moonlight_package"]):
            return True, ""
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
    return session.connected(settings), "address registration timed out"


@node(
    id="usb.moonlight_connect", node_type="vibeflow.node",
    display_name="让平板开始投屏",
    description="在平板上登记电脑当前的 USB 地址并打开投屏；首次使用或地址变化时会自动完成登记。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    implementation_files=["moonlight_ui.py", "session.py"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.usb_address", "cardinality": "exactly_one", "display_name": "USB host address"},
            {"type": "usb.stream_ready", "cardinality": "exactly_one", "display_name": "Stream readiness"},
            {"type": "usb.state", "cardinality": "exactly_one", "display_name": "Runtime state"},
        ],
        "provides": [{"key": "launch_state", "type": "usb.launch_state", "display_name": "Launch state"}],
        "params_schema": {"register_ms": {"type": "integer"}, "connect_ms": {"type": "integer"},
                          "state_path": {"type": "string"}},
        "params_defaults": {"register_ms": 45000, "connect_ms": 55000,
                            "state_path": "/tmp/usb-tablet-display/state.json"},
        "input_semantics": {
            "usb.settings": ["ADB binary, serial, Moonlight package and configured app."],
            "usb.usb_address": ["Assigned USB host address for registration and launch."],
            "usb.stream_ready": ["Sunshine readiness before Moonlight is launched."],
            "usb.state": ["Persisted state carrying the last registered USB address."],
        },
        "output_semantics": {"launch_state": ["Registered address, stage and stream connectivity."]},
    },
)
class MoonlightConnect:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        trace = []
        address = str(inputs["usb.usb_address"]["value"].get("address", ""))
        state_path = params["state_path"]
        known = str(inputs["usb.state"]["value"].get("registered_address") or "")
        package = settings["moonlight_package"]
        if not address:
            return {"launch_state": {"connected": False, "address": "", "stage": "no-usb-address",
                                     "error": "no usb host address"}}
        ready, detail = _observe(settings, address)
        if ready:
            return {"launch_state": {"connected": True, "address": address, "stage": "already"}}
        if not _reachable(settings, address):
            _save_failure("reachability", address, None, "tablet cannot reach serverinfo over usb")
            return {"launch_state": {"connected": False, "address": address, "stage": "reachability",
                                     "error": "tablet cannot reach http://" + address + ":47989/serverinfo"}}
        fast_deadline = time.monotonic() + 12
        fast_launched = _try_launch(settings, address)
        while time.monotonic() < fast_deadline and fast_launched:
            ready, _detail = _observe(settings, address)
            if ready:
                return {"launch_state": {"connected": True, "address": address,
                                         "stage": "already-registered"}}
            time.sleep(0.5)
        _adb(settings, ["am", "force-stop", package])
        started = _am_start(settings, package, PCVIEW, ("--activity-clear-top",))
        _foreground(settings)
        trace.append({"start_rc": None if started is None else started.returncode,
                      "start_out": "" if started is None else ((started.stdout or "") + (started.stderr or "")).strip()[:200]})
        if known == address:
            registered, error = True, ""
        else:
            registered, error = _register_address(settings, address, time.monotonic() + max(int(params["register_ms"]), 5000) / 1000.0)
        if registered and known != address:
            _write_registered(state_path, address)
        if error:
            _save_failure("register", address, _dump_ui(settings, settings.get("shared_ui_snapshot")), error)
            _append_trace(trace)
            return {"launch_state": {"connected": False, "address": address, "stage": "register",
                                     "error": error}}
        launched = _try_launch(settings, address)
        deadline = time.monotonic() + max(int(params["connect_ms"]), 5000) / 1000.0
        while time.monotonic() < deadline:
            ready, detail = _observe(settings, address)
            if ready:
                return {"launch_state": {"connected": True, "address": address,
                                         "stage": "shortcut", "registered": registered}}
            time.sleep(0.5)
        _save_failure("launch", address, _dump_ui(settings, settings.get("shared_ui_snapshot")), detail)
        return {"launch_state": {"connected": False, "address": address, "stage": "launch",
                                 "registered": registered, "launched": launched, "detail": detail,
                                 "reachable": _reachable(settings, address)}}


@node(
    id="usb.require_stream", node_type="vibeflow.node",
    display_name="要求画面已连上",
    description="如果最终没有连上，就明确报错结束，避免把失败误当成成功。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.process"],
    contract={
        "requires": [
            {"type": "usb.stream_check", "cardinality": "exactly_one", "display_name": "Stream check"},
            {"type": "usb.launch_state", "cardinality": "exactly_one", "display_name": "Launch state"},
        ],
        "provides": [{"key": "required", "type": "usb.required", "display_name": "Required outcome"}],
        "params_schema": {},
        "params_defaults": {},
        "input_semantics": {
            "usb.stream_check": ["Final Sunshine/Moonlight observation."],
            "usb.launch_state": ["Address, stage and any registration error."],
        },
        "output_semantics": {"required": ["Confirmation that the stream is connected."]},
    },
)
class RequireStream:
    def run_pure(self, inputs, params):
        check = inputs["usb.stream_check"]["value"]
        launch = inputs["usb.launch_state"]["value"]
        if check.get("connected"):
            return {"required": {"stream_connected": True}}
        stage = launch.get("stage", "unknown")
        error = launch.get("error", "")
        raise RuntimeError(f"stream not established (stage={stage}, server={check.get('server_connected')}, "
                           f"client={check.get('client_connected')}, address={launch.get('address', '')}"
                           + (f", error={error}" if error else "") + ")")
