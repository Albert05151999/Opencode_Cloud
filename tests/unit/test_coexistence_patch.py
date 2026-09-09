import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


@pytest.mark.parametrize('tamper', [False, True])
def test_patch_checks_base_preserves_config_and_never_stops_services(tmp_path, monkeypatch, tamper):
    source = Path(__file__).resolve().parents[2] / 'scripts/apply-coexistence-patch.py'
    spec = importlib.util.spec_from_file_location('trial_patch', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    patch, bundle, root = [tmp_path / name for name in ('patch', 'bundle', 'installed')]
    patch.mkdir()
    for directory in (bundle, root):
        (directory / 'deploy').mkdir(parents=True)
        (directory / 'deploy/doctor.py').write_text('old')
    (root / 'config.cfg').write_text('[platform]\ninstance_id=test-only\nhost=127.0.0.1\nport=8080\n[custom]\nkeep=yes\n')
    sha = lambda value: hashlib.sha256(value.encode()).hexdigest()
    (bundle / 'checksums.sha256').write_text(sha('old') + '  deploy/doctor.py\n')
    (patch / 'doctor.py').write_text('new')
    (patch / 'patch.json').write_text(json.dumps({'original_doctor_sha256': sha('old'), 'new_doctor_sha256': sha('new')}))
    monkeypatch.setattr(module, '__file__', str(patch / 'apply.py'))
    monkeypatch.setattr(module.os, 'geteuid', lambda: 0, raising=False)
    calls = []
    def docker(command, **kwargs):
        calls.append(command)
        assert command[:3] == ['docker', 'ps', '-q']
        return ''
    monkeypatch.setattr(module.subprocess, 'check_output', docker)
    class Listener:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def bind(self, address): assert address == ('127.0.0.1', 18080)
    monkeypatch.setattr(module.socket, 'socket', Listener)
    monkeypatch.setattr(sys, 'argv', ['apply.py', '--bundle', str(bundle), '--root', str(root)])
    if tamper:
        (bundle / 'deploy/doctor.py').write_text('tampered')
        with pytest.raises(AssertionError, match='checksum mismatch'):
            module.main()
        assert not (root / '.preflight-profile').exists()
        assert not calls
    else:
        module.main()
        assert len(calls) == 2
        assert 'port = 18080' in (root / 'config.cfg').read_text()
        assert 'keep = yes' in (root / 'config.cfg').read_text()
        assert (root / 'deploy/doctor.py.before-coexistence').read_text() == 'old'
        assert (root / '.preflight-profile').read_text().strip() == 'coexistence-trial'
