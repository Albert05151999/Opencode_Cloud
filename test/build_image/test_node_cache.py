import hashlib
import base64
import json

import pytest

from build_image.build import stage_node_archive, stage_npm_archives


@pytest.mark.parametrize('state', ['missing', 'valid', 'corrupt'])
def test_node_cache_requires_pinned_digest(tmp_path, state):
    root = tmp_path / 'source'
    output = tmp_path / 'context'
    output.mkdir()
    archive = root / 'artifacts/env/node-download/node-v24.20.0-linux-x64.tar.xz'
    args = {'NODE_VERSION': '24.20.0', 'NODE_ARCHIVE_SHA256': hashlib.sha256(b'verified').hexdigest()}
    if state != 'missing':
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b'verified' if state == 'valid' else b'corrupted')
    if state == 'corrupt':
        with pytest.raises(ValueError, match='pinned SHA256'):
            stage_node_archive(root, output, args)
        assert not list((output / 'runtime-downloads').iterdir())
    else:
        stage_node_archive(root, output, args)
        staged = output / 'runtime-downloads' / archive.name
        assert staged.exists() == (state == 'valid')
        if staged.exists():
            assert staged.read_bytes() == b'verified'


@pytest.mark.parametrize('corrupt', [False, True])
def test_npm_cache_checks_lock_integrity(tmp_path, corrupt):
    image = tmp_path / 'agent_runtime/image'
    image.mkdir(parents=True)
    cache = tmp_path / 'artifacts/env/npm-download'
    cache.mkdir(parents=True)
    output = tmp_path / 'context'
    (output / 'runtime-downloads').mkdir(parents=True)
    integrity = 'sha512-' + base64.b64encode(hashlib.sha512(b'valid').digest()).decode()
    names = ('opencode-ai', 'opencode-linux-x64', 'opencode-linux-x64-baseline')
    packages = {'node_modules/' + name: {'version': '1.0.0', 'integrity': integrity} for name in names}
    (image / 'package-lock.json').write_text(json.dumps({'packages': packages}))
    (cache / 'opencode-ai-1.0.0.tgz').write_bytes(b'bad' if corrupt else b'valid')
    if corrupt:
        with pytest.raises(ValueError, match='lock integrity'):
            stage_npm_archives(tmp_path, output)
        assert not list((output / 'runtime-downloads').iterdir())
    else:
        stage_npm_archives(tmp_path, output)
        assert (output / 'runtime-downloads/opencode-ai-1.0.0.tgz').read_bytes() == b'valid'
