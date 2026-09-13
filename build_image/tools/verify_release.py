#!/usr/bin/env python3
"""Verify a completed offline release without Docker or original source checkout."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest.get('prepared_only'):
        raise ValueError('Prepared contexts are not a completed offline release')
    checked = set()
    for line in (root / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        raw_path = root / name
        path = raw_path.resolve()
        if not path.is_relative_to(root) or raw_path.is_symlink():
            raise ValueError('Unsafe checksum path')
        actual = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''): actual.update(block)
        if actual.hexdigest() != digest: raise ValueError(f'Checksum mismatch: {name}')
        checked.add(name)
    expected = {'compose.json', 'manifest.json', 'install.sh', 'compose.sh'}
    expected.update(f'images/{module}.tar' for module in manifest['images'])
    if not expected <= checked: raise ValueError(f'Incomplete inventory: {expected-checked}')
    if 'admin_web' in manifest['images']: raise ValueError('Server release must not contain admin_web')
    if manifest['mode'] == 'ip' and 'nginx' in manifest['images']: raise ValueError('IP release must not require nginx')
    return {'version': manifest['version'], 'mode': manifest['mode'], 'images':len(manifest['images']), 'verified_files':len(checked)}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    print(json.dumps(verify(parser.parse_args().release)))
