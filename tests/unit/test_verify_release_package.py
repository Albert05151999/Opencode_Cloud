import importlib.util
import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify-release-package.py"
SPEC = importlib.util.spec_from_file_location("verify_release_package", SCRIPT)
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def make_zip(path, names):
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "x")


def test_zip_requires_one_release_root(tmp_path):
    package = tmp_path / "release.zip"
    make_zip(package, ["cloud-agent-release-1/VERSION", "cloud-agent-release-1/deploy/install.sh"])
    assert verify.validate_zip(package) == "cloud-agent-release-1"
    make_zip(package, ["one/file", "two/file"])
    with pytest.raises(verify.VerificationError, match="zip_root_invalid"):
        verify.validate_zip(package)


def test_zip_rejects_traversal(tmp_path):
    package = tmp_path / "release.zip"
    make_zip(package, ["cloud-agent-release-1/../../escape"])
    with pytest.raises(verify.VerificationError, match="zip_path_unsafe"):
        verify.validate_zip(package)


def test_env_archive_is_memory_only_and_mode_0600():
    payload = b"API_KEY=test-secret\n"
    archive = verify.env_archive(payload)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        member = stream.getmember("provider.env")
        assert stat.S_IMODE(member.mode) == 0o600
        assert stream.extractfile(member).read() == payload
