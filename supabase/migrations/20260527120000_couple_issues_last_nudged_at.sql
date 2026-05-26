-- Track when a stale-issue nudge was last fired for a given issue so
-- the issue-nudge cron can fire push + email exactly once per stale
-- window. When partners touch the issue (bumping last_discussed_at)
-- and then let it go stale again, the cron will see
-- last_discussed_at > last_nudged_at and fire again.

alter table couple_issues
  add column if not exists last_nudged_at timestamptz;

-- Cron filter: issues in 'discussed' or 'agreed', stale, not yet
-- nudged for the current stale window. Partial index keeps it tight.
create index if not exists idx_couple_issues_pending_nudge
  on couple_issues(couple_link_id, last_discussed_at)
  where status in ('discussed', 'agreed') and resolved_at is null;
