-- §6.4 wagers: anti_charities catalog, wagers, wager_checkins, streaks.
-- Anti-charity disbursement on failure is captured by apps/workers/jobs/wager_evaluator.py.

create table anti_charities (
  slug text primary key,
  name text not null,
  description text not null,
  url text not null,
  ideological_tag text not null check (ideological_tag in (
    'progressive_us','conservative_us','centrist','religious_christian','secular',
    'climate_action','climate_skeptic','gun_rights','gun_control',
    'animal_welfare','industry_lobby'
  )),
  active boolean not null default true
);


create table wagers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
  goal text not null,
  stake_cents integer not null check (stake_cents between 500 and 100000),
  currency text not null default 'usd',
  anti_charity_slug text not null references anti_charities(slug),
  referee_id uuid references profiles(id),
  start_at date not null,
  end_at date not null,
  status text not null default 'pending' check (status in ('pending','active','succeeded','failed','disputed','refunded')),
  polar_payment_id text,
  polar_charge_id text,
  evaluation_notes text,
  evaluated_at timestamptz,
  disputed_at timestamptz,
  dispute_resolution text,
  created_at timestamptz not null default now(),
  constraint valid_dates check (end_at > start_at)
);
create index idx_wagers_user_status on wagers(user_id, status);
create index idx_wagers_active_end on wagers(end_at) where status = 'active';

alter table wagers enable row level security;
create policy wagers_self on wagers for all using (user_id = auth.uid());


create table wager_checkins (
  id bigserial primary key,
  wager_id uuid not null references wagers(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  checkin_date date not null,
  status text not null check (status in ('completed','missed','skipped')),
  notes text,
  proof_url text,
  created_at timestamptz not null default now(),
  unique(wager_id, checkin_date)
);

alter table wager_checkins enable row level security;
create policy wager_checkins_self on wager_checkins for all using (user_id = auth.uid());


create table streaks (
  id bigserial primary key,
  user_id uuid not null references profiles(id) on delete cascade,
  habit text not null,
  current_streak integer not null default 0,
  longest_streak integer not null default 0,
  last_checkin_at date,
  created_at timestamptz not null default now()
);
create index idx_streaks_user on streaks(user_id);

alter table streaks enable row level security;
create policy streaks_self on streaks for all using (user_id = auth.uid());
