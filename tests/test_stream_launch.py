"""Scenario tests for the Moonlight launch node using a stubbed adb."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from usb_tablet_display.nodes.stream.moonlight import MoonlightConnect


STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_LOG"
case "$*" in
  *"/system/bin/curl"*) echo "${STUB_CURL_CODE:-200}" ;;
  *"get-state"*) echo "device" ;;
  *"uiautomator dump"*) echo "dumped" ;;
  *) exit 0 ;;
esac
"""


@pytest.fixture()
def stub(tmp_path, monkeypatch, settings):
    script = tmp_path / "adb-stub"
    script.write_text(STUB)
    script.chmod(0o755)
    log = tmp_path / "adb.log"
    monkeypatch.setenv("STUB_LOG", str(log))
    settings = dict(settings, adb=str(script))
    return settings, log


def run(settings, address, state_path):
    inputs = {
        "usb.settings": {"value": settings},
        "usb.usb_address": {"value": {"address": address}},
        "usb.stream_ready": {"value": {"ok": True}},
        "usb.state": {"value": {}},
    }
    params = {"register_ms": 2000, "connect_ms": 2000, "reach_ms": 100, "state_path": state_path}
    return MoonlightConnect().run_pure(inputs, params)["launch_state"]


def test_missing_address_short_circuits(stub, state_path):
    settings, log = stub
    result = run(settings, "", state_path)
    assert result["stage"] == "no-usb-address"
    assert result["connected"] is False
    assert not log.exists()


def test_unreachable_server_is_reported_before_launch(stub, state_path, monkeypatch):
    settings, log = stub
    monkeypatch.setenv("STUB_CURL_CODE", "000")
    result = run(settings, "10.0.0.9", state_path)
    assert result["stage"] == "reachability"
    assert "serverinfo" in result["error"]
    calls = log.read_text()
    assert "am start" not in calls
