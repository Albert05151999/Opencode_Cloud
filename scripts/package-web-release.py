"""Build allowlisted server/local Web bundles; execute under Linux with Docker."""
import configparser
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, help='Fresh output directory; defaults to artifacts/release/web-v<VERSION>')
    parser.add_argument('--zip-only', action='store_true')
    parser.add_argument('--stage-only', action='store_true', help='Stage and validate files for upgrade testing before creating final ZIPs')
    parser.add_argument('--refresh', action='store_true', help='Verify the previous stage, then update it from current sources and controller image')
    args = parser.parse_args()
    version = (ROOT / 'VERSION').read_text().strip()
    packaging = module('web_packaging', 'scripts/package-release.py')
    manage = module('web_manage', 'deploy/manage.py')
    audit = module('web_audit', 'scripts/audit-release-images.py')
    output = args.output_dir or ROOT / f'artifacts/release/web-v{version}'
    target = output / f'cloud-agent-release-{version}'
    local = output / f'cloud-agent-web-{version}'
    if not args.zip_only:
        if args.refresh:
            manage.verify_checksums(target)
            manage.verify_checksums(local)
        elif target.exists() or local.exists():
            raise RuntimeError('Use --output-dir for a fresh stage, or --refresh for an unchanged image set')
        # Build from checked-in sources and the current image build report.
        # No previous release archive or private deployment state is required.
        packaging.stage(target)
        for relative in ('VERSION', '02_api_contract.md', '04-user_manager_web.md', 'scripts/sse-chat.py',
                         'deploy/manage.py', 'deploy/doctor.py', 'deploy/smoke.py'):
            packaging.copy(ROOT / relative, target / relative)
        packaging.copy(ROOT / 'docs/web-readme.md', target / 'README.md')
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read(target / 'config/config.cfg')
        cfg['platform'].update(host='0.0.0.0', port='18080')
        with (target / 'config/config.cfg').open('w') as stream:
            cfg.write(stream)
        for relative in ('VERSION', 'start-web.ps1', 'scripts/start-web.py', 'scripts/sse-chat.py',
                         'local_web/__init__.py', 'local_web/server.py', 'local_web/importer.py', 'local_web/runtime.py',
                         'local_web/requirements.txt', 'app/__init__.py', 'app/management.py',
                         '02_api_contract.md', '04-user_manager_web.md'):
            packaging.copy(ROOT / relative, local / relative)
        packaging.copy(ROOT / 'docs/web-readme.md', local / 'README.md')
        for name in (f'upgrade-{version}-verification.json', 'session-binding-verification.json', f'release-{version}-assessment.md', 'final-assessment.md', 'controller-openapi.json', 'runtime-verification.json',
                     'upgrade-verification.json', 'windows-companion-verification.json',
                     'real-chat-desktop.png', 'real-admin-desktop.png'):
            path = ROOT / 'artifacts/web' / name
            if path.is_file():
                packaging.copy(path, target / 'artifacts/web' / name)
                packaging.copy(path, local / 'artifacts/web' / name)
        for path in (ROOT / 'web/dist').rglob('*'):
            if path.is_file():
                packaging.copy(path, local / path.relative_to(ROOT))
        for path in (local / 'web/dist').rglob('*'):
            if path.is_file() and not (ROOT / path.relative_to(local)).is_file():
                path.unlink()
        if not (local / 'web/dist/index.html').is_file():
            raise RuntimeError('Build the frontend before packaging')
    secret_values = [v.encode() for v in audit.parse_env_file(ROOT / 'deploy/.env')]
    image_report, image_errors = audit.inspect_image(f'cloud-agent-controller:{version}', [v.decode() for v in secret_values])
    if image_errors:
        raise RuntimeError('Controller image metadata audit failed')
    (output / 'controller-image-audit.json').write_text(json.dumps(image_report, indent=2) + '\n')
    reports = []
    for directory in (target, local):
        for path in directory.rglob('*'):
            if path.is_file() and path.relative_to(directory).parts[0] != 'images':
                if path.name in {'.env', 'admin-token'} or path.suffix == '.pyc' or any(v in path.read_bytes() for v in secret_values):
                    raise RuntimeError('Secret or cache file in release: ' + path.relative_to(directory).as_posix())
        packaging.checksums(directory)
        manage.verify_checksums(directory)
        if args.stage_only:
            continue
        archive = directory.with_suffix('.zip')
        # Dotted release names are not file extensions.
        archive = output / (directory.name + '.zip')
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as z:
            for path in sorted(directory.rglob('*')):
                if path.is_file():
                    z.write(path, path.relative_to(output))
        with zipfile.ZipFile(archive) as z:
            if z.testzip():
                raise RuntimeError('ZIP CRC failure')
        reports.append({'name': archive.name, 'bytes': archive.stat().st_size, 'sha256': digest(archive), 'checksums': 'passed', 'zip_crc': 'passed', 'secret_scan': 'passed'})
    if args.stage_only:
        print('Release stages verified; ZIPs not updated')
        return
    (output / 'package-verification.json').write_text(json.dumps({'version': version, 'packages': reports}, indent=2) + '\n')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
