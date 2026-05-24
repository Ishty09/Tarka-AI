-- Same root cause as the profiles_self_insert fix
-- (20260525120000_profiles_self_insert.sql): the original §6.7
-- schema gave several user-touched tables only SELECT policies. Every
-- apps/web server action that INSERTs or UPDATEs into them silently
-- fails on RLS. Adding the missing write policies here.

-- ----- couple_links --------------------------------------------------------
-- createInvite (apps/web/(app)/couples/actions.ts) INSERTs a new row
-- with user_a = auth.uid(). acceptInvite UPDATEs the row to set user_b
-- and flip status. setCrossFactConsent + revokeLink also UPDATE.

create policy couple_links_creator_insert on couple_links for insert
  with check (user_a = auth.uid());

create policy couple_links_member_update on couple_links for update
  using (user_a = auth.uid() or user_b = auth.uid())
  with check (user_a = auth.uid() or user_b = auth.uid());

-- ----- group_rooms ---------------------------------------------------------
-- createGroup INSERTs with owner_id = auth.uid(). archiveGroup UPDATEs.

create policy group_rooms_owner_insert on group_rooms for insert
  with check (owner_id = auth.uid());

create policy group_rooms_owner_update on group_rooms for update
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

-- ----- group_members -------------------------------------------------------
-- createGroup seats the owner. joinGroup upserts the member. leaveGroup
-- deletes.

create policy group_members_self_insert on group_members for insert
  with check (user_id = auth.uid());

create policy group_members_self_delete on group_members for delete
  using (user_id = auth.uid());

-- Fix the existing group_members_visible policy: the subquery
-- referenced `gm.group_id = gm.group_id` (always true) instead of
-- correlating with the outer row. Replace it.

drop policy if exists group_members_visible on group_members;
create policy group_members_visible on group_members for select using (
  user_id = auth.uid()
  or exists (
    select 1 from group_members gm
    where gm.group_id = group_members.group_id
      and gm.user_id = auth.uid()
  )
);
