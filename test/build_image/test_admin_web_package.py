import json
import tarfile

import pytest

from admin_web import build


@pytest.mark.parametrize('existing_log', [False, True])
def test_client_package_does_not_require_or_copy_local_logs(tmp_path, monkeypatch, existing_log):
    (tmp_path / 'VERSION').write_text('0.3.2')
    source = tmp_path / 'admin_web'
    for name in ('local_service', 'scripts', 'docs', 'frontend/dist'):
        (source / name).mkdir(parents=True)
    (source / 'frontend/dist/index.html').write_text('<html></html>')
    for name in ('__init__.py', 'module.yaml', 'config.schema.json'):
        (source / name).write_text('{}')
    if existing_log:
        (source / 'log').mkdir()
        (source / 'log/private.log').write_text('local runtime data')
    output = tmp_path / 'output'
    monkeypatch.setattr(build, 'ROOT', source)
    monkeypatch.setattr('sys.argv', ['build.py', '--skip-frontend', '--output', str(output)])
    build.main()
    with tarfile.open(output / '0.3.2/admin_web-0.3.2.tar.gz') as archive:
        assert archive.getmember('admin_web/log').isdir()
        assert 'admin_web/log/private.log' not in archive.getnames()
        assert 'admin_web/frontend/dist/index.html' in archive.getnames()
    assert json.loads((output / '0.3.2/manifest.json').read_text())['runtime'].startswith('Python 3.11+')
