"""Apply the explicit trial preflight patch to an already staged installation.

Does not start/stop containers or change Docker. Original release is verified first.
"""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path('/srv/cloud-agent'))
    args = parser.parse_args()
    assert os.geteuid() == 0, 'sudo required'
    bundle, root = args.bundle.resolve(), args.root.resolve()
    assert len(root.parts) >= 3 and root != bundle, 'invalid installation root'
    patch = Path(__file__).resolve().parent
    metadata = json.loads((patch / 'patch.json').read_text())
    assert digest(patch / 'doctor.py') == metadata['new_doctor_sha256'], 'patch checksum mismatch'
    manifest = bundle / 'checksums.sha256'
    original_manifest = manifest.read_text()
    entries = []
    for line in original_manifest.splitlines():
        expected, relative = line.split('  ', 1)
        target = (bundle / relative).resolve(strict=True)
        assert target.is_relative_to(bundle) and target.is_file(), 'invalid release path'
        assert digest(target) == expected, 'release checksum mismatch: ' + relative
        entries.append((expected, relative))
    assert digest(bundle / 'deploy/doctor.py') == metadata['original_doctor_sha256'], 'wrong patch base'
    config = root / 'config.cfg'
    cfg = configparser.ConfigParser(interpolation=None)
    assert cfg.read(config), 'run original installer first to stage installation'
    instance = cfg['platform']['instance_id']
    marker = root / '.instance-id'
    assert not marker.exists() or marker.read_text().strip() == instance, 'instance mismatch'
    active = subprocess.check_output(['docker', 'ps', '-q', '--filter', 'label=com.docker.compose.project=' + instance], text=True)
    sandboxes = subprocess.check_output(['docker', 'ps', '-q', '--filter', 'label=cloud.platform_instance=' + instance], text=True)
    assert not active.strip() and not sandboxes.strip(), 'new installation already running; no live changes applied'
    assert cfg['platform']['host'] == '127.0.0.1', 'loopback required'
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 18080))
    targets = [manifest, bundle / 'deploy/doctor.py', config, root / 'deploy/doctor.py']
    for target in targets:
        backup = target.with_name(target.name + '.before-coexistence')
        assert not backup.exists(), 'backup exists; patch may already be applied'
    for target in targets:
        shutil.copy2(target, target.with_name(target.name + '.before-coexistence'))
    shutil.copyfile(patch / 'doctor.py', bundle / 'deploy/doctor.py')
    shutil.copyfile(patch / 'doctor.py', root / 'deploy/doctor.py')
    cfg['platform']['port'] = '18080'
    with config.open('w') as stream:
        cfg.write(stream)
    (root / '.preflight-profile').write_text('coexistence-trial\n')
    manifest.write_text(''.join((metadata['new_doctor_sha256'] if name == 'deploy/doctor.py' else sha) + '  ' + name + '\n' for sha, name in entries))
    (root / 'coexistence-patch.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({'result': 'passed', 'profile': 'coexistence-trial', 'port': 18080,
                      'services_started_or_stopped': False, 'original_release_acceptance_applies_to_patch': False}))


if __name__ == '__main__':
    main()
