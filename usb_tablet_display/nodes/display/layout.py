#!/usr/bin/python3
"""Pure GNOME monitor layout planning shared by the display nodes."""

from __future__ import annotations

import math
from collections import deque
from typing import Any, Sequence



BUS_NAME = "org.gnome.Mutter.DisplayConfig"
OBJECT_PATH = "/org/gnome/Mutter/DisplayConfig"
INTERFACE = "org.gnome.Mutter.DisplayConfig"
APPLY_SIGNATURE = "(uua(iiduba(ssa{sv}))a{sv})"
ROTATED_TRANSFORMS = (1, 3, 5, 6)


class ConfigError(RuntimeError):
    pass


class MonitorRecord:
    def __init__(self, connector, modes, properties):
        self.connector = connector
        self.modes = modes
        self.properties = properties


class LogicalPlan:
    def __init__(self, connectors, mode_ids, old_x, old_y, old_width, old_height,
                 new_width, new_height, transform, primary):
        self.connectors = connectors
        self.mode_ids = mode_ids
        self.old_x = old_x
        self.old_y = old_y
        self.old_width = old_width
        self.old_height = old_height
        self.new_width = new_width
        self.new_height = new_height
        self.transform = transform
        self.primary = primary
        self.x = 0
        self.y = 0


def monitor_records(state: tuple[Any, ...]) -> dict[str, MonitorRecord]:
    records: dict[str, MonitorRecord] = {}
    for spec, modes, properties in state[1]:
        connector = spec[0]
        records[connector] = MonitorRecord(connector, modes, properties)
    return records


def mode_by_id(record: MonitorRecord, mode_id: str) -> tuple[Any, ...]:
    for mode in record.modes:
        if mode[0] == mode_id:
            return mode
    raise ConfigError(f"Mode {mode_id} is unavailable on {record.connector}")


def selected_mode_id(
    record: MonitorRecord,
    requested_mode: str | None = None,
) -> str:
    if requested_mode:
        mode_by_id(record, requested_mode)
        return requested_mode

    for property_name in ("is-current", "is-preferred"):
        for mode in record.modes:
            if mode[6].get(property_name):
                return mode[0]

    if record.modes:
        return record.modes[0][0]
    raise ConfigError(f"No usable modes found on {record.connector}")


def mode_size(record: MonitorRecord, mode_id: str, transform: int) -> tuple[int, int]:
    mode = mode_by_id(record, mode_id)
    width, height = int(mode[1]), int(mode[2])
    if transform in ROTATED_TRANSFORMS:
        width, height = height, width
    return width, height


def _close(left: int, right: int) -> bool:
    return abs(left - right) <= 1


def _axis_relation(
    first_pos: int,
    first_old_size: int,
    first_new_size: int,
    second_pos: int,
    second_old_size: int,
    second_new_size: int,
) -> int | None:
    first_end = first_pos + first_old_size
    second_end = second_pos + second_old_size

    if _close(first_end, second_pos):
        return first_new_size
    if _close(second_end, first_pos):
        return -second_new_size
    if _close(first_pos, second_pos):
        return 0
    if _close(first_end, second_end):
        return first_new_size - second_new_size
    return None


def _reflow_axis(plans: Sequence[LogicalPlan], axis: str) -> list[int]:
    if axis == "x":
        old_positions = [plan.old_x for plan in plans]
        old_sizes = [plan.old_width for plan in plans]
        new_sizes = [plan.new_width for plan in plans]
    else:
        old_positions = [plan.old_y for plan in plans]
        old_sizes = [plan.old_height for plan in plans]
        new_sizes = [plan.new_height for plan in plans]

    edges: list[list[tuple[int, int]]] = [[] for _ in plans]
    for first in range(len(plans)):
        for second in range(first + 1, len(plans)):
            offset = _axis_relation(
                old_positions[first],
                old_sizes[first],
                new_sizes[first],
                old_positions[second],
                old_sizes[second],
                new_sizes[second],
            )
            if offset is None:
                continue
            edges[first].append((second, offset))
            edges[second].append((first, -offset))

    positions: list[int | None] = [None] * len(plans)
    for root in sorted(range(len(plans)), key=lambda index: old_positions[index]):
        if positions[root] is not None:
            continue
        positions[root] = old_positions[root]
        queue: deque[int] = deque([root])
        while queue:
            current = queue.popleft()
            assert positions[current] is not None
            for neighbor, offset in edges[current]:
                if positions[neighbor] is not None:
                    continue
                positions[neighbor] = positions[current] + offset
                queue.append(neighbor)

    resolved = [int(position) for position in positions if position is not None]
    if len(resolved) != len(plans):
        raise ConfigError("Unable to preserve the current monitor positions")
    minimum = min(resolved, default=0)
    return [position - minimum for position in resolved]


def reflow_positions(plans: Sequence[LogicalPlan]) -> None:
    if not plans:
        return
    x_positions = _reflow_axis(plans, "x")
    y_positions = _reflow_axis(plans, "y")
    for plan, x, y in zip(plans, x_positions, y_positions, strict=True):
        plan.x = x
        plan.y = y


