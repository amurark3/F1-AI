-- Durable document store for small JSON application documents.
--
-- Used by app/data/store.py to persist the prediction snapshot cache and the
-- prediction accuracy history off the ephemeral filesystem.  The table is
-- created automatically on first write; this file is kept for reference and
-- for provisioning a database manually (e.g. via the Supabase SQL editor).

CREATE TABLE IF NOT EXISTS app_documents (
    name       TEXT PRIMARY KEY,
    payload    JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
