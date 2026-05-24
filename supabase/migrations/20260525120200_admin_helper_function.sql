-- The original §6.7 admin policies all share the same shape:
--
--   exists (select 1 from profiles where id = auth.uid() and is_admin = true)
--
-- When that subquery runs against `profiles`, it re-evaluates the same
-- policies on `profiles` (including the admin one), which triggers
-- PostgreSQL's "42P17 infinite recursion in policy" error. Rabbi hit
-- this on the very first profile save because the upsert touched
-- `profiles` and tripped the admin policy's recursive check.
--
-- Fix: a single `is_admin()` SECURITY DEFINER helper that bypasses RLS
-- when reading the profiles row to determine admin status. Replace the
-- three admin policies (profiles, safety_incidents, audit_log) to call
-- it. Keep the same intent: admin can do everything on these tables.

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select coalesce(
    (select is_admin from public.profiles where id = auth.uid()),
    false
  );
$$;

-- Allow anon + authenticated to call the function. It returns just a
-- boolean derived from auth.uid(), so it can't be used to enumerate
-- other users.
grant execute on function public.is_admin() to anon, authenticated, service_role;

-- ----- profiles -----------------------------------------------------------
drop policy if exists profiles_admin_all on profiles;
create policy profiles_admin_all on profiles for all
  using (public.is_admin())
  with check (public.is_admin());

-- ----- safety_incidents ---------------------------------------------------
drop policy if exists safety_incidents_admin on safety_incidents;
create policy safety_incidents_admin on safety_incidents for all
  using (public.is_admin())
  with check (public.is_admin());

-- ----- audit_log ----------------------------------------------------------
drop policy if exists audit_log_admin on audit_log;
create policy audit_log_admin on audit_log for select
  using (public.is_admin());
