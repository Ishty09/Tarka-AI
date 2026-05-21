-- §27 step 58 — GDPR account-deletion sweeper.
--
-- Two append-only changes that let the workers sweep + hard-delete an
-- account 30 days after the user requests it.

-- 1) audit_log.actor_user_id must outlive the user whose action it records
--    (privacy policy: audit entries retained for 12 months after deletion).
--    The original FK had no `on delete` clause, so it defaults to NO ACTION
--    and would block the cascade. SET NULL preserves the row but loses the
--    actor link, which is the right posture.

alter table audit_log
  drop constraint if exists audit_log_actor_user_id_fkey;
alter table audit_log
  add constraint audit_log_actor_user_id_fkey
  foreign key (actor_user_id)
  references profiles(id)
  on delete set null;

-- 2) Track that the account_deletion_grace_started email has been sent so
--    the sweeper doesn't keep firing it on every cron tick.

alter table profiles
  add column if not exists deletion_grace_notified_at timestamptz;
