import tarfile

from build_image.build import archive_release


def test_archive_restores_script_execute_bits_and_private_env(tmp_path):
    release = tmp_path / 'release'
    release.mkdir()
    for name in ('install.sh', 'compose.sh', '.env'):
        path = release / name
        path.write_text('example\n')
        path.chmod(0o644)
    archive = tmp_path / 'release.tar.gz'
    archive_release(release, archive, 'test')
    with tarfile.open(archive) as tar:
        assert tar.getmember('release-test').mode == 0o755
        assert tar.getmember('release-test/install.sh').mode == 0o755
        assert tar.getmember('release-test/compose.sh').mode == 0o755
        assert tar.getmember('release-test/.env').mode == 0o600
