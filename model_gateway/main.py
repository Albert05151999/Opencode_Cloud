"""Independent LiteLLM model data plane and configuration control plane."""

import asyncio
import os
import json
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from shared_libs.service import configure_service, run
from shared_libs.logging import TRACE_CONTEXT, bind_request
from model_gateway.src.state import GatewayState, make_router
from model_gateway.src.models import compile_model
from model_gateway.src.auth import RuntimeCredentialMiddleware


def public_error(exc):
    code = getattr(exc, "status_code", 502)
    if not isinstance(code, int) or not 400 <= code <= 599:
        code = 502
    # Provider exceptions can contain keys and request content.
    return JSONResponse(
        {"error": {"message": "Model request failed", "type": type(exc).__name__}}, code
    )


def create_app(config=None, router_factory=make_router):
    app = FastAPI(title="Model gateway")
    config = configure_service(app, "model_gateway", config)
    app.add_middleware(
        RuntimeCredentialMiddleware,
        runtime_token=os.environ.get("MODEL_GATEWAY_TOKEN", ""),
        service_token=config["service_token"],
    )
    state = GatewayState(config["data_root"], router_factory)
    app.state.gateway = state
    lock = asyncio.Lock()
    probe_limit = asyncio.Semaphore(1)

    @app.get("/health/ready")
    async def ready():
        return JSONResponse(state.status(), 200 if state.router else 503)

    @app.get("/internal/v1/config/status")
    async def status():
        return state.status()

    @app.post("/internal/v1/config/validate")
    async def validate(payload: dict):
        try:
            return await asyncio.to_thread(state.validate, payload)
        except (ValueError, TypeError, ImportError) as exc:
            raise HTTPException(422, "Model configuration cannot be loaded") from exc

    @app.post("/internal/v1/config/activate")
    async def activate(payload: dict):
        async with lock:
            try:
                return await asyncio.to_thread(state.activate, payload)
            except (ValueError, TypeError, ImportError) as exc:
                raise HTTPException(
                    422, "Model configuration cannot be loaded"
                ) from exc

    @app.post("/internal/v1/config/rollback")
    async def rollback(payload: dict):
        async with lock:
            return await asyncio.to_thread(state.rollback, payload.get("release_id"))

    @app.get("/v1/models")
    @app.get("/models")
    async def models():
        names = (
            sorted(
                {
                    entry["model_name"]
                    for entry in state.active["configuration"]["model_list"]
                }
            )
            if state.active
            else []
        )
        return {
            "object": "list",
            "data": [
                {"id": name, "object": "model", "owned_by": "cloud"} for name in names
            ],
        }

    methods = {
        "chat/completions": "acompletion",
        "completions": "atext_completion",
        "embeddings": "aembedding",
        "responses": "aresponses",
        "rerank": "arerank",
    }

    @app.post("/v1/{operation:path}")
    async def inference(operation: str, request: Request):
        if operation not in methods:
            raise HTTPException(404, "Unsupported model endpoint")
        router = (
            state.router
        )  # In-flight requests keep their original immutable router.
        if router is None:
            raise HTTPException(503, "No model configuration activated")
        payload = await request.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("model"), str):
            raise HTTPException(422, "model is required")
        context = TRACE_CONTEXT.get()
        entries = state.active["configuration"]["model_list"] if state.active else []
        configured_headers = next(
            (
                entry["litellm_params"].get("extra_headers", {})
                for entry in entries
                if entry["model_name"] == payload["model"]
            ),
            {},
        )
        headers = {**configured_headers, **dict(payload.get("extra_headers") or {})}
        if context.get("trace_id") and context.get("span_id"):
            headers["traceparent"] = f"00-{context['trace_id']}-{context['span_id']}-01"
        for header, field in (
            ("x-cloud-session-id", "session_id"),
            ("x-cloud-message-id", "message_id"),
        ):
            value = request.headers.get(header)
            if (
                value
                and len(value) <= 128
                and all(c.isalnum() or c in "_.:-" for c in value)
            ):
                headers[header] = value
                bind_request(request.scope, **{field: value})
        if headers:
            payload["extra_headers"] = headers
        try:
            result = await getattr(router, methods[operation])(**payload)
            if payload.get("stream"):

                async def events():
                    try:
                        async for chunk in result:
                            value = (
                                chunk.model_dump_json(exclude_none=True)
                                if hasattr(chunk, "model_dump_json")
                                else json.dumps(chunk)
                            )
                            yield "data: " + value + "\n\n"
                        yield "data: [DONE]\n\n"
                    finally:
                        close = getattr(result, "aclose", None)
                        if close:
                            await close()

                return StreamingResponse(
                    events(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
            return (
                result.model_dump(exclude_none=True)
                if hasattr(result, "model_dump")
                else result
            )
        except Exception as exc:
            logging.getLogger("model_gateway").warning(
                "Model request failed: %s", type(exc).__name__
            )
            return public_error(exc)

    @app.post("/cloud/admin/models/test-draft")
    async def test_draft(payload: dict):
        model = dict(payload.get("model", {}))
        saved = (state.active or {}).get("models", {}).get(model.get("id"), {})
        for key in ("api_key", "headers"):
            if model.get(key) == "••••":
                model[key] = saved.get(key)
            elif isinstance(model.get(key), dict):
                model[key] = {
                    k: saved.get(key, {}).get(k) if v == "••••" else v
                    for k, v in model[key].items()
                }
        configuration = compile_model(model)
        async with probe_limit:
            try:
                router = router_factory(configuration)
                await router.acompletion(
                    model=model["id"],
                    messages=[{"role": "user", "content": "Reply with OK."}],
                    max_tokens=32,
                )
                return {
                    "ok": True,
                    "tested": "current_form",
                    "published": False,
                    "status": 200,
                    "error": None,
                }
            except Exception as exc:
                status = getattr(exc, "status_code", 502)
                return {
                    "ok": False,
                    "tested": "current_form",
                    "published": False,
                    "status": status,
                    "error": {
                        400: "model_or_parameters",
                        401: "credentials",
                        403: "model_access",
                        404: "endpoint_or_model",
                        429: "quota_or_rate_limit",
                    }.get(status, "upstream_failure"),
                }

    @app.post("/cloud/admin/models/{model_id}/test")
    async def test_saved(model_id: str):
        if not state.router:
            raise HTTPException(503, "No model configuration activated")
        try:
            await state.router.acompletion(
                model=model_id,
                messages=[{"role": "user", "content": "Reply with OK."}],
                max_tokens=32,
            )
            return {"ok": True}
        except Exception as exc:
            return public_error(exc)

    return app


app = create_app()

if __name__ == "__main__":
    run("model_gateway")
