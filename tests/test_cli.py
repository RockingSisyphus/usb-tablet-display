"""Command line contract: request files, argument validation and exit codes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_cli(tmp_path, *args):
    env = dict(os.environ, USB_TABLET_STATE_DIR=str(tmp_path))
    return subprocess.run([sys.executable, str(ROOT / "cli" / "main.py"), *args],
                          capture_output=True, text=True, timeout=60, env=env)


def request_of(tmp_path):
    files = sorted((tmp_path / "requests").glob("*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text())


CASES = [
    (("enable",), "enable", None),
    (("disable",), "disable", None),
    (("reconnect",), "reconnect", None),
    (("auto",), "auto", None),
    (("set-auto", "off"), "set-auto", False),
    (("set-auto", "on"), "set-auto", True),
]


@pytest.mark.parametrize("args,action,value", CASES)
def test_actions_queue_one_request(tmp_path, args, action, value):
    done = run_cli(tmp_path, *args)
    assert done.returncode == 0
    payload = request_of(tmp_path)
    assert payload["action"] == action
    assert payload["value"] == value


def test_set_auto_requires_a_value(tmp_path):
    done = run_cli(tmp_path, "set-auto")
    assert done.returncode == 2
    assert not (tmp_path / "requests").exists() or not list((tmp_path / "requests").glob("*.json"))


def test_unknown_action_is_rejected(tmp_path):
    done = run_cli(tmp_path, "explode")
    assert done.returncode == 2
