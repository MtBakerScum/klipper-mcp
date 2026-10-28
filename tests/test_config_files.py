import httpx, respx
import klipper_mcp.server as srv

B = "http://x:7125"


def _env(m):
    m.setenv("MOONRAKER_URL", B); m.setenv("MOONRAKER_FALLBACK_URL", "")


@respx.mock
async def test_write_previews_then_backs_up_and_uploads(monkeypatch):
    _env(monkeypatch)
    respx.get(f"{B}/server/files/config/extended%2Fklipper%2Fexhaust.cfg").mock(
        return_value=httpx.Response(200, text="[fan_generic exhaust]\npin: PA1\n"))
    copy = respx.post(f"{B}/server/files/copy").mock(return_value=httpx.Response(200, json={"result": {}}))
    up = respx.post(f"{B}/server/files/upload").mock(return_value=httpx.Response(201, json={"result": {}}))
    new = "[fan_generic exhaust]\npin: PA2\n"
    pv = await srv.write_config_file("extended/klipper/exhaust.cfg", new)
    assert "-pin: PA1" in str(pv) and copy.call_count == 0 and up.call_count == 0
    out = await srv.write_config_file("extended/klipper/exhaust.cfg", new, confirm=True)
    assert out["changed"] and out["backup"].startswith("extended/klipper/exhaust.cfg.bak-")
    assert copy.call_count == 1 and up.call_count == 1


async def test_bad_paths_refused():
    assert (await srv.read_config_file("../secrets.cfg"))["error"] == "bad_path"
    assert (await srv.write_config_file("printer.txt", "x"))["error"] == "bad_path"
