-- Additive PostgreSQL migration. Also applied idempotently by Database.initialize().
BEGIN;
ALTER TABLE live_sessions ADD COLUMN IF NOT EXISTS last_seen_at TEXT;
UPDATE live_sessions SET last_seen_at = started_at WHERE last_seen_at IS NULL;
COMMIT;
