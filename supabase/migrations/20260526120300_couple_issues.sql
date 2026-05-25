-- §9.3.x Week 4 — Open issues tracker.
--
-- Recurring themes a couple keeps coming back to (money, in-laws,
-- household, intimacy, career, etc.). Auto-extracted from disputes +
-- (optionally) health frustrations by an LLM job, plus partners can
-- add issues manually. Each issue has a status lifecycle:
--   discussed  → talked about but no agreement
--   agreed     → both committed to a path
--   resolved   → not a current source of friction
--   recurring  → keeps coming back (auto-flag after N re-mentions)
--
-- Reminder: if an issue is left in 'discussed' or 'agreed' for >30
-- days without a follow-up, the weekly report flags it.

create table couple_issues (
  id uuid primary key default gen_random_uuid(),
  couple_link_id uuid not null references couple_links(id) on delete cascade,
  theme text not null check (length(theme) between 2 and 100),
  description text check (description is null or length(description) <= 1000),
  status text not null default 'discussed' check (status in (
    'discussed','agreed','resolved','recurring'
  )),
  severity smallint not null default 5 check (severity between 1 and 10),
  source text not null default 'manual' check (source in (
    'manual','dispute','health_log','chat_extract','report'
  )),
  source_ref uuid,  -- e.g. couple_disputes.id or couple_reports.id
  first_raised_at timestamptz not null default now(),
  last_discussed_at timestamptz not null default now(),
  resolved_at timestamptz,
  resolved_by uuid references profiles(id) on delete set null,
  created_by uuid references profiles(id) on delete set null,
  recurrence_count integer not null default 1,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_couple_issues_link_status on couple_issues(couple_link_id, status);
create index idx_couple_issues_last_discussed on couple_issues(couple_link_id, last_discussed_at desc);

alter table couple_issues enable row level security;

create policy couple_issues_member_select on couple_issues for select using (
  exists (
    select 1 from couple_links cl
    where cl.id = couple_link_id
      and cl.status = 'active'
      and (cl.user_a = auth.uid() or cl.user_b = auth.uid())
  )
);

create policy couple_issues_member_insert on couple_issues for insert
  with check (
    exists (
      select 1 from couple_links cl
      where cl.id = couple_link_id
        and cl.status = 'active'
        and (cl.user_a = auth.uid() or cl.user_b = auth.uid())
    )
  );

create policy couple_issues_member_update on couple_issues for update
  using (
    exists (
      select 1 from couple_links cl
      where cl.id = couple_link_id
        and cl.status = 'active'
        and (cl.user_a = auth.uid() or cl.user_b = auth.uid())
    )
  )
  with check (
    exists (
      select 1 from couple_links cl
      where cl.id = couple_link_id
        and cl.status = 'active'
        and (cl.user_a = auth.uid() or cl.user_b = auth.uid())
    )
  );
