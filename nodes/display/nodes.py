"""GNOME monitor layout nodes backed by Mutter's DisplayConfig interface."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from gi.repository import Gio, GLib

from vibeflow.targets.python.sdk import node

from . import layout


def _bus() -> Gio.DBusConnection:
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    if connection is None:
        raise layout.ConfigError("session bus is unavailable")
    return connection


def _state(connection: Gio.DBusConnection) -> tuple:
    reply = connection.call_sync(layout.BUS_NAME, layout.OBJECT_PATH, layout.INTERFACE,
                                "GetCurrentState", None, None, Gio.DBusCallFlags.NONE, 5000, None)
    return reply.unpack()


EXTENSION_UUID = "android-tablet-auto-keep-display@rockingsisyphus.local"
MARKER_SUFFIX = (".cache", "usb-tablet-display", "auto-accept-display-change")


def _marker_path() -> Path:
    return Path.home().joinpath(*MARKER_SUFFIX)


def _extension_active(uuid: str) -> bool:
    try:
        done = subprocess.run(
            ["gdbus", "call", "--session", "--dest", "org.gnome.Shell.Extensions",
             "--object-path", "/org/gnome/Shell/Extensions", "--method",
             "org.gnome.Shell.Extensions.GetExtensionInfo", uuid],
            capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if done.returncode != 0:
        return False
    try:
        info = GLib.Variant.parse(None, done.stdout, None, None).unpack()[0]
    except Exception:
        return False
    return info.get("state") == 1


def _await_confirmation(target: str, settings: dict, timeout_ms: int) -> bool:
    """等待系统确认：布局到位后再留一段宽限，交给扩展点击"保留更改"。"""
    deadline = time.monotonic() + max(timeout_ms, 0) / 1000.0
    matched_at = None
    while time.monotonic() < deadline:
        state = _state(_bus())
        matches = layout.config_matches(state, target, settings["connector"],
                                        settings["virtual_mode"], settings["builtin_mode"], settings["scale"])
        if matches and matched_at is None:
            matched_at = time.monotonic()
        if matches and not _marker_path().exists():
            return True
        if matched_at is not None and time.monotonic() - matched_at >= 1.5 and not _marker_path().exists():
            return True
        if not matches and not _marker_path().exists():
            return layout.config_matches(state, target, settings["connector"],
                                         settings["virtual_mode"], settings["builtin_mode"],
                                         settings["scale"])
        time.sleep(0.2)
    return layout.config_matches(_state(_bus()), target, settings["connector"],
                                 settings["virtual_mode"], settings["builtin_mode"], settings["scale"])


def _rebuild_previous(state: tuple, previous: list) -> list:
    """把 GetCurrentState 的逻辑显示器改写成 ApplyMonitorsConfig 需要的形状。"""
    modes = {spec[0]: spec for spec in state[1]}
    config = []
    for logical in previous:
        monitors = []
        for monitor in logical[5]:
            connector = monitor[0]
            record = modes.get(connector)
            mode_id = layout.selected_mode_id(record) if record else ""
            monitors.append((connector, mode_id, {}))
        config.append((logical[0], logical[1], logical[2], logical[3], logical[4], monitors))
    return config


def _service_active(unit: str) -> bool:
    try:
        done = subprocess.run(["systemctl", "--user", "is-active", unit],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.stdout.strip() == "active"


def _apply(connection: Gio.DBusConnection, state: tuple, config: list, method: int, layout_mode: int) -> None:
    parameters = GLib.Variant(layout.APPLY_SIGNATURE,
                              (state[0], method, config, {"layout-mode": GLib.Variant("u", layout_mode)}))
    connection.call_sync(layout.BUS_NAME, layout.OBJECT_PATH, layout.INTERFACE, "ApplyMonitorsConfig",
                         parameters, None, Gio.DBusCallFlags.NONE, 10000, None)


@node(
    id="usb.display_matches", node_type="vibeflow.node",
    display_name="检查副屏是否已就位",
    description="把当前屏幕布局和期望的副屏状态做比较，判断还需要不需要调整。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    implementation_files=["layout.py"],
    contract={
        "requires": [{"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"}],
        "provides": [{"key": "display_check", "type": "usb.display_check", "display_name": "Display match result"}],
        "params_schema": {"target": {"type": "string"}},
        "params_defaults": {"target": "enable"},
        "input_semantics": {"usb.settings": ["Connector, modes and scale to compare against."]},
        "output_semantics": {"display_check": ["Whether the current layout already matches the target."]},
    },
)
class DisplayMatches:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        state = _state(_bus())
        matches = layout.config_matches(state, params["target"], settings["connector"],
                                        settings["virtual_mode"], settings["builtin_mode"], settings["scale"])
        return {"display_check": {"target": params["target"], "matches": bool(matches)}}


@node(
    id="usb.display_apply", node_type="vibeflow.node",
    display_name="调整副屏",
    description="需要时把屏幕布局调整为打开或关闭副屏，并自动确认系统的变更提示；如果结果不对会自动恢复原状。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    implementation_files=["layout.py"],
    contract={
        "requires": [{"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"}],
        "provides": [{"key": "display_result", "type": "usb.display_result", "display_name": "Display result"}],
        "params_schema": {"target": {"type": "string"}, "method": {"type": "integer"},
                          "layout_mode": {"type": "integer"}, "allow_disable": {"type": "boolean"},
                          "settle_ms": {"type": "integer"},
                          "extension_uuid": {"type": "string"},
                          "confirm_timeout_ms": {"type": "integer"},
                          "stop_wait_ms": {"type": "integer"}},
        "params_defaults": {"target": "enable", "method": 2, "layout_mode": 1,
                            "allow_disable": False, "settle_ms": 400,
                            "extension_uuid": EXTENSION_UUID, "confirm_timeout_ms": 6000,
                            "stop_wait_ms": 20000},
        "input_semantics": {"usb.settings": ["Connector, modes and scale to apply."]},
        "output_semantics": {"display_result": ["Applied state, whether a change was needed and verification result."]},
    },
)
class DisplayApply:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        target = params["target"]
        if target == "disable" and not params["allow_disable"]:
            return {"display_result": {"target": target, "changed": False, "verified": False,
                                       "skipped": True,
                                       "reason": "removing a monitor requires explicit confirmation"}}
        if target == "disable" and _service_active(settings["sunshine_unit"]):
            deadline = time.monotonic() + max(int(params.get("stop_wait_ms", 20000)), 1000) / 1000.0
            while _service_active(settings["sunshine_unit"]) and time.monotonic() < deadline:
                time.sleep(0.25)
            if _service_active(settings["sunshine_unit"]):
                return {"display_result": {"target": target, "changed": False, "verified": False,
                                           "skipped": True,
                                           "reason": "sunshine is still casting a monitor; stop the stream first"}}
        connection = _bus()
        state = _state(connection)
        if target == "enable" and settings["connector"] not in {spec[0] for spec in state[1]}:
            # 虚拟副屏由 Sunshine 的录屏门户创建；没有时先把它拉起来再等一等。
            try:
                subprocess.run(["systemctl", "--user", "start", settings["sunshine_unit"]],
                               capture_output=True, text=True, timeout=20)
            except (OSError, subprocess.TimeoutExpired):
                pass
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and settings["connector"] not in {spec[0] for spec in state[1]}:
                time.sleep(0.5)
                state = _state(connection)
        if layout.config_matches(state, target, settings["connector"],
                                 settings["virtual_mode"], settings["builtin_mode"], settings["scale"]):
            return {"display_result": {"target": target, "changed": False, "verified": True}}
        if not _extension_active(params["extension_uuid"]):
            return {"display_result": {"target": target, "changed": False, "verified": False,
                                       "skipped": True,
                                       "reason": "display confirmation extension is not active"}}
        marker = _marker_path()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(int(time.time())), encoding="utf-8")
        previous = _rebuild_previous(state, state[2])
        config = layout.build_logical_config(state, target, settings["connector"],
                                             settings["virtual_mode"], settings["builtin_mode"], settings["scale"])
        _apply(connection, state, config, int(params["method"]), int(params["layout_mode"]))
        time.sleep(max(int(params["settle_ms"]), 0) / 1000.0)
        confirmed = _await_confirmation(target, settings, int(params["confirm_timeout_ms"]))
        verified = confirmed and layout.config_matches(
            _state(connection), target, settings["connector"],
            settings["virtual_mode"], settings["builtin_mode"], settings["scale"])
        rolled_back = False
        if not verified:
            _apply(connection, state, previous, int(params["method"]), int(params["layout_mode"]))
            time.sleep(max(int(params["settle_ms"]), 0) / 1000.0)
            rolled_back = True
        return {"display_result": {"target": target, "changed": True, "verified": bool(verified),
                                   "rolled_back": rolled_back}}
