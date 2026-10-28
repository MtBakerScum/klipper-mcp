import httpx, respx
import klipper_mcp.server as srv
from klipper_mcp import sensors

B = "http://x:7125"


def test_summarize_groups_objects():
    st = {"temperature_sensor cavity": {"temperature": 41.23},
          "extruder1": {"temperature": 220.04, "target": 220, "power": 0.456},
          "fan": {"speed": 0.5}, "fan_generic exhaust": {"speed": 1.0, "rpm": 3000.4},
          "output_pin dragonbreath_filter": {"value": 1.0},
          "filament_switch_sensor e0_runout": {"filament_detected": True, "enabled": True},
          "tmc2240 stepper_x": {"temperature": 55.6},
          "print_task_config": {"filament_type": ["PLA"]}}
    s = sensors.summarize(st)
    assert s["temperatures"]["cavity"] == 41.2
    assert s["heaters"]["extruder1"] == {"temp": 220.0, "target": 220, "power_pct": 46}
    assert s["fans"]["part_fan"]["speed_pct"] == 50 and s["fans"]["exhaust"]["rpm"] == 3000
    assert s["outputs"]["dragonbreath_filter"] == 1.0
    assert s["filament_sensors"]["e0_runout"]["present"] is True
    assert s["driver_temps"]["stepper_x"] == 55.6
    assert "print_task_config" in s["other"]


@respx.mock
async def test_get_printer_sensors_encodes_names(monkeypatch):
    monkeypatch.setenv("MOONRAKER_URL", B); monkeypatch.setenv("MOONRAKER_FALLBACK_URL", "")
    respx.get(f"{B}/printer/objects/list").mock(return_value=httpx.Response(200, json={"result": {"objects": [
        "temperature_sensor cavity", "gcode_move", "fan"]}}))
    q = respx.get(url__regex=rf"{B}/printer/objects/query.*").mock(return_value=httpx.Response(200, json={
        "result": {"status": {"temperature_sensor cavity": {"temperature": 30.0}, "fan": {"speed": 0}}}}))
    out = await srv.get_printer_sensors()
    assert out["temperatures"]["cavity"] == 30.0
    assert "temperature_sensor%20cavity" in str(q.calls[0].request.url) and "gcode_move" not in str(q.calls[0].request.url)
