"""Tests for websocket payload routing logic."""

from fastapi.testclient import TestClient

from server.main import app
from tests.server.conftest import ControlledGNSSReader, ControlledIMUReader
from tests.server.helpers import make_gnss, make_imu


def test_gnss_without_vtg_yields_null(gnss_controller: ControlledGNSSReader) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        gnss_controller.message_queue.put(make_gnss(has_vtg=False, vtg_valid=False))
        data = websocket.receive_json()
        assert data["type"] == "gnss"
        assert data["vtg_valid"] is None


def test_gnss_with_valid_vtg_yields_true(gnss_controller: ControlledGNSSReader) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        gnss_controller.message_queue.put(make_gnss(has_vtg=True, vtg_valid=True))
        data = websocket.receive_json()
        assert data["type"] == "gnss"
        assert data["vtg_valid"] is True


def test_gnss_with_invalid_vtg_yields_false(
    gnss_controller: ControlledGNSSReader,
) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        gnss_controller.message_queue.put(make_gnss(has_vtg=True, vtg_valid=False))
        data = websocket.receive_json()
        assert data["type"] == "gnss"
        assert data["vtg_valid"] is False


def test_imu_message_routing(imu_controller: ControlledIMUReader) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        imu_controller.message_queue.put(make_imu())
        data = websocket.receive_json()
        assert data["type"] == "imu"
