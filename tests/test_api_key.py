from fastapi.testclient import TestClient

from main import create_app


def test_no_api_key_configured_allows_requests(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200
    # Missing required headers -> 400, but not 401
    assert client.get("/retrieve-calendar-file-proxy").status_code != 401


def test_api_key_required_when_configured(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret123")
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200
    assert client.get("/retrieve-calendar-file-proxy").status_code == 401
    assert client.get("/retrieve-calendar-file-proxy", headers={"X-API-Key": "wrong"}).status_code == 401
    response = client.get("/retrieve-calendar-file-proxy", headers={"X-API-Key": "secret123"})
    assert response.status_code != 401
