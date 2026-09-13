"""Destructive VM restart persistence acceptance against an explicit deployment."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

DEFAULT_LABCTL = "/Volumes/Lee_brain/cloud-acceptance/labctl"
DEFAULT_ACCEPTANCE_REPORT = "artifacts/verification/server-acceptance-real.json"
DEFAULT_OUTPUT = "artifacts/verification/restart-persistence.json"
DEFAULT_API_BASE_URL = "http://192.168.1.152:18080"
RELEASE_ENV = "/srv/cloud-release/release-0.3.0/.env"


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance-report", type=Path, default=Path(DEFAULT_ACCEPTANCE_REPORT))
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT))
    parser.add_argument("--labctl", default=os.environ.get("LABCTL", DEFAULT_LABCTL))
    parser.add_argument("--api-base-url", default=os.environ.get("API_BASE_URL", DEFAULT_API_BASE_URL))
    parser.add_argument(
        "--stub-evidence-url",
        default=os.environ.get("STUB_EVIDENCE_URL"),
        help="Optional protocol-stub evidence endpoint; omit for real-provider runs",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = arguments(argv)
    import httpx

    def shell(*command):
        return subprocess.check_output(
            [args.labctl, "shell", "server", *command],
            stderr=subprocess.PIPE,
            text=True,
        )

    # Read only the credential this test needs. Never persist or print it.
    admin_token = shell("sudo", "sed", "-n", "s/^ADMIN_TOKEN=//p", RELEASE_ENV).strip()
    if not admin_token or "\n" in admin_token:
        raise RuntimeError("Deployment ADMIN_TOKEN is missing or invalid")

    report = json.loads(args.acceptance_report.read_text())
    session_id = report["session_id"]
    agent_id = report["run_id"]
    native = {"x-cloud-agent-id": agent_id, "x-cloud-username": "acceptance-user"}
    output = {
        "scope": {
            "vm_restart": True,
            "persistence_snapshot": True,
            "post_restart_tool_call": True,
            "protocol_stub_evidence": bool(args.stub_evidence_url),
        },
        "session_id": session_id,
        "agent_id": agent_id,
        "sandbox_id": report["sandbox_id"],
        "result": "running",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(output, indent=2) + "\n")

    def redact_error(error):
        message = str(error)
        secrets = [admin_token]
        for name, value in os.environ.items():
            if value and any(word in name.upper() for word in ("TOKEN", "KEY", "SECRET", "PASSWORD")):
                secrets.append(value)
        for secret in sorted(set(secrets), key=len, reverse=True):
            message = message.replace(secret, "[REDACTED]")
        return message[:2000]

    client = httpx.Client(
        base_url=args.api_base_url,
        headers={"Authorization": "Bearer " + admin_token},
        timeout=180,
        trust_env=False,
    )

    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response

    params = {
        "agent_id": agent_id,
        "username": "acceptance-user",
        "session_id": session_id,
        "path": "acceptance.txt",
    }

    def snapshot():
        messages = request("GET", f"/session/{session_id}/message", headers=native).json()
        file_content = request("GET", "/cloud/files/download", params=params).content
        agent = request("GET", f"/cloud/admin/agents/{agent_id}/effective-config").json()
        jobs = {
            step["job_id"]: request("GET", "/cloud/admin/jobs/" + step["job_id"]).json()["status"]
            for step in report["steps"]
            if "job_id" in step
        }
        return {
            "message_count": len(messages),
            "message_sha256": hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest(),
            "contains_5050": "5050" in json.dumps(messages),
            "completed_tool_count": sum(
                part.get("type") == "tool" and part.get("state", {}).get("status") == "completed"
                for message in messages
                for part in message.get("parts", [])
            ),
            "file_sha256": hashlib.sha256(file_content).hexdigest(),
            "agent_active_version": agent["active_version"],
            "jobs": jobs,
            "model_catalog_revision": request("GET", "/cloud/admin/models").json()["revision"],
        }

    try:
        output["before"] = snapshot()
        save()
        subprocess.run([args.labctl, "stop", "server"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(
            [args.labctl, "start", "server", "--tty=false"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 240
        healthy = []
        while time.monotonic() < deadline:
            try:
                rows = shell("sudo", "docker", "ps", "--format", "{{.Names}}|{{.Status}}").splitlines()
                healthy = [row for row in rows if "(healthy)" in row]
                if len(healthy) >= 7 and client.get("/cloud/health", timeout=5).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(3)
        else:
            raise AssertionError("Services did not recover automatically")
        output["automatic_service_recovery"] = healthy
        output["docker_systemd_active"] = shell("systemctl", "is-active", "docker").strip()
        save()
        output["after"] = snapshot()
        assert output["before"] == output["after"], "Persistent snapshot changed"
        save()
        request(
            "POST",
            f"/session/{session_id}/message",
            headers=native,
            json={"parts": [{"type": "text", "text": "Run Python again in bash: print(sum(range(1,101))). Report actual result after reboot."}]},
        )
        output["after_new_tool"] = snapshot()
        assert output["after_new_tool"]["completed_tool_count"] > output["before"]["completed_tool_count"]
        assert output["after_new_tool"]["file_sha256"] == output["before"]["file_sha256"]
        if args.stub_evidence_url:
            stub = httpx.get(args.stub_evidence_url, timeout=30, trust_env=False)
            stub.raise_for_status()
            output["protocol_stub_evidence"] = stub.json()
            assert output["protocol_stub_evidence"]["tool_calls"] >= 1
        output["result"] = "passed"
        save()
        print("restart persistence passed")
    except Exception as error:
        output["result"] = "failed"
        output["error"] = redact_error(error)
        save()
        raise
    finally:
        client.close()


if __name__ == "__main__":
    main()
