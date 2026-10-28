from klipper_mcp.gcode_usage import per_tool_usage

G = """M83
T0
G1 X1 E10
G1 E-1
G1 E1
T1
G1 X2 E5.5
T0
G1 X3 E4
; filament_diameter = 1.75,1.75
; filament_density = 1.24,1.27
; filament_settings_id = "PLA A";"PETG B"
"""


def test_full_job_per_tool():
    r = per_tool_usage(G.splitlines())
    t = {x["tool"]: x for x in r["tools"]}
    assert t[0]["mm"] == 14.0 and t[1]["mm"] == 5.5
    assert t[0]["preset"] == "PLA A" and abs(t[0]["g"] - 14 * 3.14159 * 0.875 ** 2 * 1.24 / 1000) < 0.01


def test_cancelled_job_stops_at_actual_total():
    r = per_tool_usage(G.splitlines(), stop_at_mm=13.0)
    t = {x["tool"]: x["mm"] for x in r["tools"]}
    assert t == {0: 10.0, 1: 3.0} and r["stopped_at_actual"]


def test_absolute_extrusion():
    r = per_tool_usage(["M82", "G92 E0", "G1 E5", "G1 E8", "T1", "G92 E0", "G1 E2"])
    assert {x["tool"]: x["mm"] for x in r["tools"]} == {0: 8.0, 1: 2.0}
