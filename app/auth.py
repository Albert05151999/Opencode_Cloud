"""Reserved token exchange endpoint; no authentication is enabled in the MVP."""
from fastapi import APIRouter
from starlette.responses import JSONResponse

from app.config import AuthConfig


def create_auth_router(config: AuthConfig) -> APIRouter:
    router = APIRouter()
    if config.token_endpoint_enabled:
        @router.post(config.cookie_token_endpoint)
        async def token():
            return JSONResponse({"error": {"code": "AUTH_DISABLED", "message": "Authentication adapter is not implemented"}}, status_code=501)
    return router
