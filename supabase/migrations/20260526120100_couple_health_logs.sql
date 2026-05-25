-- §9.3.x Week 2 — Daily effort logging per partner.
--
-- One row per (couple_link, user, date). 1-minute check-in:
--   effort_rating 1-5 (slider)
--   partner_appreciation: one sentence
--   frustration: one sentence (optional)
--
-- Both partners see each other's logs side-by-side. Powers the
-- /couples/[linkId]/health dashboard + feeds the weekly report.

create table couple_health_logs (
  id uuid primary key default gen_random_uuid(),
  couple_link_id uuid not null references couple_links(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  log_date date not null,
  effort_rating smallint not null check (effort_rating between 1 and 5),
  partner_appreciation text check (partner_appreciation is null or length(partner_appreciation) between 1 and 300),
  frustration text check (frustration is null or length(frustration) between 1 and 300),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(couple_link_id, user_id, log_date)
);

create index idx_couple_health_logs_link_date on couple_health_logs(couple_link_id, log_date desc);

alter table couple_health_logs enable row level security;

-- Both link members can SELECT all logs on the link (they see each
-- other's check-ins side-by-side — that's the feature).
create policy couple_health_logs_member_select on couple_health_logs for select using (
  exists (
    select 1 from couple_links cl
    where cl.id = couple_link_id
      and cl.status = 'active'
      and (cl.user_a = auth.uid() or cl.user_b = auth.uid())
  )
);

-- Only the row owner can INSERT/UPDATE their own log.
create policy couple_health_logs_self_insert on couple_health_logs for insert
  with check (
    user_id = auth.uid()
    and exists (
      select 1 from couple_links cl
      where cl.id = couple_link_id
        and cl.status = 'active'
        and (cl.user_a = auth.uid() or cl.user_b = auth.uid())
    )
  );

create policy couple_health_logs_self_update on couple_health_logs for update
  using (user_id = auth.uid())
  with check (user_id = auth.uid());
