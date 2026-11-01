"""GNOME monitor layout nodes backed by Mutter's DisplayConfig interface."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from gi.repository import Gio, GLib

from vibeflow.targets.python.sdk import node

from usb_tablet_display.nodes.display import layout


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
    deadline = time.monotonic() + max(timeout_ms, 0) / 1000.0
    while time.monotonic() < deadline:
        if not _marker_path().exists():
            return True
        time.sleep(0.1)
    return not _marker_path().exists()


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
    display_name="Match display layout",
    description="Reads the Mutter layout and reports whether it already equals the requested target.",
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
    display_name="Apply display layout",
    description="Applies the requested layout when needed and verifies the result by re-reading Mutter state.",
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
                          "confirm_timeout_ms": {"type": "integer"}},
        "params_defaults": {"target": "enable", "method": 2, "layout_mode": 1,
                            "allow_disable": False, "settle_ms": 400,
                            "extension_uuid": EXTENSION_UUID, "confirm_timeout_ms": 6000},
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
            return {"display_result": {"target": target, "changed": False, "verified": False,
                                       "skipped": True,
                                       "reason": "sunshine is still casting a monitor; stop the stream first"}}
        connection = _bus()
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
        previous = [tuple(item) for item in state[2]]
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
            marker.unlink(missing_ok=True)
            _apply(connection, state, previous, int(params["method"]), int(params["layout_mode"]))
            time.sleep(max(int(params["settle_ms"]), 0) / 1000.0)
            rolled_back = True
        return {"display_result": {"target": target, "changed": True, "verified": bool(verified),
                                   "rolled_back": rolled_back}}
