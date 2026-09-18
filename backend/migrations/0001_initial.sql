-- A new database: remote records are a rebuildable cache, sessions remain server-side.
CREATE TABLE tasks (id TEXT PRIMARY KEY, source TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE events (id TEXT PRIMARY KEY, source TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE members (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE connections (subject TEXT PRIMARY KEY, open_id TEXT NOT NULL UNIQUE, data TEXT NOT NULL);
CREATE TABLE sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE TABLE notifications (
 id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
 kind TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
 recipients TEXT NOT NULL, status TEXT NOT NULL, error TEXT NOT NULL DEFAULT ''
);
