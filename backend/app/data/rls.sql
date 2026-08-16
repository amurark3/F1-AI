-- Row-Level Security for every table this app owns.
--
-- WHY
-- Supabase publishes each table in the `public` schema over its PostgREST API.
-- A table with RLS disabled is therefore readable *and writable* by anyone who
-- knows the project URL and the (publishable, client-side) anon key — which is
-- what the "rls_disabled_in_public" security advisor flags.
--
-- WHY NO POLICIES
-- This app never touches PostgREST.  Every read and write goes through psycopg
-- over a plain Postgres connection (`DATABASE_URL`) as the owning role, and a
-- table's owner bypasses RLS unless FORCE ROW LEVEL SECURITY is set.  So RLS
-- with zero policies is exactly the intent: full access for the backend, none
-- for the public API.  Do NOT add a permissive `USING (true)` policy — that
-- would re-open the hole the advisor is reporting.
--
-- The application DDL (store.py, memory.py, rag/pgvector_store.py) applies the
-- same ALTER TABLE on startup, so a rebuilt database comes up hardened.  Run
-- this file once against an existing database — e.g. in the Supabase SQL
-- editor — to fix tables that were created before this was added.
--
-- Every statement is idempotent and safe to re-run.

ALTER TABLE IF EXISTS public.app_documents  ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.user_profile   ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.chat_message   ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.rulebook_chunk ENABLE ROW LEVEL SECURITY;

-- Defence in depth: RLS alone already blocks these roles, but revoking the
-- grants means a future accidental policy cannot hand them access either.
-- Guarded because `anon`/`authenticated` exist only on Supabase, not on a
-- vanilla Postgres used for local development.
DO $$
DECLARE
    target_role TEXT;
BEGIN
    FOREACH target_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = target_role) THEN
            EXECUTE format(
                'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', target_role
            );
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                'REVOKE ALL ON TABLES FROM %I', target_role
            );
        END IF;
    END LOOP;
END
$$;

-- Verify: `rls_enabled` must be true for all four rows.
--   SELECT tablename, rowsecurity AS rls_enabled
--     FROM pg_tables
--    WHERE schemaname = 'public'
--    ORDER BY tablename;
