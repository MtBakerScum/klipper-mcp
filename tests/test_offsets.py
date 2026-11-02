import httpx, respx
import klipper_mcp.server as srv
from klipper_mcp import offsets

B = "http://x:7125"
READY = {"result": {"state": "ready", "state_message": "Printer is ready"}}


def _status(main_state=0, job="standby"):
    st = {"extruder_offset_calibration": {"calibration_step": "idle", "extruder1_last_xyz_result": None},
          "machine_state_manager": {"main_state": main_state, "action_code": 0},
          "print_stats": {"state": job, "filename": ""},
          "webhooks": {"state": "ready"}, "display_status": {"progress": 0.0}}
    for i in range(4):
        st[offsets.extruder_obj(i)] = {"extruder_offset": [0.01 * i, -0.02 * i, -0.005 * i],
                                       "nozzle_diameter": 0.4, "nozzle_volume_type": "standard"}
    return st


def _env(m, **kw):
    m.setenv("MOONRAKER_URL", B); m.setenv("MOONRAKER_FALLBACK_URL", "")
    respx.get(f"{B}/printer/info").mock(return_value=httpx.Response(200, json=READY))
    respx.get(url__regex=rf"{B}/printer/objects/query.*").mock(
        return_value=httpx.Response(200, json={"result": {"status": _status(**kw)}}))
    return respx.post(url__regex=rf"{B}/printer/gcode/script.*").mock(
        return_value=httpx.Response(200, json={"result": "ok"}))


def test_scripts_follow_firmware_order():
    s = offsets.start_script([1, 2], clean=True, bed_temp=None).splitlines()
    assert s[0] == "EXTRUDER_OFFSET_ACTION_PRESTART"
    assert s[1:4] == ["EXTRUDER_OFFSET_ACTION_HEAT TOOL_ID=T0", "EXTRUDER_OFFSET_ACTION_AUTO_CLEAN TOOL_ID=T0",
                      "EXTRUDER_OFFSET_ACTION_WAIT_COOL TOOL_ID=T0 TEMP=140"]
    p = offsets.probe_script([1, 2, 3, 4]).splitlines()
    assert p[0] == "EXTRUDER_OFFSET_ACTION_DETECT_PLATE PRESENCE=0" and p[-1] == "EXTRUDER_OFFSET_ACTION_EXIT"
    assert not any("SAVE_RESULT" in l for l in p)
    assert "EXTRUDER_OFFSET_ACTION_SAVE_RESULT FORCE_SAVE=1" in offsets.probe_script([2])
    assert offsets.parse_heads([5]) == "heads are 1-4"


@respx.mock
async def test_get_head_offsets(monkeypatch):
    _env(monkeypatch)
    out = await srv.get_head_offsets()
    assert out["supported"] and out["main_state"] == "IDLE"
    assert out["heads"][1]["offset_mm"] == {"x": 0.01, "y": -0.02, "z": -0.005}


@respx.mock
async def test_start_previews_then_sends(monkeypatch):
    g = _env(monkeypatch)
    prev = await srv.calibrate_head_offsets("start")
    assert prev["confirm_required"] and "PRESTART" in prev["preview"]["gcode"] and not g.called
    out = await srv.calibrate_head_offsets("start", confirm=True)
    assert out["ok"] and "EXTRUDER_OFFSET_ACTION_PRESTART" in str(g.calls.last.request.url)


@respx.mock
async def test_probe_needs_calibration_state(monkeypatch):
    _env(monkeypatch, main_state=0)
    assert (await srv.calibrate_head_offsets("probe"))["error"] == "not_started"


@respx.mock
async def test_start_refused_while_printing(monkeypatch):
    _env(monkeypatch, main_state=1, job="printing")
    assert (await srv.calibrate_head_offsets("start"))["error"] == "not_idle"
