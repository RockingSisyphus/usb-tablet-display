"""Read Sunshine and Moonlight session state through systemd, journal and adb."""
from __future__ import annotations

import re
import subprocess


def _run(argv, timeout):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def server_connected(unit: str) -> bool:
    shown = _run(["systemctl", "--user", "show", unit, "-P", "InvocationID"], 5)
    if shown is None:
        return False
    invocation = shown.stdout.strip()
    if not invocation:
        return False
    events = _run(["journalctl", "--user", f"_SYSTEMD_INVOCATION_ID={invocation}",
                   "--grep", "CLIENT (CONNECTED|DISCONNECTED)", "-n", "1", "--no-pager", "-o", "cat"], 5)
    if events is None:
        return False
    found = re.findall(r"CLIENT (CONNECTED|DISCONNECTED)", events.stdout)
    return bool(found) and found[-1] == "CONNECTED"


def client_connected(settings: dict, timeout: float = 5.0) -> bool:
    done = _run([settings["adb"], "-s", settings["serial"], "shell", "dumpsys",
                 "activity", "activities"], timeout)
    if done is None:
        return False
    return bool(re.search(r"(?:topResumedActivity|mResumedActivity)=.*" +
                          re.escape(settings["moonlight_package"]) + r"/\.Game\b", done.stdout))


def connected(settings: dict) -> bool:
    return server_connected(settings["sunshine_unit"]) and client_connected(settings)


PORTS = (47984, 47989, 47990, 48010)


def ports_ready(settings: dict, host_ip: str) -> tuple[bool, str]:
    """All streaming ports must be listened on the current USB address by our Sunshine."""
    listening = _run(["ss", "-H", "-ltnp"], 5)
    shown = _run(["systemctl", "--user", "show", settings["sunshine_unit"], "-P", "MainPID"], 5)
    if listening is None or shown is None:
        return False, "cannot inspect listening sockets"
    pid = shown.stdout.strip()
    for port in PORTS:
        rows = [row for row in listening.stdout.splitlines() if re.search(rf":{port}\s", row)]
        if not rows:
            return False, f"port {port} not listening"
        if not any(f"pid={pid}," in row for row in rows):
            return False, f"port {port} owned by another process"
        if host_ip and any(row.split()[3] != f"{host_ip}:{port}" for row in rows):
            return False, f"port {port} is not bound to usb address {host_ip}"
    return True, ""
