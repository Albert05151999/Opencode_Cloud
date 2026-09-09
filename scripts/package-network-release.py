"""Repackage verified 0.1.0 offline images with host deployment fixes."""
import configparser
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    source = ROOT / 'artifacts/release/final/cloud-agent-release-0.1.0'
    output = ROOT / 'artifacts/release/network-r1'
    target = output / 'cloud-agent-release-0.1.0-network-r1'
    if target.exists():
        raise RuntimeError('use_a_fresh_output_directory')
    manage = module('network_manage', ROOT / 'deploy/manage.py')
    packaging = module('network_packaging', ROOT / 'scripts/package-release.py')
    manage.verify_checksums(source)
    # Copy only manifest-listed files: exclude local caches and untracked secrets.
    for line in (source / 'checksums.sha256').read_text().splitlines():
        _, relative = line.split('  ', 1)
        packaging.copy(source / relative, target / relative)
    for relative in ('deploy/manage.py', 'deploy/doctor.py', 'scripts/sse-chat.py'):
        packaging.copy(ROOT / relative, target / relative)
    # A distributable client defaults to localhost; this workspace uses the user's server.
    client = target / 'scripts/sse-chat.py'
    client.write_text(client.read_text(encoding='utf-8').replace(
        'http://106.52.221.61:18080', 'http://127.0.0.1:18080').replace(
        '已验证的服务器 API；其他服务器可通过 --base-url 指定地址。',
        '远端使用 --base-url http://服务器IP:18080 指定地址。'), encoding='utf-8')
    packaging.copy(ROOT / 'docs/network-release-readme.md', target / 'README.md')
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(target / 'config/config.cfg')
    cfg['platform'].update(host='0.0.0.0', port='18080')
    with (target / 'config/config.cfg').open('w') as stream:
        cfg.write(stream)
    revision = {'application_version': '0.1.0', 'deployment_revision': 'network-r1',
                'base_manifest_sha256': digest(source / 'checksums.sha256'),
                'application_images_rebuilt': False}
    (target / 'deployment-revision.json').write_text(json.dumps(revision, indent=2) + '\n')
    assert (target / 'release-images.json').read_bytes() == (source / 'release-images.json').read_bytes()
    audit = module('network_audit', ROOT / 'scripts/audit-release-images.py')
    secret_values = [value.encode() for value in audit.parse_env_file(ROOT / 'deploy/.env')]
    for path in target.rglob('*'):
        if path.is_file() and path.relative_to(target).parts[0] != 'images':
            if any(value in path.read_bytes() for value in secret_values):
                raise RuntimeError('provider_secret_in_release_file')
    packaging.checksums(target)
    manage.verify_checksums(target)
    archive_path = output / (target.name + '.zip')
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(target.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(output))
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
    report = {**revision, 'zip': str(archive_path), 'bytes': archive_path.stat().st_size,
              'sha256': digest(archive_path), 'base_and_new_checksums': 'passed', 'zip_crc': 'passed'}
    (output / 'package-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
