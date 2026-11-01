"""Table-driven tests for the pure Mutter layout planner."""
from __future__ import annotations

import pytest

from nodes.display import layout

CONNECTORS = ["eDP-1", "DP-1"]


def state(*, virtual_active=True, virtual_mode="2560x1600@60.000", builtin_mode="2560x1600@60.000",
          scale=1.0, builtin=True):
    """Mutter GetCurrentState shape: (serial, monitor specs, logical monitors)."""
    specs = []
    if builtin:
        specs.append((("eDP-1", "eDP", "builtin", "0x1"),
                      [(builtin_mode, 2560, 1600, 0.0, [builtin_mode], {},
                        {"is-current": True, "is-preferred": True})],
                      {"is-builtin": True, "display-name": "eDP-1"}))
    specs.append((("DP-1", "BOE", "virtual", "0x2"),
                  [(virtual_mode, 2560, 1600, 0.0, [virtual_mode], {},
                    {"is-current": virtual_active, "is-preferred": True})],
                  {"is-builtin": False, "display-name": "DP-1"}))
    logicals = []
    x = 0
    if builtin:
        logicals.append((x, 0, scale, 0, True, [("eDP-1", builtin_mode, {})], {}))
        x += 2560
    if virtual_active:
        logicals.append((x, 0, scale, 0, False, [("DP-1", virtual_mode, {})], {}))
    return (0, specs, logicals)

MATCH_CASES = [
    ("enable active", state(), "enable", True),
    ("enable while disabled", state(virtual_active=False), "enable", False),
    ("disable while active", state(), "disable", False),
    ("disable while already off", state(virtual_active=False), "disable", True),
    ("wrong scale", state(scale=1.25), "enable", False),
    ("wrong virtual mode", state(virtual_mode="1920x1080@60.000"), "enable", False),
    ("no builtin display", state(builtin=False), "enable", False),
]


@pytest.mark.parametrize("label,current,target,expected", MATCH_CASES)
def test_config_matches(label, current, target, expected):
    assert layout.config_matches(current, target, "DP-1", "2560x1600@60.000",
                                 "2560x1600@60.000", 1.0) is expected


def test_build_enable_keeps_builtin_and_virtual():
    config = layout.build_logical_config(state(virtual_active=False), "enable", "DP-1",
                                         "2560x1600@60.000", "2560x1600@60.000", 1.0)
    connectors = [spec[0] for logical in config for spec in logical[5]]
    assert "eDP-1" in connectors
    assert "DP-1" in connectors


def test_build_disable_removes_virtual_output():
    config = layout.build_logical_config(state(), "disable", "DP-1",
                                         "2560x1600@60.000", "2560x1600@60.000", 1.0)
    connectors = [spec[0] for logical in config for spec in logical[5]]
    assert connectors == ["eDP-1"]
    builtin = next(logical for logical in config if logical[5][0][0] == "eDP-1")
    assert builtin[4] is True
