from dataclasses import replace
from pathlib import Path

from fastapi import APIRouter
from fastapi.testclient import TestClient
import pytest

from app.auth import create_auth_router
from app.config import load_config
from app.config import ConfigurationError
from app.main import create_app


@pytest.mark.parametrize("visible", [True, False])
def test_placeholder_visibility_preserves_native_paths_without_jwt(visible):
    config = load_config(Path(__file__).resolve().parents[2] / "config.cfg")
    native = APIRouter()
    @native.get("/session")
    async def sessions():
        return [{"id": "ses_native"}]
    client = TestClient(create_app(native, cloud_routers=[create_auth_router(replace(config.auth, token_endpoint_enabled=visible))]))
    response = client.post("/cloud/auth/token")
    assert response.status_code == (501 if visible else 404)
    if visible:
        assert response.json()["error"]["code"] == "AUTH_DISABLED"
    assert client.get("/session").json() == [{"id": "ses_native"}]
    assert client.get("/session", headers={"Authorization": "Bearer reserved-value"}).json() == [{"id": "ses_native"}]


def test_auth_endpoint_cannot_shadow_a_native_path():
    with pytest.raises(ConfigurationError, match="/cloud/auth/"):
        load_config(Path(__file__).resolve().parents[2] / "config.cfg", environ={"CLOUD_AGENT__AUTH__COOKIE_TOKEN_ENDPOINT": "/session"})
