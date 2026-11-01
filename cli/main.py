"""Command line entry for the USB tablet secondary display."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = Path("/tmp/usb-tablet-display/status.json")
REQUESTS = Path("/tmp/usb-tablet-display/requests")
UNIT = "usb-tablet-daemon.service"


def _request(action, value=None):
    REQUESTS.mkdir(parents=True, exist_ok=True)
    path = REQUESTS / f"{int(time.time() * 1000)}-{action}.json"
    path.write_text(json.dumps({"action": action, "value": value}), encoding="utf-8")
    return 0


def _state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _status(as_json):
    subprocess.run([sys.executable, "run.py", "run", "--config",
                    "usb_tablet_display/configs/status.jsonc", "--input",
                    "usb_tablet_display/probes/daemon.json"],
                   cwd=ROOT, capture_output=True, text=True, timeout=120)
    state = _state().get("status") or {}
    if as_json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    labels = (("usb", "USB 平板"), ("adb", "USB 调试"), ("display", "副屏输出"),
              ("stream", "客户端串流"), ("internet", "电脑提供的网络"),
              ("usb_interface", "USB 网卡"), ("serial", "序列号"))
    for key, title in labels:
        print(f"{title}: {state.get(key, 'unknown')}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="USB 平板副屏")
    parser.add_argument("action", nargs="?", default="status",
                        choices=("status", "enable", "disable", "reconnect", "set-auto",
                                 "auto", "logs", "gui"))
    parser.add_argument("value", nargs="?", choices=("on", "off"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.action == "status":
        return _status(args.json)
    if args.action in ("enable", "disable", "reconnect", "auto"):
        print("请求已提交；使用 status 查看结果。")
        return _request(args.action)
    if args.action == "set-auto":
        if args.value is None:
            parser.error("set-auto requires on or off")
        print("请求已提交；使用 status 查看结果。")
        return _request("set-auto", args.value == "on")
    if args.action == "logs":
        return subprocess.call(["journalctl", "--user", "-u", UNIT, "-n", "150", "--no-pager"])
    if args.action == "gui":
        print("图形界面尚未迁移到新实现。")
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
