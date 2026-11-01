"""Shared helpers for the behaviour-level test suite."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "kernel" / "vibeflow-kernel.zip"
for entry in (str(KERNEL), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)


def env(inputs, key):
    return inputs[key]["value"]


@pytest.fixture()
def settings(tmp_path):
    """Node-shaped settings pointing state and tools at the test sandbox."""
    return {
        "serial": "TEST123",
        "connector": "DP-1",
        "virtual_mode": "2560x1600@60.000",
        "builtin_mode": "2560x1600@60.000",
        "scale": 1.0,
        "connection": "android-usb-direct",
        "host_name": "test-pc",
        "app_name": "Desktop",
        "app_id": "881448767",
        "moonlight_package": "com.limelight",
        "sunshine_unit": "test-sunshine.service",
        "vpn_unit": "test-internet.service",
        "sunshine_app": "dev.lizardbyte.app.Sunshine",
        "sunshine_encoder": "nvenc",
        "sunshine_adapter": "",
        "portal_id": "BOE:VIRTUAL-DP:0x1",
        "adb": "/usr/bin/true",
        "probe_urls": ["https://example.invalid/"],
        "state_path": str(tmp_path / "state.json"),
    }


@pytest.fixture()
def state_path(tmp_path):
    return str(tmp_path / "state.json")
