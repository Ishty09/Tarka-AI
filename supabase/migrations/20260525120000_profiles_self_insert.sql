-- Onboarding step 2 (apps/web `submitProfile`) UPSERTs the profile row
-- under the signed-in user. The original profiles policies in §6.7 only
-- granted SELECT + UPDATE to self — the implicit INSERT path was never
-- granted, so first-time users hit "Couldn't save your profile" on a
-- blocked RLS check.
--
-- Add the missing INSERT policy. WITH CHECK enforces that a user can
-- only insert a row whose id matches their auth.uid() — the same
-- constraint as the other self policies.

create policy profiles_self_insert on profiles for insert
  with check (id = auth.uid());
