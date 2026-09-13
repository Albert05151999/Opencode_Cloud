"""Build a standalone client archive; server bundles never invoke this entry."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="0.3.0")
    parser.add_argument(
        "--output", type=Path, default=ROOT.parent / "artifacts/admin_web"
    )
    parser.add_argument("--skip-frontend", action="store_true")
    args = parser.parse_args()
    if not args.version or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        for c in args.version
    ):
        parser.error("version must be a safe path segment")
    if not args.skip_frontend:
        subprocess.run(["npm", "ci"], cwd=ROOT / "frontend", check=True)
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "frontend", check=True)
    if not (ROOT / "frontend/dist/index.html").is_file():
        parser.error("frontend build missing")
    output = args.output / args.version
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"admin_web-{args.version}.tar.gz"
    with tempfile.TemporaryDirectory() as temporary:
        package = Path(temporary) / "admin_web"
        package.mkdir()
        for name in ("local_service", "scripts", "docs", "log"):
            shutil.copytree(
                ROOT / name,
                package / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        shutil.copytree(ROOT / "frontend/dist", package / "frontend/dist")
        for name in ("__init__.py", "module.yaml", "config.schema.json"):
            shutil.copy2(ROOT / name, package / name)
        with tarfile.open(archive, "w:gz") as stream:
            stream.add(package, arcname="admin_web")
    manifest = {
        "module": "admin_web",
        "version": args.version,
        "archive": archive.name,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "runtime": "Python 3.11+; install pinned local_service/requirements.txt",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(archive)


if __name__ == "__main__":
    main()
