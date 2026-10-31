"""Snapmaker U1 runout backups (tracker #50).

When a head runs out mid-print the U1 firmware (print_task_config.INNER_AUTO_REPLENISH_FILAMENT)
switches to another head only if that head:
  - has filament ready (its feeder reports load_finish, or the feeder module is present, in auto
    mode, sees filament and the head's runout sensor is enabled),
  - has the same nozzle diameter and nozzle volume type (Standard / High Flow),
  - is set to the same filament vendor, type and sub-type (not NONE),
  - and the same colour, unless "replenish_ignore_color" is on (then the nearest colour wins).
Otherwise the print stays paused, the extruder map can't be changed while paused, and RESUME
keeps failing until filament is loaded into the empty head. This module predicts that.
"""
from __future__ import annotations

HEADS = 4


def extruder_obj(i: int) -> str:
    return "extruder" if i == 0 else f"extruder{i}"


def sensor_obj(i: int) -> str:
    return f"filament_motion_sensor e{i}_filament"


def _at(lst, i, default=None):
    return lst[i] if isinstance(lst, list) and 0 <= i < len(lst) else default


def _ident(ptc: dict, i: int) -> tuple:
    return (_at(ptc.get("filament_vendor"), i, "NONE"), _at(ptc.get("filament_type"), i, "NONE"),
            _at(ptc.get("filament_sub_type"), i, "NONE"))


def _label(ptc: dict, i: int) -> str:
    v, t, s = _ident(ptc, i)
    parts = [p for p in (v, t, s) if p and p != "NONE"]
    col = (_at(ptc.get("filament_color_multi"), i, {}) or {}).get("colors") or []
    return (" ".join(parts) or "nothing set") + (f" #{col[0]}" if col else "")


def head_ready(i: int, feeds: dict, sensors: dict) -> bool:
    """Whether head i has filament loaded and ready, by the firmware's own test."""
    f = feeds.get(f"extruder{i}") or {}
    s = sensors.get(sensor_obj(i)) or {}
    if f.get("channel_state") == "load_finish":
        return True
    return bool(f.get("module_exist") and not f.get("disable_auto") and f.get("filament_detected")
                and s.get("enabled"))


def find_backup(i: int, ptc: dict, feeds: dict, sensors: dict, extruders: dict) -> int | None:
    """The head the firmware would switch to when head i runs out, or None."""
    if _ident(ptc, i)[0] == "NONE" and _ident(ptc, i)[1] == "NONE":
        return None
    me = extruders.get(extruder_obj(i)) or {}
    ignore_color = bool(ptc.get("replenish_ignore_color"))
    colour_i = _at(ptc.get("filament_color_multi"), i)
    fallback = None
    for j in range(HEADS):
        if j == i:
            continue
        ex = extruders.get(extruder_obj(j))
        if ex is None:
            continue
        if ex.get("nozzle_diameter") != me.get("nozzle_diameter") or \
                ex.get("nozzle_volume_type") != me.get("nozzle_volume_type"):
            continue
        if not head_ready(j, feeds, sensors):
            continue
        if _ident(ptc, j)[0] == "NONE" or _ident(ptc, j) != _ident(ptc, i):
            continue
        if _at(ptc.get("filament_color_multi"), j) == colour_i:
            return j
        if ignore_color and fallback is None:
            fallback = j
    return fallback


def why_no_backup(i: int, ptc: dict, feeds: dict, sensors: dict, extruders: dict) -> str:
    me = extruders.get(extruder_obj(i)) or {}
    same = [j for j in range(HEADS) if j != i and _ident(ptc, j) == _ident(ptc, i) and _ident(ptc, j)[0] != "NONE"]
    if not same:
        return f"no other head is set to {_label(ptc, i)}"
    reasons = []
    for j in same:
        ex = extruders.get(extruder_obj(j)) or {}
        if ex.get("nozzle_diameter") != me.get("nozzle_diameter"):
            reasons.append(f"head {j + 1} has a {ex.get('nozzle_diameter')} mm nozzle")
        elif ex.get("nozzle_volume_type") != me.get("nozzle_volume_type"):
            reasons.append(f"head {j + 1} has a {ex.get('nozzle_volume_type')} nozzle")
        elif not head_ready(j, feeds, sensors):
            reasons.append(f"head {j + 1} has no filament ready")
        else:
            reasons.append(f"head {j + 1} is a different colour (replenish_ignore_color is off)")
    return "; ".join(reasons)


def used_heads(ptc: dict, tools: list[int] | None) -> list[int]:
    """Physical heads (0-based) a job uses. tools: the job's logical tool numbers (T0..), mapped
    through the printer's extruder map; else print_task_config's extruders_used; else every head
    that has filament set."""
    if tools:
        table = ptc.get("extruder_map_table") or list(range(HEADS))
        return sorted({_at(table, t, t) for t in tools if isinstance(t, int) and 0 <= _at(table, t, t) < HEADS})
    used = [i for i, u in enumerate(ptc.get("extruders_used") or []) if u]
    if used:
        return used
    return [i for i in range(HEADS) if _ident(ptc, i)[1] != "NONE"]


def report(ptc: dict, feeds: dict, sensors: dict, extruders: dict, heads: list[int]) -> dict:
    auto = ptc.get("auto_replenish_filament", True)
    rows, warnings = [], []
    for i in heads:
        b = find_backup(i, ptc, feeds, sensors, extruders) if auto else None
        row = {"head": i + 1, "filament": _label(ptc, i), "loaded": head_ready(i, feeds, sensors),
               "backup_head": None if b is None else b + 1}
        if b is None:
            row["why"] = "auto-refill is off on the printer" if not auto else why_no_backup(i, ptc, feeds, sensors, extruders)
            warnings.append(f"head {i + 1} ({_label(ptc, i)}) has no backup: if it runs out the print "
                            f"pauses and can only resume after filament is loaded into head {i + 1} "
                            f"({row['why']})")
        rows.append(row)
    return {"auto_replenish": auto, "ignore_color": bool(ptc.get("replenish_ignore_color")),
            "heads": rows, "warnings": warnings}
