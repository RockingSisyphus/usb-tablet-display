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
