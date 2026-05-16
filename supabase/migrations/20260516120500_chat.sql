-- §6.1 chat tables: conversations, messages.
-- Sequenced after couples_groups so the couple_link_id / group_room_id FKs resolve.

create table conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  persona_id uuid not null references personas(id),
  mode text not null check (mode in (
    'argue','roast','mediate','council','negotiate','custom',
    'roast_my_x','decision_killer','cope_detector','steelman',
    'future_self','past_self','drill_sergeant'
  )),
  title text,
  archived boolean not null default false,
  couple_link_id uuid references couple_links(id) on delete set null,
  group_room_id uuid references group_rooms(id) on delete set null,
  metadata jsonb default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index idx_conversations_user on conversations(user_id, updated_at desc);
create index idx_conversations_mode on conversations(user_id, mode);

alter table conversations enable row level security;
create policy conversations_owner on conversations for all using (user_id = auth.uid());
create policy conversations_couple_member on conversations for select using (
  couple_link_id is not null and exists (
    select 1 from couple_links cl
    where cl.id = couple_link_id and cl.status = 'active'
      and (cl.user_a = auth.uid() or cl.user_b = auth.uid())
  )
);
create policy conversations_group_member on conversations for select using (
  group_room_id is not null and exists (
    select 1 from group_members gm
    where gm.group_id = group_room_id and gm.user_id = auth.uid()
  )
);


create table messages (
  id bigserial primary key,
  conversation_id uuid not null references conversations(id) on delete cascade,
  user_id uuid references profiles(id),
  role text not null check (role in ('user','assistant','tool','system')),
  content text not null,
  redacted_content text,
  model text,
  input_tokens integer,
  output_tokens integer,
  cached_input_tokens integer,
  safety_verdict text check (safety_verdict in ('safe','crisis','abuse','minor_self_sexualization','jailbreak','redacted')),
  latency_ms integer,
  langfuse_trace_id text,
  metadata jsonb default '{}',
  created_at timestamptz not null default now()
);
create index idx_messages_conversation on messages(conversation_id, created_at);
create index idx_messages_safety on messages(safety_verdict) where safety_verdict != 'safe';

alter table messages enable row level security;
create policy messages_via_conversation on messages for select using (
  exists (
    select 1 from conversations c where c.id = conversation_id
      and (
        c.user_id = auth.uid()
        or c.couple_link_id in (
          select id from couple_links where status = 'active' and (user_a = auth.uid() or user_b = auth.uid())
        )
        or c.group_room_id in (
          select group_id from group_members where user_id = auth.uid()
        )
      )
  )
);
create policy messages_insert on messages for insert with check (
  user_id = auth.uid() or user_id is null
);
