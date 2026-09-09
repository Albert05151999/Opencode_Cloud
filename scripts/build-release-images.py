"""Serial release-image build; immutable inputs, safe build context, saved logs."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    version = (ROOT / "VERSION").read_text().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?", version):
        raise ValueError("invalid release version")
    output = ROOT / "artifacts/release"
    output.mkdir(parents=True, exist_ok=True)
    report = {"result": "running", "version": version, "images": {}}
    try:
        environment = dict(os.environ, RUNTIME_IMAGE=f"cloud-agent-runtime:{version}")
        with (output / "runtime-build.log").open("w") as log:
            subprocess.run(["bash", "scripts/verify-runtime-image.sh"], cwd=ROOT, env=environment,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run([sys.executable, "scripts/verify-runtime-search.py"], cwd=ROOT,
                       env=environment, check=True)
        command = ["docker", "build", "-f", "controller/Dockerfile", "-t", f"cloud-agent-controller:{version}"]
        proxy = os.environ.get("HTTPS_PROXY", os.environ.get("https_proxy", ""))
        if proxy.startswith("http://127.0.0.1:"):
            command += ["--network", "host"]
        # Docker's predefined proxy arguments are not persisted in image history.
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"):
            if os.environ.get(key):
                command += ["--build-arg", key]
        command += ["."]
        with (output / "controller-build.log").open("w") as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        versions = dict(line.split("=", 1) for line in (ROOT / "versions.env").read_text().splitlines() if "=" in line)
        gateway = f"ghcr.io/berriai/litellm:v{versions['LITELLM_VERSION']}@{versions['LITELLM_IMAGE_DIGEST']}"
        subprocess.run(["docker", "pull", gateway], check=True)
        for name in ("PROMETHEUS_IMAGE", "GRAFANA_IMAGE"):
            subprocess.run(["docker", "pull", versions[name]], check=True)
        subprocess.run(["docker", "tag", gateway, f"model-gateway:{version}"], check=True)
        subprocess.run([sys.executable, "scripts/verify-litellm.py"], cwd=ROOT,
                       env=dict(os.environ, LITELLM_TEST_IMAGE=f"model-gateway:{version}"), check=True)
        for name in ("cloud-agent-runtime", "cloud-agent-controller", "model-gateway"):
            raw = subprocess.check_output(["docker", "image", "inspect", f"{name}:{version}"])
            item = json.loads(raw)[0]
            report["images"][name] = {"tag": f"{name}:{version}", "id": item["Id"], "size": item["Size"]}
        for script in ("audit-release-images.py", "verify-controller-image.py"):
            subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT,
                           env=dict(os.environ, PYTHONPATH=str(ROOT)), check=True)
        report["result"] = "passed"
    except Exception as exc:
        report.update(result="failed", error=type(exc).__name__)
        raise
    finally:
        (output / "image-build.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
