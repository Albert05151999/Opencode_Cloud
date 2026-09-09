#!/usr/bin/env python3
"""Verify one real model call across controller, sandbox and model-gateway logs."""
import asyncio
import configparser
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import docker
import httpx
from app.registry import Registry

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = "stage32-trace"


def json_lines(value):
    result = []
    for line in value.splitlines():
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                result.append(parsed)
        except ValueError:
            pass
    return result


async def main():
    report = {"result": "running"}
    client = docker.from_env()
    gateway = client.containers.get("deploy-model-gateway-1")
    since = datetime.now(timezone.utc)
    request_id = "trace_" + uuid.uuid4().hex
    message_id = "msg_" + uuid.uuid4().hex
    sentinel = "SECRET_LOG_SENTINEL_" + uuid.uuid4().hex
    process = None
    with tempfile.TemporaryDirectory(prefix="cloud-trace-") as temporary:
        directory = Path(temporary)
        shutil.copytree(ROOT / "agents", directory / "agents")
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(ROOT / "config.cfg")
        parser["platform"]["instance_id"] = INSTANCE
        parser["platform"]["data_root"] = str(directory)
        parser["storage"]["workspace_root"] = str(directory / "workspaces")
        parser["storage"]["state_root"] = str(directory / "state")
        with (directory / "config.cfg").open("w") as handle:
            parser.write(handle)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP) as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        log = (directory / "controller.log").open("wb")
        try:
            process = subprocess.Popen([sys.executable, "-m", "app.main", "--config", str(directory / "config.cfg"),
                "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, stdout=log, stderr=log)
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=600) as api:
                for _ in range(200):
                    if process.poll() is not None:
                        raise RuntimeError("controller startup failed")
                    try:
                        if (await api.get("/cloud/health/ready", timeout=1)).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    raise RuntimeError("controller readiness timeout")
                created = await api.post("/session", json={"_cloud": {"agent_id": "agent-code", "username": "trace-user"}})
                created.raise_for_status()
                session_id = created.json()["id"]
                response = await api.post(f"/session/{session_id}/message",
                    headers={"Authorization": "Bearer " + sentinel, "X-Cloud-Request-ID": request_id},
                    json={"messageID": message_id, "model": {"providerID": "cloud-model-gateway", "modelID": "coding-fast"},
                          "parts": [{"type": "text", "text": "Reply with one short sentence. Test marker: " + sentinel}]})
                response.raise_for_status()
                assert response.headers["x-cloud-request-id"] == request_id
                info = response.json()["info"]
                assert not info.get("error") and info["parentID"] == message_id
                uploaded = await api.post("/cloud/files/upload", data={"agent_id": "agent-code", "username": "trace-user"},
                    files={"file": ("test.bin", sentinel.encode())})
                uploaded.raise_for_status()
            await asyncio.sleep(1)
            process.terminate()
            await asyncio.to_thread(process.wait, timeout=20)
            log.flush()
            controller_text = (directory / "controller.log").read_text()
            controller = json_lines(controller_text)
            assert len(controller) == len(controller_text.splitlines()), "controller emitted non-JSON logs"
            record = Registry(directory / "platform.db").get_sandbox("agent-code", "trace-user")
            sandbox_text = client.containers.get(record.container_id).logs().decode(errors="replace")
            model_text = gateway.logs(since=since).decode(errors="replace")
            sandbox = json_lines(sandbox_text)
            model = json_lines(model_text)
            linked_controller = [x for x in controller if x.get("request_id") == request_id and x.get("message_id") == message_id]
            linked_sandbox = [x for x in sandbox if x.get("session_id") == session_id and x.get("message_id") == message_id]
            linked_model = [x for x in model if x.get("session_id") == session_id and x.get("message_id") == message_id]
            assert linked_controller and linked_sandbox and linked_model, "correlation link missing"
            assert all(x.get("username_hash") and "username" not in x for x in linked_controller)
            combined = controller_text + sandbox_text + model_text
            assert sentinel not in combined, "sensitive payload leaked into logs"
            # Compare configured provider secrets in memory; never serialize them.
            for item in gateway.attrs["Config"].get("Env", []):
                name, _, value = item.partition("=")
                if name.endswith("_API_KEY") and value:
                    assert value not in combined, "configured key leaked into logs"
            report.update(result="passed", request_id=request_id, session_id=session_id, message_id=message_id,
                controller=linked_controller, sandbox=linked_sandbox, model_gateway=linked_model,
                all_controller_lines_json=True, credentials_and_payloads_absent=True)
        except Exception as exc:
            report.update(result="failed", error=f"{type(exc).__name__}: {exc}")
        finally:
            if process and process.poll() is None:
                process.kill()
                await asyncio.to_thread(process.wait)
            log.close()
            for container in client.containers.list(all=True, filters={"label": f"cloud.platform_instance={INSTANCE}"}):
                assert container.labels.get("cloud.platform_instance") == INSTANCE
                container.remove(force=True)
    client.close()
    destination = ROOT / "artifacts/logging/report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return report["result"] != "passed"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
