from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app, manager

def test_create_server_and_update_openapi(monkeypatch) -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    payload = {
        "name": "openapi-service",
        "source_type": "OPENAPI",
        "backend_url": "https://example.com",
        "target_port": 9100,
        "env_vars": {},
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/servers", json=payload)
        assert response.status_code == 200
        server_id = response.json()["id"]

        async def fake_update(_server):
            return "healthy"

        monkeypatch.setattr(manager, "update_server", fake_update)
        update = client.post(f"/api/v1/servers/{server_id}/update")
        assert update.status_code == 200
        assert update.json()["last_health_status"] == "healthy"
