-- §9.3.x Week 3 — Weekly couples report.
--
-- Cron Sunday 09:00 UTC generates one report per active couple_link.
-- Synthesises last 7 days of health logs + resolved/arbitrated
-- disputes + (optionally) shared chat into a structured digest both
-- partners see. Both viewed-at columns let us measure engagement.

create table couple_reports (
  id uuid primary key default gen_random_uuid(),
  couple_link_id uuid not null references couple_links(id) on delete cascade,
  period_start date not null,
  period_end date not null,
  content jsonb not null,
  generation_model text,
  generated_at timestamptz not null default now(),
  viewed_a_at timestamptz,
  viewed_b_at timestamptz,
  unique(couple_link_id, period_start)
);

create index idx_couple_reports_link_period on couple_reports(couple_link_id, period_start desc);

alter table couple_reports enable row level security;

-- Both link members can read reports on the link.
create policy couple_reports_member_select on couple_reports for select using (
  exists (
    select 1 from couple_links cl
    where cl.id = couple_link_id
      and cl.status = 'active'
      and (cl.user_a = auth.uid() or cl.user_b = auth.uid())
  )
);

-- Members can mark viewed (UPDATE) — workers create rows via service-role.
create policy couple_reports_member_update on couple_reports for update
  using (
    exists (
      select 1 from couple_links cl
      where cl.id = couple_link_id
        and cl.status = 'active'
        and (cl.user_a = auth.uid() or cl.user_b = auth.uid())
    )
  );
