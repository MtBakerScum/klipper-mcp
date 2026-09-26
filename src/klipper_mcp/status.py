"""Turn a raw /printer/objects/query status dict into one compact, model-friendly summary."""
from __future__ import annotations

# Toolchangers (e.g. Snapmaker U1) expose one Klipper object per tool: extruder, extruder1..N.
# Klipper skips objects that don't exist on single-tool printers, so querying them is harmless.
EXTRUDER_OBJECTS = ["extruder", "extruder1", "extruder2", "extruder3"]
STATUS_OBJECTS = ["webhooks", *EXTRUDER_OBJECTS, "heater_bed", "print_stats", "toolhead",
                  "display_status", "fan", "gcode_move", "virtual_sdcard"]


def _r(v, nd=1):
    return None if v is None else round(float(v), nd)


def _extruder_temps(status: dict) -> dict:
    """actual/target for every extruder object the printer reported; 'extruder' is always present."""
    out = {}
    for name in EXTRUDER_OBJECTS:
        ex = status.get(name)
        if ex or name == "extruder":
            ex = ex or {}
            out[name] = {"actual": _r(ex.get("temperature")), "target": _r(ex.get("target"))}
    return out


def summarize_status(status: dict) -> dict:
    wh = status.get("webhooks") or {}
    th0 = status.get("toolhead") or {}
    active = th0.get("extruder") or "extruder"
    ex = status.get(active) or status.get("extruder") or {}
    bed = status.get("heater_bed") or {}
    ps = status.get("print_stats") or {}
    th = status.get("toolhead") or {}
    ds = status.get("display_status") or {}
    fan = status.get("fan") or {}
    gm = status.get("gcode_move") or {}
    progress = ds.get("progress")
    origin = gm.get("homing_origin") or []
    pos = th.get("position") or []
    return {
        "klippy": {"state": wh.get("state", "unknown"), "message": (wh.get("state_message") or "").strip()},
        "job": {
            "state": ps.get("state"),
            "filename": ps.get("filename") or None,
            "progress_percent": None if progress is None else int(round(float(progress) * 100)),
            "print_duration_s": _r(ps.get("print_duration"), 0),
            "total_duration_s": _r(ps.get("total_duration"), 0),
            "filament_used_mm": _r(ps.get("filament_used"), 0),
        },
        "active_extruder": active,
        "temps": {
            **_extruder_temps(status),
            "bed": {"actual": _r(bed.get("temperature")), "target": _r(bed.get("target"))},
        },
        "pressure_advance_by_extruder": {
            name: (status.get(name) or {}).get("pressure_advance")
            for name in EXTRUDER_OBJECTS if status.get(name)},
        "fan_percent": None if fan.get("speed") is None else int(round(float(fan["speed"]) * 100)),
        "pressure_advance": ex.get("pressure_advance"),
        "z_offset": _r(origin[2], 3) if len(origin) > 2 else None,
        "speed_factor": gm.get("speed_factor"),
        "flow_factor": gm.get("extrude_factor"),
        "position": [round(float(v), 2) for v in pos[:3]],
        "homed_axes": th.get("homed_axes"),
    }
