from klipper_mcp.status import summarize_status, STATUS_OBJECTS

# Real payload from the Pi 2026-09-03, trimmed to the fields we read.
RAW = {
    "webhooks": {"state": "shutdown", "state_message": "Lost communication with MCU 'mcu'\n..."},
    "extruder": {"temperature": 21.99, "target": 0.0, "pressure_advance": 0.032},
    "heater_bed": {"temperature": 21.8, "target": 0.0},
    "print_stats": {"filename": "Body4_PLA_22m1s.gcode", "total_duration": 1475.09,
                    "print_duration": 1345.7, "filament_used": 8311.97, "state": "complete"},
    "toolhead": {"homed_axes": "", "position": [5.0, 290.0, 63.04, 61813.0]},
    "display_status": {"progress": 1.0},
    "fan": {"speed": 0.0},
    "gcode_move": {"speed_factor": 1.0, "extrude_factor": 1.0, "homing_origin": [0.0, 0.0, -0.01, 0.0]},
    "virtual_sdcard": {"progress": 1.0, "is_active": False},
}


def test_summary_shape_and_values():
    s = summarize_status(RAW)
    assert s["klippy"]["state"] == "shutdown"
    assert "MCU" in s["klippy"]["message"]
    assert s["job"]["state"] == "complete"
    assert s["job"]["filename"] == "Body4_PLA_22m1s.gcode"
    assert s["job"]["progress_percent"] == 100
    assert s["temps"]["extruder"] == {"actual": 22.0, "target": 0.0}
    assert s["temps"]["bed"]["actual"] == 21.8
    assert s["fan_percent"] == 0
    assert s["pressure_advance"] == 0.032
    assert s["z_offset"] == -0.01
    assert s["homed_axes"] == ""
    assert s["position"] == [5.0, 290.0, 63.04]


def test_missing_objects_do_not_crash():
    s = summarize_status({})
    assert s["klippy"]["state"] == "unknown"
    assert s["job"]["state"] is None
    assert s["temps"]["extruder"]["actual"] is None


def test_status_objects_include_webhooks():
    assert "webhooks" in STATUS_OBJECTS and "print_stats" in STATUS_OBJECTS


def test_toolchanger_reports_every_tool_and_the_active_one():
    raw = dict(RAW)
    raw["extruder"] = {"temperature": 36.0, "target": 0.0, "pressure_advance": 0.033}
    raw["extruder1"] = {"temperature": 30.0, "target": 0.0, "pressure_advance": 0.02}
    raw["extruder3"] = {"temperature": 255.2, "target": 255.0, "pressure_advance": 0.04}
    raw["toolhead"] = {"homed_axes": "xyz", "position": [1.0, 2.0, 3.0, 0.0], "extruder": "extruder3"}
    s = summarize_status(raw)
    assert s["active_extruder"] == "extruder3"
    assert s["temps"]["extruder3"] == {"actual": 255.2, "target": 255.0}
    assert s["temps"]["extruder"]["actual"] == 36.0
    assert "extruder2" not in s["temps"]
    assert s["pressure_advance"] == 0.04
    assert s["pressure_advance_by_extruder"] == {"extruder": 0.033, "extruder1": 0.02, "extruder3": 0.04}


def test_status_objects_include_all_toolchanger_extruders():
    for n in ("extruder", "extruder1", "extruder2", "extruder3"):
        assert n in STATUS_OBJECTS
