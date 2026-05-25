-- §9.3.x — Couple disputes table for the relationship-arbitration
-- feature. Both partners submit their perspective independently;
-- once both are in, the workers route fires an LLM call that
-- produces a structured JSON verdict both partners see.
--
-- Privacy: each perspective is only readable by its author until both
-- perspectives are submitted. After arbitration, both perspectives +
-- the verdict are visible to both link members. Either partner can
-- mark resolved; revoking the couple link cascade-deletes disputes.

create table couple_disputes (
  id uuid primary key default gen_random_uuid(),
  couple_link_id uuid not null references couple_links(id) on delete cascade,
  title text not null check (length(title) between 3 and 200),
  status text not null default 'awaiting' check (status in (
    'awaiting',
    'arbitrating',
    'arbitrated',
    'resolved'
  )),
  perspective_a_user_id uuid references profiles(id) on delete set null,
  perspective_a_text text,
  perspective_a_submitted_at timestamptz,
  perspective_b_user_id uuid references profiles(id) on delete set null,
  perspective_b_text text,
  perspective_b_submitted_at timestamptz,
  arbitration jsonb,
  arbitrated_at timestamptz,
  arbitration_model text,
  resolved_at timestamptz,
  resolved_by uuid references profiles(id) on delete set null,
  created_at timestamptz not null default now()
);

create index idx_couple_disputes_link_status on couple_disputes(couple_link_id, status);
create index idx_couple_disputes_created on couple_disputes(couple_link_id, created_at desc);

alter table couple_disputes enable row level security;

-- Any active link member can READ disputes on the link. The
-- application layer hides the other partner's perspective until both
-- are submitted (we can't easily express that constraint in RLS
-- without making the policy too clever).
create policy couple_disputes_member_select on couple_disputes for select using (
  exists (
    select 1 from couple_links cl
    where cl.id = couple_link_id
      and cl.status = 'active'
      and (cl.user_a = auth.uid() or cl.user_b = auth.uid())
  )
);

create policy couple_disputes_member_insert on couple_disputes for insert
  with check (
    exists (
      select 1 from couple_links cl
      where cl.id = couple_link_id
        and cl.status = 'active'
        and (cl.user_a = auth.uid() or cl.user_b = auth.uid())
    )
  );

create policy couple_disputes_member_update on couple_disputes for update
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
