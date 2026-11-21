"""Upload errors are visible; unimplemented chips are never reported as supported."""

import base64

from fastapi.testclient import TestClient

from circuitos.api.app import app
from circuitos.cosim.firmware import engine_status


def test_firmware_capabilities_report_pending_families():
    client = TestClient(app)
    response = client.get("/api/v1/schematic/firmware/capabilities")
    assert response.status_code == 200
    caps = {c["board"]: c for c in response.json()}
    assert set(caps) == {
        "arduino_uno",
        "arduino_nano",
        "arduino_mega",
        "esp32_devkitc",
        "rpi_pico",
        "rpi_pico2",
    }
    for kind in caps:
        assert caps[kind]["available"] == engine_status(kind)[0]
    assert caps["rpi_pico"]["formats"] == ["uf2", "elf"]
    assert caps["esp32_devkitc"]["formats"] == ["bin"]


def test_firmware_upload_rejects_corruption_and_unsupported_targets():
    client = TestClient(app)
    for board, filename in [("arduino_uno", "bad.hex"), ("esp32_devkitc", "firmware.bin")]:
        r = client.post(
            "/api/v1/schematic/firmware/validate",
            json={
                "board": board,
                "filename": filename,
                "data_base64": base64.b64encode(b"broken").decode(),
            },
        )
        assert r.status_code == 422 and isinstance(r.json()["detail"], str)
