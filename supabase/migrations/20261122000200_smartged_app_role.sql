-- SmartGED runtime role.
-- The API must NOT connect as `postgres` on Supabase: that role bypasses Row Level Security.
-- `smartged_app` owns nothing and has NOBYPASSRLS, so every tenant policy (FORCE RLS) applies.
-- Enable login once, outside of version control:
--   ALTER ROLE smartged_app WITH LOGIN PASSWORD '<strong-random-password>';
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'smartged_app') THEN
    CREATE ROLE smartged_app NOLOGIN NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
END $$;

GRANT USAGE ON SCHEMA smartged TO smartged_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA smartged TO smartged_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA smartged TO smartged_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA smartged GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO smartged_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA smartged GRANT USAGE, SELECT ON SEQUENCES TO smartged_app;
ALTER ROLE smartged_app SET search_path = smartged, public;

-- The schema is never exposed through the Supabase Data API (PostgREST): only the FastAPI backend reads it.
REVOKE ALL ON SCHEMA smartged FROM anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA smartged FROM anon, authenticated;
