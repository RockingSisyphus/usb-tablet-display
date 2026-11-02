"""生成一份用于"虚拟副屏"的 EDID（128 字节基础块），可用作内核 drm.edid_firmware。

用法示例：
    python3 tools/make_edid.py --width 2560 --height 1600 --refresh 60 \
        --name VIRTUAL-DP --vendor BOE --product 0x1234 --serial 0x12345678 \
        --output install/edid/virtual-display.bin
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path


def manufacturer_id(vendor: str) -> bytes:
    code = 0
    letters = (vendor.upper() + "AAA")[:3]
    for index, char in enumerate(letters):
        if not "A" <= char <= "Z":
            raise ValueError(f"厂商代码必须是 3 个大写字母：{vendor}")
        code |= (ord(char) - ord("A") + 1) << (10 - 5 * index)
    return struct.pack(">H", code)


def detailed_timing(width: int, height: int, refresh: int) -> bytes:
    hblank, hfront, hsync = 160, 48, 32
    vblank, vfront, vsync = 23, 3, 5
    htotal, vtotal = width + hblank, height + vblank
    clock = round(htotal * vtotal * refresh / 1e6 * 100)  # 10 kHz 单位
    if not 0 < clock < 0xFFFF:
        raise ValueError("像素时钟超出 EDID 可表示范围")

    def split(value):
        return value & 0xFF, (value >> 8) & 0x0F

    h_active_low, h_active_high = split(width)
    h_blank_low, h_blank_high = split(hblank)
    v_active_low, v_active_high = split(height)
    v_blank_low, v_blank_high = split(vblank)
    h_front_low, h_front_high = split(hfront)
    h_sync_low, h_sync_high = split(hsync)
    v_front_low, v_front_high = split(vfront)
    v_sync_low, v_sync_high = split(vsync)

    data = bytearray(18)
    struct.pack_into("<H", data, 0, clock)
    data[2] = h_active_low
    data[3] = h_blank_low
    data[4] = (h_active_high << 4) | h_blank_high
    data[5] = v_active_low
    data[6] = v_blank_low
    data[7] = (v_active_high << 4) | v_blank_high
    data[8] = h_front_low
    data[9] = h_sync_low
    data[10] = (v_front_low << 4) | (v_sync_low & 0x0F)
    data[11] = (h_front_high << 6) | (h_sync_high << 4) | (v_front_high << 2) | v_sync_high
    data[12] = width // 10 & 0xFF
    data[13] = height // 10 & 0xFF
    data[14] = 0
    data[17] = 0x1E  # 数字分离同步，行/场均为正极性
    return bytes(data)


def text_descriptor(tag: int, text: str) -> bytes:
    payload = text.encode("ascii")[:13]
    payload += b"\n" + b" " * (13 - len(payload))
    return bytes([0x00, 0x00, 0x00, tag, 0x00]) + payload[:13]


def range_descriptor(low: int = 50, high: int = 75, clock: int = 300) -> bytes:
    return bytes([0x00, 0x00, 0x00, 0xFD, 0x00, low, high, 30, 200, clock // 10,
                  0x00, 0x0A]) + b" " * 6


def build_edid(width: int, height: int, refresh: int, name: str,
               vendor: str, product: int, serial: int, year: int = 2026) -> bytes:
    data = bytearray(128)
    data[0:8] = bytes.fromhex("00FFFFFFFFFFFF00")
    data[8:10] = manufacturer_id(vendor)
    struct.pack_into("<H", data, 10, product & 0xFFFF)
    struct.pack_into("<I", data, 12, serial & 0xFFFFFFFF)
    data[16], data[17] = 1, year - 1990
    data[18], data[19] = 1, 4
    data[20] = 0x95  # 数字输入、8bit、DisplayPort
    data[21] = data[22] = 0
    data[23] = 120  # gamma 2.20
    data[24] = 0x0B  # RGB、首选时序、连续频率
    data[25:35] = bytes((0xEE, 0x91, 0xA3, 0x54, 0x4C, 0x99, 0x26, 0x0F, 0x50, 0x54))
    data[35:38] = b"\x00\x00\x00"
    data[38:54] = b"\x01\x01" * 8
    data[54:72] = detailed_timing(width, height, refresh)
    data[72:90] = text_descriptor(0xFE, f"{vendor} {name}"[:13])
    data[90:108] = text_descriptor(0xFC, name)
    data[108:126] = range_descriptor()
    data[126] = 0
    data[127] = (256 - sum(data[:127]) % 256) % 256
    return bytes(data)


def checksum_ok(block: bytes) -> bool:
    return sum(block) % 256 == 0


def parse_preferred(block: bytes):
    dtd = block[54:72]
    clock = struct.unpack_from("<H", dtd, 0)[0]
    if not clock:
        raise ValueError("没有首选时序")
    h_active = dtd[2] | ((dtd[4] >> 4) << 8)
    h_blank = dtd[3] | ((dtd[4] & 0x0F) << 8)
    v_active = dtd[5] | ((dtd[7] >> 4) << 8)
    v_blank = dtd[6] | ((dtd[7] & 0x0F) << 8)
    htotal, vtotal = h_active + h_blank, v_active + v_blank
    refresh = clock * 10000 / (htotal * vtotal)
    return h_active, v_active, round(refresh, 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=2560)
    parser.add_argument("--height", type=int, default=1600)
    parser.add_argument("--refresh", type=int, default=60)
    parser.add_argument("--name", default="VIRTUAL-DP")
    parser.add_argument("--vendor", default="BOE")
    parser.add_argument("--product", type=lambda v: int(v, 0), default=0x1234)
    parser.add_argument("--serial", type=lambda v: int(v, 0), default=0x12345678)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[1] / "install" / "edid" / "virtual-display.bin")
    args = parser.parse_args()
    data = build_edid(args.width, args.height, args.refresh, args.name,
                      args.vendor, args.product, args.serial)
    if not checksum_ok(data):
        raise SystemExit("生成的 EDID 校验失败")
    mode = parse_preferred(data)
    if mode[0] != args.width or mode[1] != args.height:
        raise SystemExit(f"生成的时序不正确：{mode}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f"已写入 {args.output}：{args.width}x{args.height}@{mode[2]}Hz，"
          f"厂商 {args.vendor}，名称 {args.name}，{len(data)} 字节")


if __name__ == "__main__":
    main()
