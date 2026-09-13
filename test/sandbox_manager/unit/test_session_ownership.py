import os
import stat

import pytest

from file_service.workspace import WorkspaceManager


@pytest.mark.skipif(os.name != 'posix' or (hasattr(os, 'geteuid') and os.geteuid() != 0), reason='Linux root ownership integration')
def test_session_upload_scope_and_nested_outputs_are_writable_by_runtime(tmp_path):
    manager = WorkspaceManager(tmp_path / 'workspaces', tmp_path / 'state', runtime_uid=10001, runtime_gid=10001)
    scope = manager.user_scope('agent-code', 'alice', 'ses_test')
    assert scope.stat().st_uid == 10001 and stat.S_IMODE(scope.stat().st_mode) == 0o770
    # Repair a directory created by the old controller as root.
    os.chown(scope, 0, 0)
    scope.chmod(0o755)
    assert manager.user_scope('agent-code', 'alice', 'ses_test').stat().st_uid == 10001
    output = manager.resolve_user_path('agent-code', 'alice', 'outputs/report.txt', 'ses_test')
    assert output.parent.stat().st_uid == 10001
    assert manager.resolve_user_path('agent-code', 'alice', '.', 'ses_test') == scope
