-- Additive PostgreSQL migration for accounts, browser logins and platform handles.
-- Run against an existing InterArcade V2 schema before rolling out the new API.
BEGIN;
CREATE TABLE IF NOT EXISTS creator_accounts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS creator_logins (
    token_hash TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    csrf_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS creator_logins_account_idx ON creator_logins (account_id);
CREATE TABLE IF NOT EXISTS creator_platform_accounts (
    account_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    source_account_id TEXT NOT NULL,
    username TEXT NOT NULL,
    configured_at TEXT NOT NULL,
    PRIMARY KEY (account_id, platform, source_account_id)
);
ALTER TABLE live_sessions ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'live';
COMMIT;
