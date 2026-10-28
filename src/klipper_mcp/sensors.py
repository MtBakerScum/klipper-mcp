"""Group every Klipper object into a readable sensors/fans/outputs summary (tracker #29)."""
from __future__ import annotations


def _r(v, nd=1):
    return round(v, nd) if isinstance(v, (int, float)) else v


def _pct(v):
    return round(v * 100) if isinstance(v, (int, float)) else v


# Object types whose state is worth reading; prefix match on the object's type word.
SENSOR_TYPES = ("temperature_sensor", "temperature_fan", "heater_generic", "heater_bed", "extruder",
                "fan", "fan_generic", "heater_fan", "controller_fan", "output_pin", "pwm_tool",
                "led", "neopixel", "filament_switch_sensor", "filament_motion_sensor",
                "tmc2240", "tmc2209", "tmc5160", "tmc2130", "tmc2660")


def wanted(name: str) -> bool:
    t = name.split(" ", 1)[0]
    if t in SENSOR_TYPES or t.startswith("extruder"):
        return True
    # Snapmaker U1 / paxx extras: purifier, print_task_config, DragonBreath, cavity bits.
    low = name.lower()
    return any(k in low for k in ("purifier", "print_task_config", "dragonbreath", "cavity", "chamber"))


def summarize(status: dict) -> dict:
    temps, heaters, fans, outputs, filament, drivers, other = {}, {}, {}, {}, {}, {}, {}
    for name, st in sorted(status.items()):
        if not isinstance(st, dict):
            continue
        t, _, label = name.partition(" ")
        label = label or t
        if t in ("heater_bed", "heater_generic") or t.startswith("extruder"):
            heaters[label] = {"temp": _r(st.get("temperature")), "target": _r(st.get("target")),
                              "power_pct": _pct(st.get("power"))}
        elif t in ("temperature_sensor",):
            temps[label] = _r(st.get("temperature"))
        elif t == "temperature_fan":
            fans[label] = {"speed_pct": _pct(st.get("speed")), "temp": _r(st.get("temperature")),
                           "target": _r(st.get("target"))}
        elif t in ("fan", "fan_generic", "heater_fan", "controller_fan"):
            row = {"speed_pct": _pct(st.get("speed"))}
            if st.get("rpm") is not None:
                row["rpm"] = _r(st.get("rpm"), 0)
            fans[label if t != "fan" else "part_fan"] = row
        elif t in ("output_pin", "pwm_tool"):
            outputs[label] = _r(st.get("value"), 3)
        elif t in ("led", "neopixel"):
            outputs[f"{t} {label}"] = st.get("color_data")
        elif t in ("filament_switch_sensor", "filament_motion_sensor"):
            filament[label] = {"present": st.get("filament_detected"), "enabled": st.get("enabled")}
        elif t.startswith("tmc"):
            if st.get("temperature") is not None:
                drivers[label] = _r(st.get("temperature"))
        else:
            other[name] = st
    out = {"heaters": heaters, "temperatures": temps, "fans": fans, "outputs": outputs,
           "filament_sensors": filament, "driver_temps": drivers}
    if other:
        out["other"] = other
    return out
