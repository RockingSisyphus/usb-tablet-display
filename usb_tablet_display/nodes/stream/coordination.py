"""通过本机协调服务发起和观察连接、断开工作流。"""
from __future__ import annotations

from vibeflow.targets.python.sdk import node

WORKFLOWS = {
    "connect": {"root": "usb-tablet-display", "path": "configs/connect.jsonc"},
    "disconnect": {"root": "usb-tablet-display", "path": "configs/disconnect.jsonc"},
}


def _launch(config):
    return {"kind": "process", "cwd": "..",
            "command": ["python3", "run.py", "coordination", "run-python",
                        "--workspace", "vibeflow_config.jsonc", "--config", config]}


def _action(inputs):
    return inputs["usb.action"]["value"].get("action", "none")


def _busy(inputs):
    return bool(inputs["usb.state"]["value"].get("session_instance"))


@node(
    id="usb.call_connect", node_type="vibeflow.node",
    display_name="发起连接", description="需要连接时，通过协调服务在后台启动连接工作流，并记下它的实例编号。",
    version="0.1.0", flow_kind="workflow-io",
    workflow_operations=[{"operation": "call", "wait": False}],
    contract={
        "requires": [
            {"type": "usb.action", "cardinality": "exactly_one", "display_name": "决定"},
            {"type": "usb.state", "cardinality": "exactly_one", "display_name": "运行状态"},
        ],
        "provides": [{"key": "start_connect", "type": "usb.session_start_connect", "display_name": "连接启动"}],
        "params_schema": {"workflow": {"type": "object"}, "launch": {"type": "object"}},
        "params_defaults": {"workflow": WORKFLOWS["connect"], "launch": _launch("usb_tablet_display/configs/connect.jsonc")},
        "input_semantics": {"usb.action": ["本轮决定"], "usb.state": ["是否已有实例在跑"]},
        "output_semantics": {"start_connect": ["是否启动以及实例编号"]},
    },
)
class CallConnect:
    async def run_pure(self, inputs, params, context):
        if _action(inputs) != "connect" or _busy(inputs):
            return {"start_connect": {"started": False, "action": "connect"}}
        child = await context.workflow.call({"workflow": params["workflow"],
                                             "launch": params["launch"]})
        return {"start_connect": {"started": True, "action": "connect", "instance": child["id"]}}


@node(
    id="usb.call_disconnect", node_type="vibeflow.node",
    display_name="发起断开", description="需要断开时，通过协调服务在后台启动断开工作流，并记下它的实例编号。",
    version="0.1.0", flow_kind="workflow-io",
    workflow_operations=[{"operation": "call", "wait": False}],
    contract={
        "requires": [
            {"type": "usb.action", "cardinality": "exactly_one", "display_name": "决定"},
            {"type": "usb.state", "cardinality": "exactly_one", "display_name": "运行状态"},
        ],
        "provides": [{"key": "start_disconnect", "type": "usb.session_start_disconnect", "display_name": "断开启动"}],
        "params_schema": {"workflow": {"type": "object"}, "launch": {"type": "object"}},
        "params_defaults": {"workflow": WORKFLOWS["disconnect"], "launch": _launch("usb_tablet_display/configs/disconnect.jsonc")},
        "input_semantics": {"usb.action": ["本轮决定"], "usb.state": ["是否已有实例在跑"]},
        "output_semantics": {"start_disconnect": ["是否启动以及实例编号"]},
    },
)
class CallDisconnect:
    async def run_pure(self, inputs, params, context):
        if _action(inputs) != "disconnect" or _busy(inputs):
            return {"start_disconnect": {"started": False, "action": "disconnect"}}
        child = await context.workflow.call({"workflow": params["workflow"],
                                             "launch": params["launch"]})
        return {"start_disconnect": {"started": True, "action": "disconnect", "instance": child["id"]}}


@node(
    id="usb.poll_session", node_type="vibeflow.node",
    display_name="查看会话结果", description="如果有一个连接或断开正在后台进行，就查看它是否已经结束以及结果如何。",
    version="0.1.0", flow_kind="workflow-io",
    workflow_operations=[{"operation": "wait"}],
    contract={
        "requires": [{"type": "usb.state", "cardinality": "exactly_one", "display_name": "运行状态"}],
        "provides": [{"key": "session_result", "type": "usb.session_result", "display_name": "会话结果"}],
        "params_schema": {"wait_timeout": {"type": "integer"}, "max_wait_errors": {"type": "integer"}},
        "params_defaults": {"wait_timeout": 1, "max_wait_errors": 240},
        "input_semantics": {"usb.state": ["当前保存的实例编号与动作"]},
        "output_semantics": {"session_result": ["是否仍在进行，以及结束时的结果"]},
    },
)
class PollSession:
    async def run_pure(self, inputs, params, context):
        state = inputs["usb.state"]["value"]
        instance = state.get("session_instance")
        if not instance:
            return {"session_result": {"running": False, "action": "none"}}
        try:
            result = await context.workflow.wait({"id": instance,
                                                  "timeout": int(params["wait_timeout"])})
        except Exception as error:
            code = str(getattr(error, "code", ""))
            errors = int(state.get("session_wait_errors") or 0) + 1
            message = str(error)
            if code == "VF_WAIT_TIMEOUT":
                return {"session_result": {"running": True, "action": state.get("session_action", "none"),
                                           "wait_errors": errors}}
            if errors < int(params.get("max_wait_errors", 240)):
                return {"session_result": {"running": True, "action": state.get("session_action", "none"),
                                           "wait_error": message[:120], "wait_errors": errors}}
            return {"session_result": {"running": False, "action": state.get("session_action", "none"),
                                       "code": -1, "detail": message[:200],
                                       "wait_errors": errors}}
        if not isinstance(result, dict):
            return {"session_result": {"running": True, "action": state.get("session_action", "none")}}
        terminal = result.get("state") in ("succeeded", "failed", "cancelled")
        if result.get("pending") or not terminal:
            return {"session_result": {"running": True, "action": state.get("session_action", "none")}}
        code = 0 if result.get("state") == "succeeded" else 1
        return {"session_result": {"running": False, "action": state.get("session_action", "none"),
                                   "code": code, "detail": str(result.get("error"))[:200]}}
