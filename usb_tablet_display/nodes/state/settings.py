"""Load tablet configuration from TOML with the historical defaults."""
from __future__ import annotations

import tomllib
from pathlib import Path

from vibeflow.targets.python.sdk import node

def _defaults() -> dict:
    return {
    "serial": "R52W70H37TW",
    "connector": "DP-1",
    "virtual_mode": "2560x1600@300.000",
    "builtin_mode": "2560x1600@60.000",
    "scale": 1.0,
    "display_settle_seconds": 4.0,
    "connection": "android-usb-direct",
    "host_name": "rockingsisyphus-pc",
    "app_name": "Desktop",
    "app_id": "",
    "shared_ui_snapshot": "",
    "moonlight_package": "com.limelight",
    "portal_id": "BOE:VIRTUAL-DP:0x12345678",
    "sunshine_app": "dev.lizardbyte.app.Sunshine",
    "sunshine_unit": "app-dev.lizardbyte.app.Sunshine.service",
    "sunshine_encoder": "nvenc",
    "sunshine_adapter": "",
    "vpn_unit": "usb-tablet-internet.service",
    "adb": "/usr/bin/adb",
    "gnirehtet": "~/.local/share/android-usb-secondary-display/gnirehtet/gnirehtet",
    "dns": ["223.5.5.5", "1.1.1.1"],
    "probe_urls": ["https://work.weixin.qq.com/", "https://www.baidu.com/"],
    "keep_awake": False,
}


def _config_path() -> Path:
    return Path("~/.config/android-usb-secondary-display/tablet.toml").expanduser()


@node(
    id="usb.load_settings", node_type="vibeflow.node",
    display_name="Load settings",
    description="Reads the tablet TOML configuration and applies historical defaults for missing keys.",
    version="0.1.0", flow_kind="process",
    rulesets=["vibeflow.python_io"],
    contract={
        "requires": [],
        "provides": [{"key": "settings", "type": "usb.settings", "display_name": "Tablet settings"}],
        "params_schema": {"config_path": {"type": "string"}},
        "params_defaults": {"config_path": ""},
        "input_semantics": {},
        "output_semantics": {"settings": ["Merged configuration values used by later nodes."]},
    },
)
class LoadSettings:
    def run_pure(self, inputs, params):
        path = Path(params["config_path"]) if params["config_path"] else _config_path()
        values = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        unknown = sorted(set(values) - set(_defaults()))
        if unknown:
            raise ValueError(f"unknown configuration keys: {', '.join(unknown)}")
        merged = {**_defaults(), **values}
        merged["_config_path"] = str(path)
        return {"settings": merged}
