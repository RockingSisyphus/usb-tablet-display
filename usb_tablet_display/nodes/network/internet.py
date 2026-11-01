"""Supervise gnirehtet reverse tethering and probe tablet internet access."""
from __future__ import annotations

import subprocess

from vibeflow.targets.python.sdk import node

VPN_MARKER = "VPN:com.genymobile.gnirehtet"


def _run(argv, timeout):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _unit_active(unit):
    done = _run(["systemctl", "--user", "is-active", unit], 5)
    return done is not None and done.stdout.strip() == "active"


def _adb(settings, args, timeout=8):
    return _run([settings["adb"], "-s", settings["serial"], "shell", *args], timeout)


def _vpn_present(settings):
    if not _unit_active(settings["vpn_unit"]):
        return False
    done = _adb(settings, ["dumpsys", "connectivity"], 10)
    if done is None:
        return False
    return any(VPN_MARKER in row and "InterfaceName: tun0" in row for row in done.stdout.splitlines())


def _tablet_internet(settings):
    for url in settings["probe_urls"]:
        done = _adb(settings, ["/system/bin/curl", "-4", "--interface", "tun0", "-fsS",
                               "-o", "/dev/null", "--connect-timeout", "3",
                               "--max-time", "5", url], 9)
        if done is not None and done.returncode == 0:
            return True
    return False


def _host_internet(settings):
    for url in settings["probe_urls"]:
        done = _run(["curl", "-4", "-fsS", "-o", "/dev/null", "--connect-timeout", "3",
                     "--max-time", "5", url], 7)
        if done is not None and done.returncode == 0:
            return True
    return False


@node(
    id="usb.internet_sync", node_type="vibeflow.node",
    display_name="同步平板网络",
    description="确保平板能通过 USB 共享电脑的网络，并实际测试平板是否真的能上网。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [{"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"}],
        "provides": [{"key": "internet_state", "type": "usb.internet_state", "display_name": "Internet state"}],
        "params_schema": {"timeout_ms": {"type": "integer"}},
        "params_defaults": {"timeout_ms": 15000},
        "input_semantics": {"usb.settings": ["VPN unit name, ADB serial and probe URLs."]},
        "output_semantics": {"internet_state": ["VPN presence, tablet reachability and host internet state."]},
    },
)
class InternetSync:
    def run_pure(self, inputs, params):
        settings = inputs["usb.settings"]["value"]
        present = _vpn_present(settings)
        if not present:
            _run(["systemctl", "--user", "reset-failed", settings["vpn_unit"]], 10)
            _run(["systemctl", "--user", "restart", settings["vpn_unit"]], 15)
            import time
            deadline = time.monotonic() + max(int(params["timeout_ms"]), 1000) / 1000.0
            while time.monotonic() < deadline and not present:
                time.sleep(1)
                present = _vpn_present(settings)
        tablet_ok = _tablet_internet(settings) if present else False
        host_ok = _host_internet(settings)
        if tablet_ok:
            status = "ok"
        elif not present:
            status = "disconnected"
        else:
            status = "unavailable"
        return {"internet_state": {"vpn": "present" if present else "missing",
                                   "tablet_ok": tablet_ok, "host_ok": host_ok,
                                   "status": status}}


@node(
    id="usb.internet_tick", node_type="vibeflow.node",
    display_name="定期检查网络",
    description="每隔一段时间检查一次平板网络；一切正常时不做多余操作。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [
            {"type": "usb.settings", "cardinality": "exactly_one", "display_name": "Tablet settings"},
            {"type": "usb.state", "cardinality": "exactly_one", "display_name": "Runtime state"},
        ],
        "provides": [{"key": "internet_state", "type": "usb.internet_state", "display_name": "Internet state"}],
        "params_schema": {"interval_s": {"type": "integer"}, "timeout_ms": {"type": "integer"}},
        "params_defaults": {"interval_s": 60, "timeout_ms": 30000},
        "input_semantics": {
            "usb.settings": ["VPN unit, ADB serial and probe URLs."],
            "usb.state": ["State carrying the last internet check timestamp."],
        },
        "output_semantics": {"internet_state": ["Internet status, whether it was checked and when."]},
    },
)
class InternetTick:
    def run_pure(self, inputs, params):
        import time
        settings = inputs["usb.settings"]["value"]
        state = inputs["usb.state"]["value"]
        now = time.time()
        last = float(state.get("internet_at") or 0)
        interval = max(int(params["interval_s"]), 5)
        if now - last < interval:
            return {"internet_state": {"status": state.get("internet", "unknown"),
                                       "checked": False, "at": last}}
        present = _vpn_present(settings)
        if not present:
            _run(["systemctl", "--user", "reset-failed", settings["vpn_unit"]], 10)
            _run(["systemctl", "--user", "restart", settings["vpn_unit"]], 15)
            deadline = time.monotonic() + max(int(params["timeout_ms"]), 1000) / 1000.0
            while time.monotonic() < deadline and not present:
                time.sleep(1)
                present = _vpn_present(settings)
        tablet_ok = _tablet_internet(settings) if present else False
        host_ok = _host_internet(settings)
        if tablet_ok:
            status = "ok"
        elif not present:
            status = "disconnected"
        else:
            status = "unavailable"
        return {"internet_state": {"status": status, "checked": True, "at": now,
                                   "vpn": "present" if present else "missing",
                                   "tablet_ok": tablet_ok, "host_ok": host_ok}}
