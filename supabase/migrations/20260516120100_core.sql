-- §6.1 core tables: profiles, personas.
-- conversations + messages live in 20260516120500_chat.sql so their FKs to
-- couple_links / group_rooms (created in 20260516120300) resolve.

create table profiles (
  id uuid primary key references auth.users on delete cascade,
  username text unique not null check (length(username) between 3 and 30),
  display_name text,
  avatar_url text,
  locale text not null default 'en',
  country_code text not null default 'US',
  timezone text not null default 'UTC',
  age_range text check (age_range in ('under_16','16_17','18_plus')),
  age_verified_at timestamptz,
  age_verification_method text check (age_verification_method in ('apple_age_api','google_age','self_declared','third_party')),
  tier text not null default 'free' check (tier in ('free','pro','max')),
  tier_source text check (tier_source in ('polar','revenuecat_ios','revenuecat_android','manual')),
  onboarding_completed_at timestamptz,
  daily_roast_time time,
  daily_roast_persona_slug text,
  emergency_contact_email text,
  emergency_contact_name text,
  notification_email boolean not null default true,
  notification_push boolean not null default true,
  marketing_email_consent boolean not null default false,
  is_admin boolean not null default false,
  is_suspended boolean not null default false,
  suspension_reason text,
  data_deletion_requested_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index idx_profiles_tier on profiles(tier);
create index idx_profiles_suspended on profiles(is_suspended) where is_suspended = true;

alter table profiles enable row level security;
create policy profiles_self_select on profiles for select using (id = auth.uid());
create policy profiles_self_update on profiles for update using (id = auth.uid());
create policy profiles_admin_all on profiles for all using (
  exists (select 1 from profiles p where p.id = auth.uid() and p.is_admin = true)
);


create table personas (
  id uuid primary key default gen_random_uuid(),
  slug text unique not null,
  owner_id uuid references profiles(id) on delete set null,
  name text not null,
  description text,
  locale text not null default 'en',
  cultural_tag text,
  category text not null check (category in ('argue','roast','mediate','council','productivity','cultural')),
  system_prompt text not null,
  voice_id text,
  voice_provider text check (voice_provider in ('chatterbox','elevenlabs','openai')),
  visibility text not null default 'private' check (visibility in ('private','unlisted','public','official')),
  price_cents integer not null default 0,
  install_count integer not null default 0,
  rating_avg numeric(2,1),
  rating_count integer not null default 0,
  is_safe boolean not null default true,
  moderation_status text not null default 'pending' check (moderation_status in ('pending','approved','rejected','flagged')),
  moderation_notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index idx_personas_visibility_rating on personas(visibility, rating_avg desc nulls last);
create index idx_personas_owner on personas(owner_id);
create index idx_personas_category on personas(category, visibility);

alter table personas enable row level security;
create policy personas_public_read on personas for select using (
  visibility in ('public','official') and moderation_status = 'approved'
);
create policy personas_owner on personas for all using (owner_id = auth.uid());
