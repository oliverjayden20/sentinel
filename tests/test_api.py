from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def build_test_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SENTINEL_DATABASE_FILE", str(tmp_path / "sentinel-test.db"))
    monkeypatch.setenv("SENTINEL_DATA_FILE", str(tmp_path / "services.json"))
    monkeypatch.setenv("SENTINEL_LOG_FILE", str(tmp_path / "system.log"))
    monkeypatch.setenv("SENTINEL_MONITOR_INTERVAL_SECONDS", "30")
    (tmp_path / "services.json").write_text("[]\n", encoding="utf-8")
    get_settings.cache_clear()
    return TestClient(create_app(start_monitor=False))


def test_service_crud_flow(tmp_path, monkeypatch):
    with build_test_client(tmp_path, monkeypatch) as client:
        create_response = client.post(
            "/api/services",
            json={
                "name": "Example",
                "url": "https://example.com",
                "enabled": True,
            },
        )
        assert create_response.status_code == 201
        service = create_response.json()
        assert service["name"] == "Example"
        assert service["status"] == "unknown"
        assert service["uptime_percentage"] is None

        list_response = client.get("/api/services")
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1

        update_response = client.patch(
            f"/api/services/{service['id']}",
            json={"name": "Example API", "enabled": False},
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Example API"
        assert update_response.json()["enabled"] is False

        delete_response = client.delete(f"/api/services/{service['id']}")
        assert delete_response.status_code == 204

        missing_response = client.get(f"/api/services/{service['id']}")
        assert missing_response.status_code == 404


def test_validation_rejects_bad_service_payload(tmp_path, monkeypatch):
    with build_test_client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/services",
            json={"name": " ", "url": "not-a-url"},
        )
        assert response.status_code == 422


def test_service_check_history_endpoint(tmp_path, monkeypatch):
    with build_test_client(tmp_path, monkeypatch) as client:
        service = client.post(
            "/api/services",
            json={"name": "Example", "url": "https://example.com"},
        ).json()

        response = client.get(f"/api/services/{service['id']}/checks")
        assert response.status_code == 200
        assert response.json() == []
