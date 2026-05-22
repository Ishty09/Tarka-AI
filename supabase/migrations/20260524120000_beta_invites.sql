-- §27 step 72 — beta cohort invites.
--
-- Tracks each hand-picked invitee for the soft-launch window. The
-- workers cron picks up unsent rows, generates a Supabase magic-link
-- signup URL, emails via Resend, and stamps sent_at. signed_up_at is
-- populated by a trigger on profile creation matching the email so
-- §27 step 73's 7-day retention query has all the data it needs.

create table beta_invites (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  invited_by uuid references profiles(id) on delete set null,
  cohort_tag text,                           -- e.g. "wave-1", "founder-friends"
  notes text,
  sent_at timestamptz,
  signed_up_at timestamptz,
  signed_up_user_id uuid references profiles(id) on delete set null,
  expires_at timestamptz,
  error_message text,
  created_at timestamptz not null default now(),
  -- One pending invite per email; if it has been used we keep the row
  -- for the retention join + allow another invite by inserting a new
  -- one (a second wave to the same address).
  unique (email, cohort_tag)
);

create index idx_beta_invites_pending
  on beta_invites(created_at)
  where sent_at is null;
create index idx_beta_invites_cohort
  on beta_invites(cohort_tag, signed_up_at);

alter table beta_invites enable row level security;

-- Admin-only read + write — no path for regular users.
create policy beta_invites_admin on beta_invites for all using (
  exists (
    select 1 from profiles p
    where p.id = auth.uid() and p.is_admin = true
  )
);

-- Convenience: backfill signed_up_at + signed_up_user_id when a new
-- profile lands whose email matches a pending invite. Profiles join
-- through auth.users by id, so we have to look up the email there.

create or replace function _beta_invites_link_profile()
returns trigger
language plpgsql security definer
set search_path = public, auth
as $$
declare
  v_email text;
begin
  select email into v_email from auth.users where id = new.id;
  if v_email is null then
    return new;
  end if;

  update beta_invites
     set signed_up_at = coalesce(signed_up_at, now()),
         signed_up_user_id = new.id
   where email = v_email
     and signed_up_at is null;

  return new;
end
$$;

create trigger beta_invites_link_profile
after insert on profiles
for each row execute function _beta_invites_link_profile();
