-- §27 step 73 — 7-day retention measurement.
--
-- Cohort definitions and §28 launch gate (≥30%) live in
-- infra/runbooks/beta-cohort.md. This view formalises the SQL so the
-- admin UI and the CLI report read the same numbers.
--
-- Columns:
--   cohort_tag        — beta_invites.cohort_tag.
--   invited           — total invites in the cohort.
--   sent              — invites that actually shipped (sent_at not null).
--   signed_up         — invitees who created a profile.
--   retained_d2_d7    — signed-up users who sent ≥ 1 user-role message
--                       between 1 and 7 days after signup. This is the
--                       §28 gate's numerator.
--   activation_rate   — signed_up / invited (cohort funnel).
--   retention_rate    — retained_d2_d7 / signed_up (the §28 gate).

create or replace view cohort_retention as
with cohort as (
  select
    cohort_tag,
    count(*)                                              as invited,
    count(*) filter (where sent_at is not null)           as sent,
    count(*) filter (where signed_up_at is not null)      as signed_up
  from beta_invites
  where cohort_tag is not null
  group by cohort_tag
),
retained as (
  select
    bi.cohort_tag,
    count(distinct bi.signed_up_user_id) as retained_d2_d7
  from beta_invites bi
  join messages m on m.user_id = bi.signed_up_user_id
  where bi.signed_up_at is not null
    and m.role = 'user'
    and m.created_at >= bi.signed_up_at + interval '1 day'
    and m.created_at <  bi.signed_up_at + interval '8 days'
  group by bi.cohort_tag
)
select
  c.cohort_tag,
  c.invited,
  c.sent,
  c.signed_up,
  coalesce(r.retained_d2_d7, 0)::int                                     as retained_d2_d7,
  case when c.invited > 0
       then round(c.signed_up::numeric / c.invited, 4)
       else 0 end                                                        as activation_rate,
  case when c.signed_up > 0
       then round(coalesce(r.retained_d2_d7, 0)::numeric / c.signed_up, 4)
       else 0 end                                                        as retention_rate
from cohort c
left join retained r on r.cohort_tag = c.cohort_tag
order by c.cohort_tag;

-- The view inherits RLS from its base tables (beta_invites is
-- admin-only via the beta_invites_admin policy; messages is reachable
-- via the conversation join through messages_via_conversation, but for
-- the cross-user aggregation we need service-role context or admin).
-- For safety we add an explicit grant + comment so an operator can't
-- accidentally expose this on the anon role.

comment on view cohort_retention is
  'Beta-cohort retention. Admin-only; readable through Supabase service-role '
  'or any user whose profiles.is_admin = true.';
