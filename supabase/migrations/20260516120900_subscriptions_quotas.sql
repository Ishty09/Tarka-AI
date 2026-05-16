-- §6.5 subscriptions, usage_quotas, idempotency_keys.
-- All writes happen via apps/workers (service role). RLS only exposes SELECT
-- of own rows to authenticated users; idempotency_keys gets default-deny.

create table subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  tier text not null check (tier in ('pro','max')),
  status text not null check (status in ('active','past_due','canceled','paused','trialing')),
  source text not null check (source in ('polar','revenuecat_ios','revenuecat_android')),
  external_subscription_id text not null,
  current_period_start timestamptz not null,
  current_period_end timestamptz not null,
  cancel_at_period_end boolean not null default false,
  canceled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(source, external_subscription_id)
);
create index idx_subscriptions_user_status on subscriptions(user_id, status);

alter table subscriptions enable row level security;
create policy subscriptions_self_read on subscriptions for select using (user_id = auth.uid());


create table usage_quotas (
  user_id uuid not null references profiles(id) on delete cascade,
  period_start date not null,
  messages_used integer not null default 0,
  council_runs_used integer not null default 0,
  voice_seconds_used integer not null default 0,
  voice_clips_exported integer not null default 0,
  roast_feed_posts_used integer not null default 0,
  active_personas integer not null default 0,
  active_wagers integer not null default 0,
  primary key (user_id, period_start)
);

alter table usage_quotas enable row level security;
create policy usage_quotas_self_read on usage_quotas for select using (user_id = auth.uid());


create table idempotency_keys (
  key text primary key,
  scope text not null,
  user_id uuid references profiles(id),
  payload_hash text not null,
  response_status integer,
  response_body jsonb,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '7 days')
);
create index idx_idempotency_expires on idempotency_keys(expires_at);

-- Internal table — only the service role (apps/workers) touches it.
-- RLS enabled with no policies = default deny for authenticated/anon callers.
alter table idempotency_keys enable row level security;
