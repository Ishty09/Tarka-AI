-- The original Supabase project sets up default privileges so every
-- new table in `public` is automatically usable by anon/authenticated
-- (RLS then filters at row level). When the apply-migrations.py
-- script's `--reset` flag ran `drop schema public cascade; create
-- schema public;`, those defaults were lost and every existing table
-- ended up granted only to the `postgres` role.
--
-- Symptom: 42501 "permission denied for table profiles" on signup,
-- even though RLS policies are correct. PostgreSQL checks table-level
-- GRANTs before evaluating RLS.
--
-- Fix in two layers:
--   1. Backfill grants on every existing table + sequence in public.
--   2. Restore ALTER DEFAULT PRIVILEGES so future tables auto-grant.
--
-- This mirrors what Supabase does on a fresh project. RLS remains the
-- security boundary; these grants only let the role get to the RLS
-- check at all.

-- ----- 1. Backfill grants on existing objects -----------------------------

grant usage on schema public to anon, authenticated, service_role;

grant select, insert, update, delete on all tables in schema public
  to anon, authenticated;
grant all on all tables in schema public to service_role;

grant usage, select on all sequences in schema public
  to anon, authenticated, service_role;

grant execute on all functions in schema public
  to anon, authenticated, service_role;

-- ----- 2. Default privileges for future tables ----------------------------

-- `alter default privileges` applies to objects created BY the named
-- role going forward. Supabase uses `postgres` (which the Supabase CLI
-- + the migration applier runs as).

alter default privileges in schema public
  grant select, insert, update, delete on tables to anon, authenticated;
alter default privileges in schema public
  grant all on tables to service_role;

alter default privileges in schema public
  grant usage, select on sequences to anon, authenticated, service_role;

alter default privileges in schema public
  grant execute on functions to anon, authenticated, service_role;
