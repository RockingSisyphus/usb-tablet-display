"""Session gates and summaries shared by connect and teardown."""
from __future__ import annotations

from vibeflow.targets.python.sdk import node


@node(
    id="usb.require_ready", node_type="vibeflow.node",
    display_name="确认平板可用",
    description="平板没有插好或调试连接未获授权时，立刻停下并说明原因。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.process"],
    contract={
        "requires": [
            {"type": "usb.device", "cardinality": "exactly_one", "display_name": "USB device"},
            {"type": "usb.adb_state", "cardinality": "exactly_one", "display_name": "ADB transport state"},
        ],
        "provides": [{"key": "readiness", "type": "usb.readiness", "display_name": "Session readiness"}],
        "params_schema": {},
        "params_defaults": {},
        "input_semantics": {
            "usb.device": ["USB presence resolved from sysfs."],
            "usb.adb_state": ["ADB transport state for the configured serial."],
        },
        "output_semantics": {"readiness": ["Confirmed device and ADB readiness for the session."]},
    },
)
class RequireReady:
    def run_pure(self, inputs, params):
        device = inputs["usb.device"]["value"]
        adb = inputs["usb.adb_state"]["value"]
        if not device.get("present"):
            raise RuntimeError(f"tablet {device.get('serial')} is not present on the USB bus")
        if adb.get("state") != "device":
            raise RuntimeError(f"ADB transport is {adb.get('state')}: {adb.get('detail', '')}")
        return {"readiness": {"device_present": True, "adb": "device",
                              "serial": device.get("serial"), "interface": device.get("interface", "")}}


@node(
    id="usb.session_summary", node_type="vibeflow.node",
    display_name="汇总连接结果",
    description="把这次连接是否成功、画面是否连上等关键结果整理成结论。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.process"],
    contract={
        "requires": [
            {"type": "usb.readiness", "cardinality": "exactly_one", "display_name": "Session readiness"},
            {"type": "usb.display_result", "cardinality": "exactly_one", "display_name": "Display result"},
            {"type": "usb.display_check", "cardinality": "exactly_one", "display_name": "Display check"},
            {"type": "usb.stream_check", "cardinality": "exactly_one", "display_name": "Stream check"},
        ],
        "provides": [{"key": "session_result", "type": "usb.session_result", "display_name": "Session result"}],
        "params_schema": {},
        "params_defaults": {},
        "input_semantics": {
            "usb.readiness": ["Device and ADB readiness."],
            "usb.display_result": ["Applied layout result."],
            "usb.display_check": ["Post-apply layout comparison."],
            "usb.stream_check": ["Sunshine and Moonlight stream state."],
        },
        "output_semantics": {"session_result": ["Connect session outcome."]},
    },
)
class SessionSummary:
    def run_pure(self, inputs, params):
        readiness = inputs["usb.readiness"]["value"]
        result = inputs["usb.display_result"]["value"]
        check = inputs["usb.display_check"]["value"]
        stream = inputs["usb.stream_check"]["value"]
        return {"session_result": {
            "session": "connect",
            "serial": readiness.get("serial"),
            "interface": readiness.get("interface"),
            "changed": bool(result.get("changed")),
            "verified": bool(check.get("matches")),
            "stream_connected": bool(stream.get("connected")),
        }}


@node(
    id="usb.teardown_summary", node_type="vibeflow.node",
    display_name="汇总断开结果",
    description="把这次断开是否成功、屏幕是否已撤销等关键结果整理成结论。",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.process"],
    contract={
        "requires": [
            {"type": "usb.display_result", "cardinality": "exactly_one", "display_name": "Display result"},
            {"type": "usb.display_check", "cardinality": "exactly_one", "display_name": "Display check"},
        ],
        "provides": [{"key": "session_result", "type": "usb.session_result", "display_name": "Session result"}],
        "params_schema": {},
        "params_defaults": {},
        "input_semantics": {
            "usb.display_result": ["Applied layout result."],
            "usb.display_check": ["Post-apply layout comparison."],
        },
        "output_semantics": {"session_result": ["Teardown session outcome."]},
    },
)
class TeardownSummary:
    def run_pure(self, inputs, params):
        result = inputs["usb.display_result"]["value"]
        check = inputs["usb.display_check"]["value"]
        return {"session_result": {
            "session": "teardown",
            "changed": bool(result.get("changed")),
            "verified": bool(check.get("matches")),
            "skipped": bool(result.get("skipped")),
            "reason": str(result.get("reason") or "")[:200],
            "rolled_back": bool(result.get("rolled_back")),
        }}
