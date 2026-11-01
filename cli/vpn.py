"""Run gnirehtet reverse tethering as the user unit behind the new stack."""
from __future__ import annotations

import ipaddress
import os
import sys
import tomllib
from pathlib import Path

DEFAULTS = {
    "serial": "R52W70H37TW",
    "adb": "/usr/bin/adb",
    "gnirehtet": "/home/rockingsisyphus/projects/体验优化小项目/平板usb副屏/vendor/gnirehtet/gnirehtet",
    "dns": ["223.5.5.5", "1.1.1.1"],
}


def config():
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / "usb-tablet-display" / "tablet.toml"
    values = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {**DEFAULTS, **{k: values[k] for k in DEFAULTS if k in values}}


def public_routes(dns):
    networks = [ipaddress.ip_network("0.0.0.0/0")]
    for excluded in ("0.0.0.0/8", "10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16",
                     "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/3"):
        block = ipaddress.ip_network(excluded)
        networks = [part for net in networks for part in
                    (net.address_exclude(block) if block.subnet_of(net) else [net])]
    routes = [str(net) for net in sorted(networks)]
    for server in dns:
        route = f"{ipaddress.ip_address(server)}/32"
        if route not in routes:
            routes.append(route)
    return ",".join(routes)


def main():
    cfg = config()
    binary = Path(cfg["gnirehtet"]).expanduser()
    if not binary.is_file():
        print(f"gnirehtet not found: {binary}", file=sys.stderr)
        return 78
    os.chdir(binary.parent)
    os.environ["ADB"] = cfg["adb"]
    if len(sys.argv) > 1 and sys.argv[1] == "stop":
        args = [str(binary), "stop", cfg["serial"]]
    else:
        args = [str(binary), "run", cfg["serial"], "-d", ",".join(cfg["dns"]),
                "-r", public_routes(cfg["dns"])]
    try:
        os.execv(str(binary), args)
    except OSError as error:
        print(f"Cannot execute gnirehtet: {error}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
