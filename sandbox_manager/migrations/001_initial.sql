PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    config_path TEXT NOT NULL,
    image TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sandboxes (
    sandbox_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    username TEXT NOT NULL,
    container_id TEXT,
    host_port INTEGER CHECK (host_port IS NULL OR host_port BETWEEN 1 AND 65535),
    status TEXT NOT NULL,
    image_version TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (agent_id, username)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    sandbox_id TEXT NOT NULL REFERENCES sandboxes(sandbox_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    username TEXT NOT NULL,
    workspace_relpath TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS sessions_sandbox_id_idx ON sessions(sandbox_id);
PRAGMA user_version = 1;
