-- Catalog is the only writer. Resource blobs are SHA-256 addressed files.
CREATE TABLE IF NOT EXISTS catalog (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    revision INTEGER NOT NULL,
    document TEXT NOT NULL
);
-- Import staging tables are created by the transfer service on first use.
-- Existing v0 catalogs are backed up before the lifecycle schema upgrade.
