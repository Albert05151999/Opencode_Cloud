"""Workspace ownership stays with file_service; only explicit allocation API is used."""

from pathlib import Path

import httpx

from shared_libs.service import internal_sync_client
from shared_libs.workspace_paths import WorkspaceLayout, WorkspacePathError


class RemoteWorkspaces:
    def __init__(self, config, workspace_root, state_root):
        self.workspace_root, self.state_root = Path(workspace_root), Path(state_root)
        self.client = internal_sync_client(config, "file_service")

    def _allocate(self, agent_id, username, **values):
        response = self.client.post(
            "/internal/v1/workspaces/allocate",
            json={"agent_id": agent_id, "username": username, **values},
        )
        if response.status_code >= 400:
            raise WorkspacePathError(
                "Workspace allocation failed: " + response.text[:200]
            )
        return response.json()

    def ensure_user_layout(self, agent_id, username):
        return WorkspaceLayout(
            **{
                k: Path(v)
                for k, v in self._allocate(agent_id, username)["layout"].items()
            }
        )

    def user_scope(self, agent_id, username, session_id=None):
        data = self._allocate(agent_id, username, session_id=session_id)
        return Path(data["path"] or data["layout"]["shared"])

    def resolve_user_path(self, agent_id, username, relative_path, session_id=None):
        return Path(
            self._allocate(
                agent_id, username, relative_path=relative_path, session_id=session_id
            )["path"]
        )
