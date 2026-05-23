-- §6.3 social tables that conversations FK into: couple_links, group_rooms, group_members.
-- Writes are routed through apps/workers (service role); RLS here only grants SELECT.

create table couple_links (
  id uuid primary key default gen_random_uuid(),
  user_a uuid not null references profiles(id) on delete cascade,
  user_b uuid references profiles(id) on delete cascade,
  invite_code text unique,
  invite_expires_at timestamptz,
  consent_a boolean not null default false,
  consent_b boolean not null default false,
  cross_fact_consent_a boolean not null default false,
  cross_fact_consent_b boolean not null default false,
  status text not null default 'pending' check (status in ('pending','active','revoked','expired')),
  revoked_at timestamptz,
  revoked_by uuid references profiles(id),
  created_at timestamptz not null default now(),
  constraint different_users check (user_a is null or user_b is null or user_a != user_b)
);
create index idx_couple_links_users on couple_links(user_a, user_b);
create index idx_couple_links_status on couple_links(status);

alter table couple_links enable row level security;
create policy couple_links_member on couple_links for select using (
  user_a = auth.uid() or user_b = auth.uid()
);


create table group_rooms (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references profiles(id) on delete cascade,
  name text not null,
  invite_code text unique not null,
  max_members integer not null default 5,
  mediator_persona_id uuid references personas(id),
  archived boolean not null default false,
  created_at timestamptz not null default now()
);


create table group_members (
  group_id uuid not null references group_rooms(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  role text not null default 'member' check (role in ('owner','member')),
  joined_at timestamptz not null default now(),
  primary key (group_id, user_id)
);


-- Policies live below the tables they reference: group_rooms_member's
-- USING clause looks up group_members, so the table must exist first.

alter table group_rooms enable row level security;
create policy group_rooms_member on group_rooms for select using (
  owner_id = auth.uid()
  or exists (select 1 from group_members where group_id = id and user_id = auth.uid())
);

alter table group_members enable row level security;
create policy group_members_visible on group_members for select using (
  exists (select 1 from group_members gm where gm.group_id = group_id and gm.user_id = auth.uid())
);
