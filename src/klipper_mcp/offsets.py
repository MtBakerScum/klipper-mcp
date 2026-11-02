"""Snapmaker U1 per-head offsets and the offset calibration (tracker #33).

From Snapmaker/u1-klipper (probe_inductance_coil.py, machine_state_manager.py,
lava/xyz_offset_calibration.cfg):
  - each extruder object reports `extruder_offset` [x, y, z]: that head's offset from head 1,
    applied by the firmware as SET_GCODE_OFFSET at every tool change;
  - the EXTRUDER_OFFSET_ACTION_* commands only run in machine main state XYZ_OFFSET_CALIBRATE,
    which EXTRUDER_OFFSET_ACTION_PRESTART enters (only from IDLE) and EXTRUDER_OFFSET_ACTION_EXIT
    leaves;
  - the screen's sequence: PRESTART (bed 55 C, nozzles 140 C, home) -> per head HEAT, AUTO_CLEAN,
    WAIT_COOL -> DETECT_PLATE PRESENCE=0 (the build plate must be OFF: the probe touches the bed's
    reference point) -> PROBE_CALIBRATE per head (saved automatically once all four are done)
    -> EXIT.
"""
from __future__ import annotations

HEADS = 4

MAIN_STATES = {0: "IDLE", 1: "PRINTING", 2: "XYZ_OFFSET_CALIBRATE", 3: "BED_LEVELING",
               4: "FLOW_CALIBRATION", 5: "SHAPER_CALIBRATE", 6: "UPGRADING", 7: "ABNORMAL",
               8: "SCREWS_TILT_ADJUST", 9: "AUTO_LOAD", 10: "AUTO_UNLOAD", 11: "MANUAL_LOAD",
               12: "PARK_POINT_MANUAL_CALIBRATION", 13: "HOMING_ORIGIN_CALIBRATION"}

QUERY = ["extruder_offset_calibration", "machine_state_manager", "print_stats",
         "extruder", "extruder1", "extruder2", "extruder3"]


def extruder_obj(i: int) -> str:
    return "extruder" if i == 0 else f"extruder{i}"


def main_state(status: dict) -> str:
    ms = (status.get("machine_state_manager") or {}).get("main_state")
    if isinstance(ms, int):
        return MAIN_STATES.get(ms, str(ms))
    return str(ms) if ms is not None else "unknown"


def summarize(status: dict) -> dict:
    cal = status.get("extruder_offset_calibration") or {}
    heads = []
    for i in range(HEADS):
        ex = status.get(extruder_obj(i))
        if ex is None:
            continue
        off = ex.get("extruder_offset") or [0, 0, 0]
        last = cal.get(f"{extruder_obj(i)}_last_xyz_result")
        heads.append({"head": i + 1, "tool": f"T{i}",
                      "offset_mm": {"x": round(off[0], 4), "y": round(off[1], 4), "z": round(off[2], 4)},
                      "nozzle_diameter": ex.get("nozzle_diameter"),
                      "nozzle_type": ex.get("nozzle_volume_type"),
                      "probed_this_run": last is not None})
    return {"heads": heads, "reference": "head 1 (offsets are each head's difference from it)",
            "main_state": main_state(status), "calibration_step": cal.get("calibration_step"),
            "job_state": (status.get("print_stats") or {}).get("state")}


def start_script(heads: list[int], clean: bool, bed_temp: int | None) -> str:
    lines = ["EXTRUDER_OFFSET_ACTION_PRESTART"]
    if bed_temp is not None:
        # PRESTART preheats with the macro default (55 C); a different bed temp is set after it.
        lines.append(f"M140 S{int(bed_temp)}")
    for h in heads:
        t = f"T{h - 1}"
        lines.append(f"EXTRUDER_OFFSET_ACTION_HEAT TOOL_ID={t}")
        if clean:
            lines.append(f"EXTRUDER_OFFSET_ACTION_AUTO_CLEAN TOOL_ID={t}")
        lines.append(f"EXTRUDER_OFFSET_ACTION_WAIT_COOL TOOL_ID={t} TEMP=140")
    return "\n".join(lines)


def probe_script(heads: list[int]) -> str:
    lines = ["EXTRUDER_OFFSET_ACTION_DETECT_PLATE PRESENCE=0"]
    lines += [f"EXTRUDER_OFFSET_ACTION_PROBE_CALIBRATE TOOL_ID=T{h - 1}" for h in heads]
    if sorted(heads) != list(range(1, HEADS + 1)):
        # The firmware saves on its own only when all four heads are probed.
        lines.append("EXTRUDER_OFFSET_ACTION_SAVE_RESULT FORCE_SAVE=1")
    lines.append("EXTRUDER_OFFSET_ACTION_EXIT")
    return "\n".join(lines)


def parse_heads(heads: list[int] | None) -> list[int] | str:
    hs = sorted(set(heads)) if heads else list(range(1, HEADS + 1))
    if any(not isinstance(h, int) or h < 1 or h > HEADS for h in hs):
        return f"heads are 1-{HEADS}"
    return hs
