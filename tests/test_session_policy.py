"""Decision, request and job-state behaviour without any process orchestration."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from usb_tablet_display.nodes.stream.dispatch import DecideAction
from usb_tablet_display.nodes.stream.jobs import CollectJob, JOB_PATH, EXIT_PATH
from usb_tablet_display.nodes.stream.requests import TakeRequest


def inputs(*, settings, device=True, adb="device", connected=False, auto=True,
           last_action=None, request=("none", None), job_running=False):
    state = {"last_action": last_action} if last_action else {}
    if not auto:
        state["auto_enabled"] = False
    return {
        "usb.settings": {"value": settings},
        "usb.state": {"value": state},
        "usb.device": {"value": {"present": device, "interface": "enx-test"}},
        "usb.adb_state": {"value": {"state": adb, "detail": ""}},
        "usb.session_status": {"value": {"connected": connected}},
        "usb.request": {"value": {"action": request[0], "value": request[1]}},
        "usb.job": {"value": {"action": "none", "code": None, "running": job_running}},
    }


DECISION_CASES = [
    ("idle tablet connects", dict(connected=False), "connect", True),
    ("healthy session stays", dict(connected=True), "none", True),
    ("removed tablet tears down", dict(device=False, last_action="connect"), "disconnect", True),
    ("removed tablet without session", dict(device=False, last_action="disconnect"), "none", True),
    ("unauthorized adb tears down", dict(adb="unauthorized", last_action="connect"), "disconnect", True),
    ("auto off tears down", dict(connected=True, auto=False), "disconnect", False),
    ("disable request", dict(request=("disable", None)), "disconnect", False),
    ("enable request", dict(request=("enable", None)), "connect", True),
    ("enable request without tablet", dict(request=("enable", None), device=False), "none", True),
    ("job running blocks new work", dict(connected=False, job_running=True), "none", True),
]


@pytest.mark.parametrize("label,overrides,expected,expected_auto", DECISION_CASES)
def test_decide_action(label, overrides, expected, expected_auto, settings):
    decision = DecideAction().run_pure(inputs(settings=settings, **overrides), {})["action"]
    assert decision["action"] == expected
    assert decision["auto_enabled"] is expected_auto


def test_set_auto_request_updates_policy(settings):
    decision = DecideAction().run_pure(
        inputs(settings=settings, request=("set-auto", False)), {})["action"]
    assert decision == {"action": "policy", "auto_enabled": False,
                        "reason": "automatic session disabled"}


def test_take_request_claims_oldest_and_leaves_queue_empty(tmp_path):
    for name, action in (("100-a.json", "enable"), ("200-b.json", "disable")):
        (tmp_path / name).write_text(json.dumps({"action": action, "value": None}))
    first = TakeRequest().run_pure({}, {"requests_path": str(tmp_path)})["request"]
    second = TakeRequest().run_pure({}, {"requests_path": str(tmp_path)})["request"]
    assert first["action"] == "enable"
    assert second["action"] == "disable"
    assert TakeRequest().run_pure({}, {"requests_path": str(tmp_path)})["request"]["action"] == "none"


def test_collect_job_reports_running_then_exit(tmp_path, monkeypatch):
    monkeypatch.setattr("usb_tablet_display.nodes.stream.jobs.JOB_PATH", str(tmp_path / "job.json"))
    monkeypatch.setattr("usb_tablet_display.nodes.stream.jobs.EXIT_PATH", str(tmp_path / "job.exit"))
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"action": "connect", "pid": os.getpid(),
                               "started_at": time.time()}))
    running = CollectJob().run_pure({}, {})["job"]
    assert running == {"action": "connect", "code": None, "running": True, "detail": ""}
    (tmp_path / "job.exit").write_text("0")
    done = CollectJob().run_pure({}, {})["job"]
    assert done["action"] == "connect" and done["code"] == 0 and done["running"] is False
    assert not job.exists()


def test_collect_job_cleans_up_dead_job_without_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr("usb_tablet_display.nodes.stream.jobs.JOB_PATH", str(tmp_path / "job.json"))
    monkeypatch.setattr("usb_tablet_display.nodes.stream.jobs.EXIT_PATH", str(tmp_path / "job.exit"))
    (tmp_path / "job.json").write_text(json.dumps({"action": "disconnect", "pid": 999999,
                                                   "started_at": time.time()}))
    job = CollectJob().run_pure({}, {})["job"]
    assert job["running"] is False and job["code"] == -1
    assert not (tmp_path / "job.json").exists()
