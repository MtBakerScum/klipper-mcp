import httpx, respx
import klipper_mcp.server as srv

B = "http://x:7125"


def _env(m):
    m.setenv("MOONRAKER_URL", B); m.setenv("MOONRAKER_FALLBACK_URL", "")


@respx.mock
async def test_get_console_drops_temps_and_filters(monkeypatch):
    _env(monkeypatch)
    route = respx.get(url__regex=rf"{B}/server/gcode_store.*").mock(return_value=httpx.Response(200, json={
        "result": {"gcode_store": [
            {"message": "G28", "time": 1.0, "type": "command"},
            {"message": "B:60.0 /60.0 T0:210.0 /210.0", "time": 2.0, "type": "response"},
            {"message": "!! Move out of range: -0.173 10.000 0.200 [0.000]", "time": 3.0, "type": "response"},
            {"message": "// Heat soak: 5 min", "time": 4.0, "type": "response"}]}}))
    out = await srv.get_console()
    assert [l["message"] for l in out["lines"]][0] == "G28" and out["count"] == 3
    assert route.calls.last.request.url.params["count"] == "1000"
    out = await srv.get_console(pattern="out of range")
    assert out["count"] == 1 and out["lines"][0]["time"] == 3.0
    out = await srv.get_console(count=1, include_temps=True)
    assert out["lines"][0]["message"].startswith("// Heat soak")
    assert "error" in await srv.get_console(pattern="(")


@respx.mock
async def test_get_console_drops_duplicate_entries(monkeypatch):
    _env(monkeypatch)
    dup = {"message": "SET_PRINT_PREFERENCES BED_LEVEL=0", "time": 5.0, "type": "command"}
    respx.get(url__regex=rf"{B}/server/gcode_store.*").mock(return_value=httpx.Response(200, json={
        "result": {"gcode_store": [dup, dup, dup, {"message": "G28", "time": 6.0, "type": "command"},
                                   {"message": "G28", "time": 7.0, "type": "command"}]}}))
    out = await srv.get_console()
    assert [(l["time"], l["message"]) for l in out["lines"]] == [
        (5.0, "SET_PRINT_PREFERENCES BED_LEVEL=0"), (6.0, "G28"), (7.0, "G28")]


@respx.mock
async def test_get_power_devices(monkeypatch):
    _env(monkeypatch)
    respx.get(f"{B}/machine/device_power/devices").mock(return_value=httpx.Response(200, json={
        "result": {"devices": [{"device": "exhaust", "status": "on", "locked_while_printing": False,
                                "type": "gpio"}]}}))
    out = await srv.get_power_devices()
    assert out["count"] == 1 and out["devices"][0] == {
        "device": "exhaust", "status": "on", "type": "gpio", "locked_while_printing": False}


@respx.mock
async def test_get_bed_mesh_summary(monkeypatch):
    _env(monkeypatch)
    respx.get(url__regex=rf"{B}/printer/objects/query.*").mock(return_value=httpx.Response(200, json={
        "result": {"status": {"bed_mesh": {
            "profile_name": "default", "mesh_min": [5, 5], "mesh_max": [265, 265],
            "probed_matrix": [[0.0, 0.1, 0.2], [0.0, 0.1, 0.2], [-0.05, 0.05, 0.15]],
            "profiles": {"default": {}}}}}}))
    out = await srv.get_bed_mesh()
    assert out["points"] == "3x3" and out["range"] == 0.25 and out["min"] == -0.05
    assert out["left_mean"] < out["right_mean"]
    assert out["corners"]["back_left"] == -0.05 and out["profiles"] == ["default"]


@respx.mock
async def test_get_bed_mesh_none_loaded(monkeypatch):
    _env(monkeypatch)
    respx.get(url__regex=rf"{B}/printer/objects/query.*").mock(return_value=httpx.Response(200, json={
        "result": {"status": {"bed_mesh": {"profile_name": "", "probed_matrix": [[]], "profiles": {}}}}}))
    out = await srv.get_bed_mesh()
    assert out["loaded"] is False


JPEG = b"\xff\xd8\xff\xe0fakejpeg"


@respx.mock
async def test_get_camera_snapshot_uses_moonraker_webcam_list(monkeypatch):
    _env(monkeypatch)
    respx.get(f"{B}/server/webcams/list").mock(return_value=httpx.Response(200, json={
        "result": {"webcams": [{"name": "U1 Camera", "snapshot_url": "/webcam/?action=snapshot"}]}}))
    snap = respx.get("http://x/webcam/?action=snapshot").mock(
        return_value=httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"}))
    out = await srv.get_camera_snapshot()
    assert snap.called
    img, meta = out
    assert img.data == JPEG and img._mime_type == "image/jpeg"
    assert meta["camera"] == "U1 Camera" and meta["bytes"] == len(JPEG)


@respx.mock
async def test_get_camera_snapshot_falls_back_and_reports(monkeypatch):
    _env(monkeypatch)
    respx.get(f"{B}/server/webcams/list").mock(return_value=httpx.Response(200, json={"result": {"webcams": []}}))
    respx.get("http://x/webcam/?action=snapshot").mock(return_value=httpx.Response(404))
    respx.get("http://x/webcam/snapshot.jpg").mock(
        return_value=httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"}))
    img, meta = await srv.get_camera_snapshot()
    assert meta["url"] == "http://x/webcam/snapshot.jpg"


@respx.mock
async def test_get_camera_snapshot_unknown_camera(monkeypatch):
    _env(monkeypatch)
    respx.get(f"{B}/server/webcams/list").mock(return_value=httpx.Response(200, json={
        "result": {"webcams": [{"name": "U1 Camera", "snapshot_url": "/webcam/?action=snapshot"}]}}))
    out = await srv.get_camera_snapshot("nozzle cam")
    assert "no camera" in out["error"] and out["cameras"] == ["U1 Camera"]
