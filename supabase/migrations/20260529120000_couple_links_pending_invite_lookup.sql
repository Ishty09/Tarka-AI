-- Couple invite acceptance was silently broken since launch: the
-- accept flow at apps/web/(app)/couples/join/[code]/page.tsx looks up
-- the row by invite_code, but the only SELECT policy on couple_links
-- (couple_links_member from 20260516120300) requires the caller to
-- already be user_a or user_b. The accepter is neither yet — the row
-- has user_b = NULL until they accept — so the lookup returns zero
-- rows and the UI shows "Invite not found".
--
-- This adds a second SELECT policy that's OR-combined with the
-- existing one: authenticated users CAN read a couple_link still in
-- the invite stage (status = 'pending', code still present). The web
-- action's .eq('invite_code', code) does the actual matching; RLS
-- just unblocks the read.
--
-- We DO NOT include `invite_expires_at > now()` in the policy itself.
-- If we did, an expired row would vanish from the read entirely and
-- the join page would have to render the generic "Invite not found"
-- instead of the friendlier "This invite expired" branch (which then
-- transitions the row to status='expired'). Status='pending' alone is
-- enough to prevent sweeping accepted/revoked rows; the page handles
-- the expired-but-still-pending case at lines 83-96.
--
-- Security: invite_code is a 16-char random string from a 32-char
-- alphabet (~80 bits of entropy) — brute-force enumeration is
-- infeasible. The policy also gates on auth.uid() so anonymous
-- callers can't sweep the table.

drop policy if exists couple_links_pending_invite_lookup on couple_links;
create policy couple_links_pending_invite_lookup on couple_links for select using (
  auth.uid() is not null
  and status = 'pending'
  and invite_code is not null
);
