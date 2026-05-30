-- couples_accept_invite — atomic SECURITY DEFINER function that
-- accepts an invite by code.
--
-- Why a function instead of the existing inline UPDATE in
-- apps/web/app/(app)/couples/actions.ts:acceptInvite():
--
-- The UPDATE policy on couple_links (couple_links_member_update,
-- 20260525120100_user_write_policies.sql) requires the caller to be
-- user_a OR user_b. The partner accepting the invite is NEITHER at
-- the moment of accept — user_b is NULL until this very update
-- commits. So PostgreSQL silently dropped the UPDATE to 0 rows
-- without returning an error, the action thought it succeeded, the
-- redirect target rendered the still-pending row, and the user saw
-- a "refresh after accepting" dead-end forever.
--
-- This function does all the validation up front, then performs the
-- update as the function owner (BYPASSRLS). Returns either the new
-- link_id (on success) or an error code (on failure) so the web
-- action can map to a user-facing message.
--
-- Error codes returned (so the web action can localize):
--   unauthenticated, not_found, self_invite, already_accepted,
--   expired, tier_free_no_couples, cap_exceeded

create or replace function couples_accept_invite(p_invite_code text)
returns table (link_id uuid, error_code text)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_user uuid := auth.uid();
  v_link couple_links%rowtype;
  v_tier text;
  v_limit int;
  v_live_count int;
begin
  if v_user is null then
    return query select null::uuid, 'unauthenticated';
    return;
  end if;

  -- Find pending row by code. Codes have ~80 bits of entropy so the
  -- match is the only authorization needed here (in addition to the
  -- caller being authenticated).
  select * into v_link
  from couple_links
  where invite_code = p_invite_code
    and status = 'pending';
  if not found then
    return query select null::uuid, 'not_found';
    return;
  end if;

  if v_link.user_a = v_user then
    return query select null::uuid, 'self_invite';
    return;
  end if;

  if v_link.user_b is not null then
    return query select null::uuid, 'already_accepted';
    return;
  end if;

  if v_link.invite_expires_at is not null
     and v_link.invite_expires_at <= now() then
    -- Sweep this row so it stops appearing as pending.
    update couple_links set status = 'expired' where id = v_link.id;
    return query select null::uuid, 'expired';
    return;
  end if;

  -- Tier cap. Mirrors TIER_LIMITS in packages/shared/src/constants.ts
  -- and the web-side maxActiveCouples helper. Free + Pro = 1, Max = 3.
  select tier into v_tier from profiles where id = v_user;
  v_tier := coalesce(v_tier, 'free');
  v_limit := case v_tier
    when 'free' then 1
    when 'pro' then 1
    when 'max' then 3
    else 0
  end;

  if v_limit = 0 then
    return query select null::uuid, 'tier_free_no_couples';
    return;
  end if;

  -- Count active + non-expired pending links the user is in.
  select count(*)::int into v_live_count
  from couple_links
  where (user_a = v_user or user_b = v_user)
    and (
      status = 'active'
      or (status = 'pending' and invite_expires_at > now())
    );
  if v_live_count >= v_limit then
    return query select null::uuid, 'cap_exceeded';
    return;
  end if;

  -- Opportunistic sweep: flip the caller's stale-pending rows to
  -- 'expired' so they stop cluttering /couples.
  update couple_links
  set status = 'expired'
  where (user_a = v_user or user_b = v_user)
    and status = 'pending'
    and invite_expires_at <= now();

  -- The actual accept. Atomic with all the checks above.
  update couple_links
  set user_b = v_user,
      consent_b = true,
      status = 'active',
      invite_code = null,         -- burn the code; one-shot
      invite_expires_at = null
  where id = v_link.id;

  return query select v_link.id, null::text;
end;
$$;

grant execute on function couples_accept_invite(text) to authenticated;
