#!/usr/bin/env python3
"""Run the stage-16 file API gate with real isolated sandboxes."""

from __future__ import annotations

import asyncio
import atexit
import hashlib
import json
import shutil
import zipfile
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import docker
import httpx

from app.config import load_config
from app.files import create_files_router
from app.gateway import create_gateway_router
from app.main import create_app
from app.metrics import PlatformMetrics
from app.registry import Registry
from app.sandbox import LocalDockerBackend
from app.workspace import WorkspaceManager


PROJECT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path("/tmp/cloud-agent-stage16-verification")
REPORT = PROJECT / "artifacts" / "files" / "report.json"
INSTANCE = "stage16-verification"


def make_xlsx() -> bytes:
    """Create a minimal standards-compliant XLSX without host-side Excel packages."""

    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Verification" sheetId="1" r:id="rId1"/></sheets></workbook>""",
        "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        "xl/worksheets/sheet1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="inlineStr"><is><t>stage16</t></is></c><c r="B1"><v>42</v></c></row>
</sheetData></worksheet>""",
    }
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def remove_instance_containers(client: docker.DockerClient) -> None:
    filters = {"label": f"cloud.platform_instance={INSTANCE}"}
    for container in client.containers.list(all=True, filters=filters):
        container.reload()
        labels = container.attrs.get("Config", {}).get("Labels") or {}
        if labels.get("cloud.platform_instance") != INSTANCE:
            raise RuntimeError(f"refusing to remove non-{INSTANCE} container {container.id}")
        container.remove(force=True)


def remove_test_root() -> None:
    if not TEST_ROOT.exists():
        return
    resolved = TEST_ROOT.resolve(strict=True)
    if resolved != TEST_ROOT:
        raise RuntimeError(f"refusing to remove unexpected test root {resolved}")
    shutil.rmtree(resolved)


def prepare_agent() -> Path:
    target = TEST_ROOT / "agents" / "agent-data"
    shutil.copytree(PROJECT / "agents" / "agent-data", target)
    return TEST_ROOT / "agents"


async def verify() -> dict[str, object]:
    docker_client = docker.from_env()
    docker_client.ping()
    remove_instance_containers(docker_client)
    remove_test_root()
    TEST_ROOT.mkdir(parents=True)
    agents_root = prepare_agent()

    def cleanup() -> None:
        remove_instance_containers(docker_client)
        remove_test_root()

    atexit.register(cleanup)
    config = load_config(PROJECT / "config.cfg")
    config = replace(config, platform=replace(config.platform, instance_id=INSTANCE))
    registry = Registry(TEST_ROOT / "platform.db")
    registry.initialize()
    workspaces = WorkspaceManager(
        TEST_ROOT / "workspaces", TEST_ROOT / "state",
        runtime_uid=10001, runtime_gid=10001,
    )
    metrics = PlatformMetrics()
    sandboxes = LocalDockerBackend(
        config, registry, workspaces, agents_root, client=docker_client, metrics=metrics
    )
    alice, bob = await asyncio.gather(
        sandboxes.acquire("agent-data", "alice"),
        sandboxes.acquire("agent-data", "bob"),
    )

    upstream = httpx.AsyncClient(trust_env=False, timeout=20)
    files_router = create_files_router(config.storage, workspaces, metrics=metrics)
    gateway_router = create_gateway_router(registry, sandboxes, upstream, metrics=metrics)
    app = create_app(gateway_router, cloud_routers=[files_router], metrics=metrics)
    paths = [getattr(route, "path", "") for route in app.routes]
    assert paths.index("/cloud/files/upload") < paths.index("/{native_path:path}")

    payload = make_xlsx()
    expected_hash = hashlib.sha256(payload).hexdigest()
    relative_path = "input/sample.xlsx"
    session_id = "session-X"
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://files.test") as api:
            uploaded = await api.post(
                "/cloud/files/upload",
                data={
                    "agent_id": "agent-data",
                    "username": "alice",
                    "session_id": session_id,
                    "relative_path": relative_path,
                },
                files={
                    "file": (
                        "sample.xlsx", payload,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
            assert uploaded.status_code == 200, uploaded.text
            upload_result = uploaded.json()
            expected_container_path = f"/workspace/sessions/{session_id}/{relative_path}"
            assert upload_result == {
                "ok": True,
                "path": expected_container_path,
                "size": len(payload),
                "sha256": expected_hash,
            }

            alice_container = docker_client.containers.get(alice.container_id)
            code = (
                "import openpyxl; "
                f"w=openpyxl.load_workbook({expected_container_path!r}, read_only=True, data_only=True); "
                "s=w['Verification']; assert s['A1'].value == 'stage16'; assert s['B1'].value == 42; "
                "print('xlsx-cell-ok')"
            )
            cell_check = await asyncio.to_thread(
                alice_container.exec_run, ["python3", "-c", code]
            )
            assert cell_check.exit_code == 0, cell_check.output.decode(errors="replace")

            query = {
                "agent_id": "agent-data",
                "username": "alice",
                "session_id": session_id,
                "path": relative_path,
            }
            downloaded = await api.get("/cloud/files/download", params=query)
            assert downloaded.status_code == 200, downloaded.text
            assert hashlib.sha256(downloaded.content).hexdigest() == expected_hash
            assert int(downloaded.headers["content-length"]) == len(payload)
            assert "attachment" in downloaded.headers["content-disposition"]

            listing = await api.get(
                "/cloud/files/list",
                params={
                    "agent_id": "agent-data", "username": "alice",
                    "session_id": session_id, "path": "input",
                },
            )
            assert listing.status_code == 200, listing.text
            entries = listing.json()["entries"]
            entry = next(item for item in entries if item["name"] == "sample.xlsx")
            assert entry["type"] == "file" and entry["size"] == len(payload)
            assert isinstance(entry["mtime"], str) and entry["mtime"]

            bob_query = dict(query, username="bob")
            bob_download = await api.get("/cloud/files/download", params=bob_query)
            assert bob_download.status_code == 404, bob_download.text

            traversal = await api.get(
                "/cloud/files/download", params=dict(query, path="../outside/secret.txt")
            )
            assert traversal.status_code == 400, traversal.text
            traversal_upload = await api.post(
                "/cloud/files/upload",
                data={
                    "agent_id": "agent-data", "username": "alice",
                    "session_id": session_id, "relative_path": "../escape.xlsx",
                },
                files={"file": ("escape.xlsx", payload)},
            )
            assert traversal_upload.status_code == 400, traversal_upload.text

            outside = TEST_ROOT / "outside"
            outside.mkdir()
            (outside / "secret.txt").write_text("must-not-leak", encoding="utf-8")
            session_root = (
                TEST_ROOT / "workspaces" / "agent-data" / "alice" /
                "sessions" / session_id
            )
            (session_root / "escape").symlink_to(outside, target_is_directory=True)
            symlink_escape = await api.get(
                "/cloud/files/download", params=dict(query, path="escape/secret.txt")
            )
            assert symlink_escape.status_code == 400, symlink_escape.text

        samples = metrics.registry
        assert samples.get_sample_value("sandbox_create_total") == 2
        assert samples.get_sample_value("sandbox_starting") == 0
        assert samples.get_sample_value("sandbox_active") == 2
        assert samples.get_sample_value("workspace_upload_bytes_total") == len(payload)
        assert samples.get_sample_value("workspace_download_bytes_total") == len(payload)
        assert samples.get_sample_value("cloud_http_requests_total", {"method": "POST", "route": "/cloud/files/upload", "status": "200"}) == 1
        metrics_dir = PROJECT / "artifacts/metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (metrics_dir / "controller.prom").write_bytes(metrics.render())
        (metrics_dir / "report.json").write_text(json.dumps({"result": "passed", "sandbox_creates": 2, "upload_bytes": len(payload), "download_bytes": len(payload), "http_uploads": 1}, indent=2) + "\n")
        report = {
            "result": "passed",
            "instance_id": INSTANCE,
            "sandbox_count": 2,
            "alice_container_id": alice.container_id,
            "bob_container_id": bob.container_id,
            "uploaded_path": upload_result["path"],
            "size": len(payload),
            "sha256": expected_hash,
            "xlsx_cells": {"A1": "stage16", "B1": 42},
            "list_entry": entry,
            "bob_download_status": bob_download.status_code,
            "traversal_download_status": traversal.status_code,
            "traversal_upload_status": traversal_upload.status_code,
            "symlink_escape_status": symlink_escape.status_code,
            "files_router_precedes_gateway_catch_all": True,
            "checks": [
                "multipart XLSX upload returned container path, size, and SHA-256",
                "Alice sandbox read expected XLSX cells with openpyxl",
                "download SHA-256 matched upload SHA-256",
                "file list returned name, type, size, and mtime metadata",
                "Bob could not download Alice's relative session path",
                "traversal and symlink escape requests failed safely",
            ],
        }
    finally:
        await upstream.aclose()

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    cleanup()
    atexit.unregister(cleanup)
    return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(verify()), indent=2))
