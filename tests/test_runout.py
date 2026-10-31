from klipper_mcp import runout


def ptc(**over):
    base = {
        "filament_vendor": ["Snapmaker", "Snapmaker", "Polymaker", "NONE"],
        "filament_type": ["PLA", "PLA", "PETG", "NONE"],
        "filament_sub_type": ["Basic", "Basic", "NONE", "NONE"],
        "filament_color_multi": [{"colors": ["FFFFFF"]}, {"colors": ["FFFFFF"]},
                                 {"colors": ["000000"]}, {"colors": ["FFFFFF"]}],
        "extruder_map_table": [0, 1, 2, 3] + [0] * 28,
        "extruders_used": [True, False, True, False],
        "auto_replenish_filament": True,
        "replenish_ignore_color": False,
    }
    base.update(over)
    return base


FEEDS = {f"extruder{i}": {"module_exist": True, "disable_auto": False, "filament_detected": i != 3,
                          "channel_state": "load_finish" if i != 3 else "idle"} for i in range(4)}
SENS = {runout.sensor_obj(i): {"enabled": True} for i in range(4)}
EXT = {runout.extruder_obj(i): {"nozzle_diameter": 0.4, "nozzle_volume_type": "Standard"} for i in range(4)}


def test_matching_head_is_backup():
    assert runout.find_backup(0, ptc(), FEEDS, SENS, EXT) == 1


def test_no_other_head_with_that_filament():
    assert runout.find_backup(2, ptc(), FEEDS, SENS, EXT) is None
    assert "no other head" in runout.why_no_backup(2, ptc(), FEEDS, SENS, EXT)


def test_colour_must_match_unless_ignored():
    p = ptc(filament_color_multi=[{"colors": ["FFFFFF"]}, {"colors": ["FF0000"]},
                                  {"colors": ["000000"]}, {"colors": ["FFFFFF"]}])
    assert runout.find_backup(0, p, FEEDS, SENS, EXT) is None
    assert "colour" in runout.why_no_backup(0, p, FEEDS, SENS, EXT)
    p["replenish_ignore_color"] = True
    assert runout.find_backup(0, p, FEEDS, SENS, EXT) == 1


def test_nozzle_must_match():
    ext = dict(EXT)
    ext["extruder1"] = {"nozzle_diameter": 0.6, "nozzle_volume_type": "Standard"}
    assert runout.find_backup(0, ptc(), FEEDS, SENS, ext) is None
    assert "0.6 mm" in runout.why_no_backup(0, ptc(), FEEDS, SENS, ext)


def test_backup_needs_filament_ready():
    feeds = dict(FEEDS)
    feeds["extruder1"] = {"module_exist": True, "disable_auto": False, "filament_detected": False,
                          "channel_state": "idle"}
    assert runout.find_backup(0, ptc(), feeds, SENS, EXT) is None


def test_used_heads_mapping_and_fallbacks():
    p = ptc(extruder_map_table=[2, 0, 1, 3] + [0] * 28)
    assert runout.used_heads(p, [0, 1]) == [0, 2]
    assert runout.used_heads(ptc(), None) == [0, 2]
    assert runout.used_heads(ptc(extruders_used=[False] * 4), None) == [0, 1, 2]


def test_report_warns_per_head():
    rep = runout.report(ptc(), FEEDS, SENS, EXT, [0, 2])
    assert [h["backup_head"] for h in rep["heads"]] == [2, None]
    assert len(rep["warnings"]) == 1 and "head 3" in rep["warnings"][0]
    off = runout.report(ptc(auto_replenish_filament=False), FEEDS, SENS, EXT, [0])
    assert off["heads"][0]["backup_head"] is None and "off" in off["heads"][0]["why"]


# --- server wiring ---------------------------------------------------------
import httpx, respx
import klipper_mcp.server as srv

B = "http://x:7125"
OBJS = ["print_task_config", "extruder", "extruder1", "extruder2", "extruder3",
        "filament_motion_sensor e0_filament", "filament_motion_sensor e1_filament",
        "filament_motion_sensor e2_filament", "filament_motion_sensor e3_filament",
        "filament_feed left", "filament_feed right"]


def _status():
    st = {"print_task_config": ptc(), "filament_feed left": {k: FEEDS[k] for k in ("extruder0", "extruder1")},
          "filament_feed right": {k: FEEDS[k] for k in ("extruder2", "extruder3")}}
    st.update(SENS); st.update(EXT)
    return st


def _env(m):
    m.setenv("MOONRAKER_URL", B); m.setenv("MOONRAKER_FALLBACK_URL", "")
    respx.get(f"{B}/printer/objects/list").mock(return_value=httpx.Response(200, json={"result": {"objects": OBJS}}))
    respx.get(url__regex=rf"{B}/printer/objects/query.*").mock(
        return_value=httpx.Response(200, json={"result": {"status": _status()}}))


@respx.mock
async def test_check_runout_backups_from_printer(monkeypatch):
    _env(monkeypatch)
    out = await srv.check_runout_backups()
    assert out["supported"] and out["used_heads_from"] == "printer"
    assert [h["backup_head"] for h in out["heads"]] == [2, None]
    assert out["empty_used_heads"] == []


@respx.mock
async def test_check_runout_backups_local_gcode(monkeypatch, tmp_path):
    _env(monkeypatch)
    g = tmp_path / "j.gcode"; g.write_text("M83\nT1\nG1 X1 E5\nT2\nG1 X2 E5\n")
    out = await srv.check_runout_backups(str(g))
    assert out["used_heads_from"] == "file" and [h["head"] for h in out["heads"]] == [2, 3]


@respx.mock
async def test_not_a_u1(monkeypatch):
    monkeypatch.setenv("MOONRAKER_URL", B); monkeypatch.setenv("MOONRAKER_FALLBACK_URL", "")
    respx.get(f"{B}/printer/objects/list").mock(return_value=httpx.Response(200, json={"result": {"objects": ["extruder"]}}))
    assert (await srv.check_runout_backups()) == {"supported": False}