def builtin_connectors(state: tuple[Any, ...]) -> list[str]:
    return [
        spec[0]
        for spec, _modes, properties in state[1]
        if properties.get("is-builtin")
    ]


def active_connectors(state: tuple[Any, ...]) -> set[str]:
    return {
        spec[0]
        for _x, _y, _scale, _transform, _primary, specs, _properties in state[2]
        for spec in specs
    }


def current_mode_id(record: MonitorRecord) -> str | None:
    for mode in record.modes:
        if mode[6].get("is-current"):
            return mode[0]
    return None


def config_matches(
    state: tuple[Any, ...],
    target: str,
    virtual_connector: str,
    virtual_mode: str,
    builtin_mode: str,
    scale: float,
) -> bool:
    records = monitor_records(state)
    logical_monitors = state[2]
    active = active_connectors(state)
    builtins = builtin_connectors(state)

    if not active.intersection(builtins):
        return False
    if target == "enable":
        if virtual_connector not in records:
            return False
        virtual_logicals = [
            specs
            for _x, _y, _scale, _transform, _primary, specs, _properties
            in logical_monitors
            if any(spec[0] == virtual_connector for spec in specs)
        ]
        if len(virtual_logicals) != 1:
            return False
        if [spec[0] for spec in virtual_logicals[0]] != [virtual_connector]:
            return False
        if current_mode_id(records[virtual_connector]) != virtual_mode:
            return False
    elif virtual_connector in active:
        return False

    for logical in logical_monitors:
        if not math.isclose(float(logical[2]), scale, abs_tol=1e-6):
            return False

    for connector in active.intersection(builtins):
        if current_mode_id(records[connector]) != builtin_mode:
            return False
    return True


def build_logical_config(
    state: tuple[Any, ...],
    target: str,
    virtual_connector: str,
    virtual_mode: str,
    builtin_mode: str,
    scale: float,
) -> list[tuple[Any, ...]]:
    records = monitor_records(state)
    builtins = builtin_connectors(state)
    if not builtins:
        raise ConfigError("Mutter did not report a built-in display")

    plans: list[LogicalPlan] = []
    for x, y, old_scale, transform, primary, specs, _properties in state[2]:
        connectors = [spec[0] for spec in specs if spec[0] != virtual_connector]
        if not connectors:
            continue

        mode_ids = [
            selected_mode_id(
                records[connector],
                builtin_mode if connector in builtins else None,
            )
            for connector in connectors
        ]
        width, height = mode_size(records[connectors[0]], mode_ids[0], transform)
        plans.append(
            LogicalPlan(
                connectors=connectors,
                mode_ids=mode_ids,
                old_x=int(x),
                old_y=int(y),
                old_width=round(width / float(old_scale)),
                old_height=round(height / float(old_scale)),
                new_width=round(width / scale),
                new_height=round(height / scale),
                transform=int(transform),
                primary=bool(primary),
            )
        )

    planned_connectors = {
        connector for plan in plans for connector in plan.connectors
    }
    if not planned_connectors.intersection(builtins):
        builtin = builtins[0]
        mode_id = selected_mode_id(records[builtin], builtin_mode)
        width, height = mode_size(records[builtin], mode_id, 0)
        plans.append(
            LogicalPlan(
                connectors=[builtin],
                mode_ids=[mode_id],
                old_x=max(
                    (plan.old_x + plan.old_width for plan in plans),
                    default=0,
                ),
                old_y=0,
                old_width=round(width / scale),
                old_height=round(height / scale),
                new_width=round(width / scale),
                new_height=round(height / scale),
                transform=0,
                primary=not any(plan.primary for plan in plans),
            )
        )

    reflow_positions(plans)

    if not any(plan.primary for plan in plans):
        primary = next(
            (
                plan
                for plan in plans
                if set(plan.connectors).intersection(builtins)
            ),
            plans[0],
        )
        primary.primary = True

    config: list[tuple[Any, ...]] = []
    if target == "enable":
        if virtual_connector not in records:
            raise ConfigError(
                f"Virtual display connector {virtual_connector} is unavailable"
            )
        mode_by_id(records[virtual_connector], virtual_mode)
        virtual_width, _virtual_height = mode_size(
            records[virtual_connector], virtual_mode, 0
        )
        virtual_logical_width = round(virtual_width / scale)
        for plan in plans:
            plan.x += virtual_logical_width
        config.append(
            (
                0,
                0,
                scale,
                0,
                False,
                [(virtual_connector, virtual_mode, {})],
            )
        )

    for plan in plans:
        configured_monitors = [
            (connector, mode_id, {})
            for connector, mode_id in zip(
                plan.connectors, plan.mode_ids, strict=True
            )
        ]
        config.append(
            (
                plan.x,
                plan.y,
                scale,
                plan.transform,
                plan.primary,
                configured_monitors,
            )
        )
    return config


