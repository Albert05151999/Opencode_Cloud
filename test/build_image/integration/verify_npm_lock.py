"""Verify the pinned OpenCode npm graph in a disposable Linux directory."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def main():
    lock = json.loads((ROOT / "agent_runtime/image/package-lock.json").read_text())
    version = json.loads((ROOT / "agent_runtime/image/package.json").read_text())["dependencies"]["opencode-ai"]
    assert all(p.get("version") == version and p.get("integrity", "").startswith("sha512-")
               for name, p in lock["packages"].items() if name)
    with tempfile.TemporaryDirectory(prefix="cloud-npm-lock-") as directory:
        work = Path(directory)
        for name in ("package.json", "package-lock.json"):
            shutil.copyfile(ROOT / "agent_runtime/image" / name, work / name)
        subprocess.run(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=work, check=True)
        # The pinned package needs this step to prepare its executable launcher.
        subprocess.run(["node", "postinstall.mjs"], cwd=work / "node_modules/opencode-ai", check=True)
        result = subprocess.run([str(work / "node_modules/.bin/opencode"), "--version"],
                                check=True, capture_output=True, text=True)
        assert result.stdout.strip() == version
    report = {"result": "passed", "opencode": version,
              "locked_packages": len(lock["packages"]) - 1,
              "integrity": "sha512 for every npm package",
              "finding": "Only the pinned OpenCode postinstall runs, during build/verification."}
    output = ROOT / "artifacts/verification/npm-lock-verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
