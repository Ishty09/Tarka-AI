-- §9.3.x Week 5 — Pre-conversation coaching.
--
-- Before a hard talk, each partner gets PRIVATE prep. AI builds:
--   - their talking points
--   - what their partner might say (and what each statement actually means)
--   - de-escalation paths
--
-- Privacy: each row is owned by ONE partner. The other partner cannot
-- read it. Service-role workers write the prep after the LLM call;
-- read access via RLS is restricted to the owner.

create table couple_conversation_preps (
  id uuid primary key default gen_random_uuid(),
  couple_link_id uuid not null references couple_links(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  topic text not null check (length(topic) between 5 and 200),
  desired_outcome text check (desired_outcome is null or length(desired_outcome) <= 500),
  context text check (context is null or length(context) <= 2000),
  prep jsonb,
  generation_model text,
  status text not null default 'pending' check (status in (
    'pending','generating','ready','failed'
  )),
  created_at timestamptz not null default now(),
  generated_at timestamptz
);

create index idx_couple_conversation_preps_user on couple_conversation_preps(user_id, created_at desc);

alter table couple_conversation_preps enable row level security;

-- Only the owner can SELECT/INSERT/UPDATE their own prep. Partner has
-- no read access — this is intentionally private prep, not shared content.
create policy couple_conversation_preps_self_all on couple_conversation_preps for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());
