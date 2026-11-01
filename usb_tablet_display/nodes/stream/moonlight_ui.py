"""Parse Moonlight UI snapshots without assuming a dialog order."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET


def field(xml, package, resource_id):
    for node in ET.fromstring(xml).iter():
        if node.get("package") != package or node.get("resource-id") != f"{package}:id/{resource_id}":
            continue
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if match:
            x1, y1, x2, y2 = map(int, match.groups())
            return ((x1 + x2) // 2, (y1 + y2) // 2), node.get("text", "")
    return None


def clickable(root, text):
    parents = {child: parent for parent in root.iter() for child in parent}
    for node in root.iter():
        if text not in (node.get("text"), node.get("content-desc")):
            continue
        current = node
        while current is not None:
            if current.get("clickable") == "true":
                return current
            current = parents.get(current)
    return None


def stream_surface(root, package):
    return any(n.get("package") == package and
               n.get("class", "").endswith("SurfaceView") for n in root.iter())


def fresh_snapshot(output, max_age=5):
    try:
        modified, now, xml = output.split("\n", 2)
        if 0 <= int(now) - int(modified) <= max_age and ET.fromstring(xml).tag == "hierarchy":
            return xml
    except (ValueError, ET.ParseError):
        pass
    return None


def dialog_error(xml, package):
    """An acknowledged error dialog, not the ongoing registration spinner."""
    root = ET.fromstring(xml)
    nodes = [n for n in root.iter() if n.get("package") == package]
    if any(n.get("resource-id") == "android:id/button1" for n in nodes):
        return next((n.get("text", "") for n in nodes
                     if n.get("resource-id") == "android:id/message"), "")
    return ""
