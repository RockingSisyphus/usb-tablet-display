"""Authorize Sunshine for the virtual display through the portal permission store."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from vibeflow.targets.python.sdk import node

def _token_path():
    return Path.home() / ".config/sunshine/portal_token"
PG_BASE = ("gdbus", "call", "--session", "--dest", "org.freedesktop.impl.portal.PermissionStore",
           "--object-path", "/org/freedesktop/impl/portal/PermissionStore")


def _run(argv, timeout=10):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


@node(
    id="usb.portal_pin", node_type="vibeflow.node",
    display_name="授权录屏",
    description="把虚拟副屏加入系统的录屏授权名单，避免每次串流都被系统弹窗拦住。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.stream_state", "cardinality": "exactly_one", "display_name": "Stream state"},
        ],
        "provides": [{"key": "portal_state", "type": "usb.portal_state", "display_name": "Portal state"}],
        "params_schema": {},
        "params_defaults": {},
        "input_semantics": {
            "usb.settings": ["Sunshine app id and the portal output identifier."],
            "usb.stream_state": ["Sunshine must have run once so its portal token exists."],
        },
        "output_semantics": {"portal_state": ["Whether the portal entry changed or is already correct."]},
    },
)
class PortalPin:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        token_path = _token_path()
        if not token_path.exists():
            return {"portal_state": {"state": "authorization-needed", "changed": False}}
        token = token_path.read_text(encoding="utf-8").strip()
        lookup = _run([*PG_BASE, "--method", "org.freedesktop.impl.portal.PermissionStore.Lookup",
                       "remote-desktop", token])
        if lookup is not None and f"<'{settings['portal_id']}'>" in lookup.stdout:
            return {"portal_state": {"state": "virtual-display", "changed": False}}
        now = time.time_ns() // 1000
        data = (f"<('GNOME', uint32 1, <(int64 {now}, int64 {now + 1}, uint32 7, false, "
                f"[(uint32 0, uint32 1, <'{settings['portal_id']}'>)])>)>")
        result = _run([*PG_BASE, "--method", "org.freedesktop.impl.portal.PermissionStore.Set",
                       "remote-desktop", "true", token,
                       f"{{'{settings['sunshine_app']}': ['yes']}}", data])
        if result is None or result.returncode != 0:
            return {"portal_state": {"state": "failed", "changed": False}}
        return {"portal_state": {"state": "virtual-display", "changed": True}}
