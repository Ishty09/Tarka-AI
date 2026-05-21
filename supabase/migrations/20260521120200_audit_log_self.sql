-- §27 step 59 — user-facing audit log viewer.
--
-- The existing audit_log_admin policy stays. We add a second SELECT
-- policy that lets each user read rows that are about them:
--   - rows they were the actor of (e.g. cross-fact retrieval they
--     triggered, admin actions if they themselves are admins),
--   - rows where the entity is their own profile or subscription
--     (account hard-delete, suspension, payment events).
--
-- Inserts/updates/deletes still require service-role — users cannot
-- write audit entries.

create policy audit_log_self_select on audit_log for select using (
  actor_user_id = auth.uid()
  or (
    entity_type in ('profile', 'subscription')
    and entity_id = auth.uid()::text
  )
);
