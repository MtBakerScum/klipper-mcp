import httpx, respx
import klipper_mcp.server as srv

B = "http://x:7125"


@respx.mock
async def test_job_filament_uses_actual_total(monkeypatch):
    monkeypatch.setenv("MOONRAKER_URL", B); monkeypatch.setenv("MOONRAKER_FALLBACK_URL", "")
    respx.get(url__regex=rf"{B}/server/history/list.*").mock(return_value=httpx.Response(200, json={"result": {"jobs": [
        {"job_id": "0001", "filename": "a.gcode", "status": "cancelled", "filament_used": 12.0}]}}))
    respx.get(f"{B}/server/files/gcodes/a.gcode").mock(return_value=httpx.Response(200, content=b"M83\nT0\nG1 E10\nT1\nG1 E10\n"))
    out = await srv.get_job_filament()
    assert {t["head"]: t["mm"] for t in out["tools"]} == {1: 10.0, 2: 2.0}
    assert out["status"] == "cancelled"
