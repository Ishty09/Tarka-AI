-- Fix infinite RLS recursion on group_members (PostgreSQL 42P17).
--
-- Symptom: every SELECT on conversations (and any table whose RLS
-- transitively touches group_members) returns
--   "infinite recursion detected in policy for relation group_members"
-- which surfaces as a SILENTLY empty UI:
-- - /chat shows "No conversations yet" despite the user having rows
-- - sidebar shows the same empty state
-- - couples flows error out because their queries embed conversations
--
-- Root cause: the existing group_members_visible policy (originally
-- in 20260516120300_couples_groups.sql, then "patched" in
-- 20260525120100_user_write_policies.sql) checks "is the caller also
-- a member of this group?" by SELECTing from group_members itself.
-- That inner SELECT re-evaluates RLS on group_members, which runs
-- THIS policy again, which subqueries group_members again, etc. PG
-- detects the cycle and aborts with 42P17 — and because
-- conversations_group_member's policy SELECTs from group_members
-- too, every conversations read inherits the error.
--
-- Fix: extract the membership check into a SECURITY DEFINER function.
-- The function runs as its owner (postgres, BYPASSRLS), so the inner
-- group_members SELECT inside the function does NOT re-trigger the
-- RLS policy. We then rewrite group_members_visible to use the
-- function. Same semantics ("you can see members of groups you're in"),
-- no recursion.
--
-- Pinned search_path on the function is required by Supabase linter
-- and prevents schema-shadowing attacks.

create or replace function auth_user_is_in_group(p_group_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists(
    select 1 from group_members
    where group_id = p_group_id
      and user_id = auth.uid()
  );
$$;

grant execute on function auth_user_is_in_group(uuid)
  to anon, authenticated, service_role;

drop policy if exists group_members_visible on group_members;
create policy group_members_visible on group_members for select using (
  -- You can always see your own membership row …
  user_id = auth.uid()
  -- … and you can see every member of any group you're also in.
  -- The function call bypasses RLS, breaking the recursion cycle.
  -- `public.` prefix is intentional for grep-ability + insulation
  -- against a future migration shifting the policy's search_path.
  or public.auth_user_is_in_group(group_id)
);
