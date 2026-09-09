from fastapi.testclient import TestClient

from app.main import create_app


def test_liveness_endpoint() -> None:
    response = TestClient(create_app()).get("/cloud/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
