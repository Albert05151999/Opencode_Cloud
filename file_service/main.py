"""Independent workspace/file service. Owns filesystem allocation and cleanup."""

from __future__ import annotations

import os
import asyncio
import hashlib
import shutil
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from file_service.files import create_files_router
from file_service.coordination import FileCoordination
from file_service.workspace import WorkspaceManager
from shared_libs.config_models import StorageConfig
from shared_libs.service import configure_service, run, settings
from shared_libs.workspace_paths import WorkspacePathError, validate_identifier


class Allocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str
    username: str
    session_id: str | None = None
    relative_path: str | None = None


def create_app(config=None, workspaces=None):
    config = config or settings("file_service")
    values = config.get("settings", {})
    storage = StorageConfig(
        os.environ.get(
            "WORKSPACE_ROOT",
            values.get("workspace_root", str(Path(config["data_root"]) / "workspaces")),
        ),
        os.environ.get(
            "STATE_ROOT",
            values.get("state_root", str(Path(config["data_root"]) / "state")),
        ),
        int(values.get("max_upload_mb", 100)),
        int(values.get("max_user_workspace_gb", 10)),
    )
    manager = workspaces or WorkspaceManager(
        storage.workspace_root,
        storage.state_root,
        runtime_uid=values.get("runtime_uid"),
        runtime_gid=values.get("runtime_gid"),
    )
    coordination = FileCoordination(config)

    @asynccontextmanager
    async def lifespan(application):
        try:
            yield
        finally:
            await coordination.aclose()

    application = FastAPI(title="Workspace file service", lifespan=lifespan)
    configure_service(application, "file_service", config)
    application.state.workspaces = manager
    application.state.file_coordination = coordination
    application.include_router(create_files_router(storage, manager))

    @application.exception_handler(WorkspacePathError)
    async def invalid_path(request, exc):
        from starlette.responses import JSONResponse

        return JSONResponse({"detail": str(exc)}, status_code=400)

    @application.get("/health/ready")
    def ready():
        return {"ok": manager.workspace_root.is_dir() and manager.state_root.is_dir()}

    @application.post("/internal/v1/workspaces/allocate")
    async def allocate(body: Allocation):
        async with coordination.guard(body.agent_id):
            await coordination.admission(body.agent_id, body.username)
            layout = manager.ensure_user_layout(body.agent_id, body.username)
            path = None
            if body.session_id:
                path = manager.user_scope(body.agent_id, body.username, body.session_id)
            if body.relative_path:
                path = manager.resolve_user_path(
                    body.agent_id, body.username, body.relative_path, body.session_id
                )
            return {
                "workspace_id": hashlib.sha256(
                    f"{body.agent_id}\0{body.username}".encode()
                ).hexdigest(),
                "layout": {k: str(v) for k, v in asdict(layout).items()},
                "path": str(path) if path else None,
            }

    def remove_user(agent_id, username):
        removed = []
        for root in (manager.workspace_root, manager.state_root):
            target = root / agent_id / username
            if target.is_symlink() or (
                target.exists() and target.resolve() != target.absolute()
            ):
                raise HTTPException(409, "Workspace ownership path changed")
            if target.exists():
                shutil.rmtree(target)
                removed.append(str(target))
        return {"ok": True, "removed": removed}

    @application.post("/internal/v1/workspaces/{agent_id}/{username}/cleanup")
    async def cleanup_user(agent_id: str, username: str, body: dict):
        validate_identifier(username, "username")
        request_id = body.get("request_id")
        payload = {"agent_id": agent_id, "username": username, **body}
        async with coordination.guard(agent_id):
            replay = coordination.replay(request_id, payload)
            if replay is not None:
                return replay
            await coordination.check(
                "/internal/v1/cleanup-authorization",
                agent_id=agent_id,
                username=username,
                request_id=request_id,
                run_id=body.get("run_id"),
            )
            coordination.begin(request_id, payload)
            result = await asyncio.to_thread(remove_user, agent_id, username)
            coordination.finish(request_id, result)
            return result

    @application.delete("/internal/v1/workspaces/{agent_id}/{username}")
    async def delete(
        agent_id: str,
        username: str,
        confirmed: bool = False,
        request_id: str | None = None,
        run_id: str | None = None,
    ):
        if not confirmed:
            raise HTTPException(409, "Explicit cleanup confirmation required")
        return await cleanup_user(
            agent_id, username, {"request_id": request_id, "run_id": run_id}
        )

    def agent_impact(aid):
        validate_identifier(aid, "agent_id")
        entries = []
        for base in (manager.workspace_root, manager.state_root):
            directory = base / aid
            if directory.is_symlink():
                raise HTTPException(409, "Agent directory is a symlink")
            if directory.exists():
                for item in sorted(directory.rglob("*")):
                    if item.is_symlink():
                        raise HTTPException(409, "Agent data contains a symlink")
                    if item.is_file():
                        stat = item.stat()
                        entries.append((str(item), stat.st_size, stat.st_mtime_ns))
        import json

        return {
            "agent_id": aid,
            "files": len(entries),
            "bytes": sum(x[1] for x in entries),
            "fingerprint": hashlib.sha256(json.dumps(entries).encode()).hexdigest(),
        }

    @application.get("/internal/v1/agents/{aid}/deletion-impact")
    async def deletion_impact(aid: str):
        async with coordination.guard(aid):
            return await asyncio.to_thread(agent_impact, aid)

    @application.post("/internal/v1/agents/{aid}/cleanup")
    async def cleanup_agent(aid: str, body: dict):
        request_id = body.get("request_id")
        payload = {"agent_id": aid, **body}
        async with coordination.guard(aid):
            replay = coordination.replay(request_id, payload)
            if replay is not None:
                return replay
            await coordination.check(
                "/internal/v1/cleanup-authorization",
                agent_id=aid,
                request_id=request_id,
            )
            impact = await asyncio.to_thread(agent_impact, aid)
            if (
                not body.get("expected_fingerprint")
                or body["expected_fingerprint"] != impact["fingerprint"]
            ):
                raise HTTPException(409, "Fresh file deletion fingerprint required")
            if body.get("empty_only") and impact["files"]:
                raise HTTPException(409, "Agent files are not empty")
            coordination.begin(request_id, payload)
            for base in (manager.workspace_root, manager.state_root):
                if (base / aid).exists():
                    await asyncio.to_thread(shutil.rmtree, base / aid)
            result = {"ok": True, "removed_files": impact["files"]}
            coordination.finish(request_id, result)
            return result

    return application


app = create_app()

if __name__ == "__main__":
    run("file_service")
