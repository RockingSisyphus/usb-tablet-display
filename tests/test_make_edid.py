"""生成的 EDID 必须自洽：校验和、首选时序与名称。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import make_edid  # noqa: E402


def names(block):
    found = []
    for offset in range(54, 126, 18):
        desc = block[offset:offset + 18]
        if desc[3] == 0xFC:
            found.append(desc[5:18].split(b"\n")[0].decode("ascii", "ignore"))
    return found


@pytest.mark.parametrize("width,height,refresh", [(2560, 1600, 60), (1920, 1080, 60), (2560, 1440, 90)])
def test_generated_edid_is_valid(width, height, refresh):
    block = make_edid.build_edid(width, height, refresh, "VIRTUAL-DP", "BOE", 0x1234, 0x12345678)
    assert len(block) == 128
    assert block[:8] == bytes.fromhex("00FFFFFFFFFFFF00")
    assert make_edid.checksum_ok(block)
    assert make_edid.parse_preferred(block)[:2] == (width, height)
    assert abs(make_edid.parse_preferred(block)[2] - refresh) <= 1
    assert names(block) == ["VIRTUAL-DP"]


def test_manufacturer_code_is_three_letters():
    assert make_edid.manufacturer_id("BOE") == bytes.fromhex("09e5")


def test_invalid_vendor_is_rejected():
    with pytest.raises(ValueError):
        make_edid.manufacturer_id("BO1")
