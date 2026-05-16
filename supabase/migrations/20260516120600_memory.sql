-- §6.2 memory tables: user_facts, contradictions, mirror_reports, eulogy_reports.
-- user_facts.embedding is vector(1536) (OpenAI text-embedding-3-small).
-- Query path: pgvector hnsw cosine.

create table user_facts (
  id bigserial primary key,
  user_id uuid not null references profiles(id) on delete cascade,
  fact text not null,
  embedding vector(1536),
  source_message_id bigint references messages(id) on delete set null,
  confidence numeric(3,2) not null default 0.80 check (confidence between 0 and 1),
  category text check (category in ('belief','goal','preference','identity','history','commitment','rationalization')),
  superseded_by bigint references user_facts(id),
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);
create index idx_user_facts_user_active on user_facts(user_id, is_active) where is_active = true;
create index idx_user_facts_embedding on user_facts using hnsw (embedding vector_cosine_ops);

alter table user_facts enable row level security;
create policy user_facts_self on user_facts for all using (user_id = auth.uid());


create table contradictions (
  id bigserial primary key,
  user_id uuid not null references profiles(id) on delete cascade,
  fact_a_id bigint not null references user_facts(id) on delete cascade,
  fact_b_id bigint not null references user_facts(id) on delete cascade,
  severity numeric(2,1) not null check (severity between 0 and 10),
  summary text not null,
  surfaced_at timestamptz,
  acknowledged_at timestamptz,
  dismissed_at timestamptz,
  created_at timestamptz not null default now(),
  unique(user_id, fact_a_id, fact_b_id)
);
create index idx_contradictions_user_severity on contradictions(user_id, severity desc) where dismissed_at is null;

alter table contradictions enable row level security;
create policy contradictions_self on contradictions for all using (user_id = auth.uid());


create table mirror_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  period_start date not null,
  period_end date not null,
  summary text not null,
  patterns jsonb not null,
  dodges jsonb not null,
  generated_at timestamptz not null default now(),
  viewed_at timestamptz,
  unique(user_id, period_start)
);
create index idx_mirror_user on mirror_reports(user_id, period_start desc);

alter table mirror_reports enable row level security;
create policy mirror_self on mirror_reports for all using (user_id = auth.uid());


create table eulogy_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  quarter text not null,
  content text not null,
  generated_at timestamptz not null default now(),
  viewed_at timestamptz,
  unique(user_id, quarter)
);

alter table eulogy_reports enable row level security;
create policy eulogy_self on eulogy_reports for all using (user_id = auth.uid());
