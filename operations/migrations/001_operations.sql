CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    request_id TEXT UNIQUE,
    target TEXT,
    document TEXT
);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, document TEXT);
-- LoadTestStore separately creates load_tests and load_test_users in this DB.
