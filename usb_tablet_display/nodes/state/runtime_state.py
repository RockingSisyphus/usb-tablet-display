"""Advance one daemon tick and publish the merged runtime state."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from vibeflow.targets.python.sdk import node

DEFAULT_STATE_PATH = "/tmp/usb-tablet-display/state.json"
DEFAULT_SHUTDOWN_PATH = "/tmp/usb-tablet-display/shutdown"


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


@node(
    id="usb.tick_merge", node_type="vibeflow.node",
    display_name="推进一轮循环",
    description="等待一个很短的间隔，把本轮看到的信息写进运行状态，并判断是否需要停止常驻程序。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [
            {"type": "usb.state", "cardinality": "exactly_one", "display_name": "Runtime state"},
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.device", "cardinality": "exactly_one", "display_name": "USB device"},
            {"type": "usb.adb_state", "cardinality": "exactly_one", "display_name": "ADB transport state"},
            {"type": "usb.action", "cardinality": "exactly_one", "display_name": "Session action"},
            {"type": "usb.session_start_connect", "cardinality": "exactly_one", "display_name": "Connect start"},
            {"type": "usb.session_start_disconnect", "cardinality": "exactly_one", "display_name": "Disconnect start"},
            {"type": "usb.session_result", "cardinality": "exactly_one", "display_name": "Session result"},
            {"type": "usb.internet_state", "cardinality": "exactly_one", "display_name": "Internet state"},
        ],
        "provides": [{"key": "stop", "type": "usb.shutdown", "display_name": "Stop flag"}],
        "params_schema": {
            "state_path": {"type": "string"},
            "shutdown_path": {"type": "string"},
            "tick_ms": {"type": "integer"},
            "max_ticks": {"type": "integer"},
        },
        "params_defaults": {
            "state_path": DEFAULT_STATE_PATH,
            "shutdown_path": DEFAULT_SHUTDOWN_PATH,
            "tick_ms": 200,
            "max_ticks": 0,
        },
        "input_semantics": {
            "usb.state": ["State carried from the previous iteration."],
            "usb.settings": ["Configuration for the current run."],
            "usb.device": ["USB presence and RNDIS interface from this iteration."],
            "usb.adb_state": ["ADB transport state from this iteration."],
            "usb.action": ["Decision for this iteration."],
            "usb.session_start_connect": ["Whether a connect instance was started."],
            "usb.session_start_disconnect": ["Whether a disconnect instance was started."],
            "usb.session_result": ["Result of the background session, if any."],
            "usb.internet_state": ["Internet supervision result for this tick."],
        },
        "output_semantics": {"stop": ["True when the daemon should leave its loop."]},
    },
)
class TickMerge:
    def run_pure(self, inputs, params):
        state = dict(inputs["usb.state"]["value"])
        device = inputs["usb.device"]["value"]
        adb = inputs["usb.adb_state"]["value"]
        settings = inputs["usb.settings"]["value"]
        action = inputs["usb.action"]["value"]
        started = inputs["usb.session_start_connect"]["value"]
        started_disconnect = inputs["usb.session_start_disconnect"]["value"]
        session = inputs["usb.session_result"]["value"]
        internet = inputs["usb.internet_state"]["value"]
        time.sleep(max(int(params["tick_ms"]), 1) / 1000.0)
        state.update({
            "ticks": int(state.get("ticks") or 0) + 1,
            "updated_at": time.time(),
            "serial": settings["serial"],
            "device_present": bool(device.get("present")),
            "usb_interface": device.get("interface", ""),
            "adb": adb.get("state", "unavailable"),
            "adb_detail": adb.get("detail", ""),
        })
        if started.get("instance"):
            state["session_instance"] = started["instance"]
            state["session_action"] = started.get("action", "connect")
        if started_disconnect.get("instance"):
            state["session_instance"] = started_disconnect["instance"]
            state["session_action"] = started_disconnect.get("action", "disconnect")
        if internet.get("status"):
            state["internet"] = internet["status"]
        if internet.get("checked"):
            state["internet_at"] = float(internet.get("at") or time.time())
        if action.get("auto_enabled") is not None:
            state["auto_enabled"] = bool(action["auto_enabled"])
        if session.get("wait_errors") is not None:
            state["session_wait_errors"] = int(session["wait_errors"])
        if session.get("running") is False and session.get("code") is not None:
            state["last_action"] = session.get("action") or "none"
            state["last_action_code"] = session["code"]
            state["last_action_at"] = time.time()
            state["last_action_detail"] = str(session.get("detail") or "")[-200:]
            state.pop("session_instance", None)
            state.pop("session_action", None)
            state.pop("session_wait_errors", None)
        _write_json(Path(params["state_path"]), state)
        limit = int(params["max_ticks"] or 0)
        stop = Path(params["shutdown_path"]).exists() or (limit > 0 and state["ticks"] >= limit)
        return {"stop": bool(stop)}
