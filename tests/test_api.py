from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app, manager


def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_openapi_server_creation_and_health_update(monkeypatch) -> None:
    _fresh_db()
    payload = {
        "name": "openapi-service",
        "slug": "openapi-service",
        "source_type": "OPENAPI",
        "backend_url": "https://example.com",
        "env_vars": {},
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/servers", json=payload)
        assert response.status_code == 200
        assert response.json()["slug"] == "openapi-service"
        server_id = response.json()["id"]

        async def fake_update(_server):
            return "healthy"

        monkeypatch.setattr(manager, "update_server", fake_update)
        update = client.post(f"/api/v1/servers/{server_id}/update")
        assert update.status_code == 200
        assert update.json()["last_health_status"] == "healthy"


def test_proxy_route_openapi_server(monkeypatch) -> None:
    """Proxy route forwards requests to the OpenAPI backend_url."""
    _fresh_db()
    payload = {
        "name": "proxy-test",
        "slug": "proxy-test",
        "source_type": "OPENAPI",
        "backend_url": "http://fake-backend",
        "env_vars": {},
    }

    # Simulate the upstream returning a simple JSON response.
    mock_response = httpx.Response(200, json={"openapi": "3.1.0"})

    async def mock_request(self, method, url, **kwargs):
        assert "proxy-test" not in url  # proxy must rewrite to backend
        assert "fake-backend" in url
        return mock_response

    monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

    with TestClient(app) as client:
        client.post("/api/v1/servers", json=payload)
        resp = client.get("/v1/mcp/proxy-test/openapi.json")
        assert resp.status_code == 200


def test_proxy_route_unknown_slug() -> None:
    _fresh_db()
    with TestClient(app) as client:
        resp = client.get("/v1/mcp/does-not-exist/openapi.json")
        assert resp.status_code == 404
