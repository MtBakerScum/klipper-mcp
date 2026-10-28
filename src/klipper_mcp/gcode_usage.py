"""Per-tool filament used by a job, from its G-code (tracker #35).

Moonraker's history only has the job's TOTAL filament_used (mm, actual, also for cancelled
jobs). Walking the G-code and summing extrusion per tool until the running total reaches that
figure gives each head's share of what was really extruded, not the slicer's split of a
complete print. Grams use the filament_diameter / filament_density lists Orca writes into the
G-code's config block."""
from __future__ import annotations
import math
import re

_TOOL = re.compile(r"^T(\d+)\b")
_E = re.compile(r"\bE(-?\d*\.?\d+)")
_CFG = re.compile(r"^;\s*(filament_diameter|filament_density|filament_settings_id|filament_type)\s*=\s*(.*)$")


def _floats(s: str) -> list[float]:
    out = []
    for p in s.split(","):
        try:
            out.append(float(p.strip().strip('"')))
        except ValueError:
            out.append(float("nan"))
    return out


def per_tool_usage(lines, stop_at_mm: float | None = None) -> dict:
    """lines: iterable of G-code lines. stop_at_mm: the job's actual total (history
    filament_used); extrusion is counted only up to it. Returns per tool mm (and grams when the
    config block is present) plus whether the stop point was reached."""
    relative = True  # Orca writes M83 for the U1; G90/M82 switch to absolute below
    tool = 0
    last_abs = {}
    used: dict[int, float] = {}
    total = 0.0
    reached = False
    cfg: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith(";"):
            m = _CFG.match(line)
            if m:
                cfg[m.group(1)] = m.group(2)
            continue
        code = line.split(";", 1)[0].strip()
        if not code:
            continue
        up = code.upper()
        if up.startswith("M83"):
            relative = True
            continue
        if up.startswith("M82"):
            relative = False
            continue
        if up.startswith("G92"):
            m = _E.search(up)
            if m:
                last_abs[tool] = float(m.group(1))
            continue
        mt = _TOOL.match(up)
        if mt:
            tool = int(mt.group(1))
            continue
        if reached or not (up.startswith("G1") or up.startswith("G0") or up.startswith("G2") or up.startswith("G3")):
            continue
        m = _E.search(up)
        if not m:
            continue
        e = float(m.group(1))
        if relative:
            d = e
        else:
            d = e - last_abs.get(tool, 0.0)
            last_abs[tool] = e
        # Net feed, retracts included: Klipper's print_stats.filament_used is the net change in
        # extruder position, so this matches it.
        if stop_at_mm is not None and d > 0 and total + d >= stop_at_mm:
            d = stop_at_mm - total
            reached = True
        used[tool] = used.get(tool, 0.0) + d
        total += d
    dia = _floats(cfg.get("filament_diameter", ""))
    den = _floats(cfg.get("filament_density", ""))
    names = [n.strip().strip('"') for n in cfg.get("filament_settings_id", "").split(";")] if cfg.get("filament_settings_id") else []
    tools = []
    for t in sorted(used):
        row = {"tool": t, "head": t + 1, "mm": round(used[t], 1)}
        if t < len(dia) and t < len(den) and not math.isnan(dia[t]) and not math.isnan(den[t]):
            area = math.pi * (dia[t] / 2) ** 2
            row["g"] = round(used[t] * area * den[t] / 1000.0, 2)
        if t < len(names) and names[t]:
            row["preset"] = names[t]
        tools.append(row)
    return {"tools": tools, "total_mm": round(total, 1), "stopped_at_actual": reached}
