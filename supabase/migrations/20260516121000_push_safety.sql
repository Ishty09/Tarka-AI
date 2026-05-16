-- §6.6 push + safety: push_subscriptions, crisis_hotlines, safety_incidents, audit_log.

create table push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  platform text not null check (platform in ('web','ios','android')),
  token text not null,
  device_label text,
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique(user_id, platform, token)
);

alter table push_subscriptions enable row level security;
create policy push_self on push_subscriptions for all using (user_id = auth.uid());


create table crisis_hotlines (
  locale text not null,
  country_code text not null,
  name text not null,
  phone text,
  url text,
  context_tag text not null check (context_tag in ('suicide','abuse','domestic_violence','child_safety','general')),
  primary key (locale, country_code, context_tag)
);

-- crisis_hotlines is a public reference table — everyone reads, only service
-- role writes. We grant SELECT to anon + authenticated so the Web Push handler
-- and unauthenticated landing pages can surface help instantly (CLAUDE.md §15).
alter table crisis_hotlines enable row level security;
create policy crisis_hotlines_public_read on crisis_hotlines for select using (true);


create table safety_incidents (
  id bigserial primary key,
  user_id uuid references profiles(id) on delete cascade,
  message_id bigint references messages(id),
  conversation_id uuid references conversations(id),
  category text not null check (category in ('crisis','abuse','minor_self_sexualization','jailbreak','spam','harassment')),
  verdict text not null,
  action_taken text not null,
  reviewed_by uuid references profiles(id),
  reviewed_at timestamptz,
  created_at timestamptz not null default now()
);
create index idx_safety_incidents_user on safety_incidents(user_id, created_at desc);

alter table safety_incidents enable row level security;
create policy safety_incidents_admin on safety_incidents for all using (
  exists (select 1 from profiles where id = auth.uid() and is_admin = true)
);


create table audit_log (
  id bigserial primary key,
  actor_user_id uuid references profiles(id),
  action text not null,
  entity_type text not null,
  entity_id text not null,
  metadata jsonb,
  ip_address inet,
  user_agent text,
  created_at timestamptz not null default now()
);
create index idx_audit_log_entity on audit_log(entity_type, entity_id);
create index idx_audit_log_actor on audit_log(actor_user_id, created_at desc);

alter table audit_log enable row level security;
create policy audit_log_admin on audit_log for select using (
  exists (select 1 from profiles where id = auth.uid() and is_admin = true)
);
