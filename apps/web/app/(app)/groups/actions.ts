"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { type Tier } from "@quarrel/shared/constants";
import { hashUserId, trackServer } from "@/lib/analytics";
import { createServerSupabase } from "@/lib/supabase/server";
import { generateGroupInviteCode, maxSeatsForTier } from "@/lib/groups";

// All group-room mutations run as the authenticated user — RLS
// (§6.7 group_rooms_member + group_members_visible) gates everything.

export type ActionResult =
  | { ok: true; payload?: unknown }
  | { ok: false; error: string; upgrade?: boolean };

// ----- Create room (§9.3.4 step 1) -----------------------------------------

const createSchema = z.object({
  name: z.string().min(2).max(80),
  max_members: z.coerce.number().int().min(2).max(15),
  mediator_persona_slug: z.string().min(1).max(80),
});

export async function createGroup(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = createSchema.safeParse({
    name: (formData.get("name") ?? "").toString().trim(),
    max_members: formData.get("max_members"),
    mediator_persona_slug: formData.get("mediator_persona_slug"),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input." };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";
  const seatCap = maxSeatsForTier(tier);
  if (seatCap === 0) {
    return {
      ok: false,
      error: "Free tier doesn't include group rooms.",
      upgrade: true,
    };
  }
  if (parsed.data.max_members > seatCap) {
    return {
      ok: false,
      error: `Your ${tier} tier caps rooms at ${seatCap} seats. Pick a smaller size.`,
      upgrade: true,
    };
  }

  // Resolve mediator persona id.
  const { data: persona } = await supabase
    .from("personas")
    .select("id, slug, category, visibility, moderation_status")
    .eq("slug", parsed.data.mediator_persona_slug)
    .maybeSingle();
  if (!persona || persona.moderation_status !== "approved") {
    return { ok: false, error: "Pick a valid mediator." };
  }

  const inviteCode = generateGroupInviteCode();

  const { data: room, error: roomErr } = await supabase
    .from("group_rooms")
    .insert({
      owner_id: user.id,
      name: parsed.data.name,
      max_members: parsed.data.max_members,
      mediator_persona_id: persona.id,
      invite_code: inviteCode,
    })
    .select("id, invite_code")
    .maybeSingle();
  if (roomErr || !room) {
    return { ok: false, error: "Couldn't create the room." };
  }

  const { error: memberErr } = await supabase
    .from("group_members")
    .insert({ group_id: room.id, user_id: user.id, role: "owner" });
  if (memberErr) {
    // Best-effort rollback: archive the orphan room.
    await supabase.from("group_rooms").update({ archived: true }).eq("id", room.id);
    return { ok: false, error: "Couldn't seat you as owner. Try again." };
  }

  await trackServer("group_room_created", {
    user_id: hashUserId(user.id),
    group_id: room.id,
  });
  revalidatePath("/groups");
  return {
    ok: true,
    payload: { group_id: room.id, invite_code: room.invite_code },
  };
}

// ----- Accept invite (§9.3.4 step 3) ---------------------------------------

const acceptSchema = z.object({ invite_code: z.string().min(8).max(64) });

export async function joinGroup(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = acceptSchema.safeParse({ invite_code: formData.get("invite_code") });
  if (!parsed.success) return { ok: false, error: "Bad invite code." };

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: room } = await supabase
    .from("group_rooms")
    .select("id, owner_id, max_members, archived")
    .eq("invite_code", parsed.data.invite_code)
    .maybeSingle();
  if (!room) return { ok: false, error: "Group not found." };
  if (room.archived) return { ok: false, error: "This group has been archived." };

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";
  if (maxSeatsForTier(tier) === 0) {
    return {
      ok: false,
      error: "Free tier doesn't include group rooms.",
      upgrade: true,
    };
  }

  const { count } = await supabase
    .from("group_members")
    .select("user_id", { count: "exact", head: true })
    .eq("group_id", room.id);
  if ((count ?? 0) >= (room.max_members ?? 0)) {
    return { ok: false, error: "This room is full." };
  }

  // Composite PK (group_id, user_id) makes the insert idempotent via upsert.
  const { error } = await supabase
    .from("group_members")
    .upsert(
      { group_id: room.id, user_id: user.id, role: "member" },
      { onConflict: "group_id,user_id", ignoreDuplicates: true },
    );
  if (error) return { ok: false, error: "Couldn't join the room." };

  await trackServer("group_room_joined", {
    user_id: hashUserId(user.id),
    group_id: room.id,
  });
  revalidatePath("/groups");
  redirect(`/groups/${room.id}`);
}

// ----- Leave / archive -----------------------------------------------------

const idSchema = z.object({ group_id: z.string().uuid() });

export async function leaveGroup(formData: FormData): Promise<void> {
  const parsed = idSchema.safeParse({ group_id: formData.get("group_id") });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Owners can't leave — they archive instead. This keeps the row
  // accessible to historical RLS reads.
  const { data: room } = await supabase
    .from("group_rooms")
    .select("owner_id")
    .eq("id", parsed.data.group_id)
    .maybeSingle();
  if (!room) return;
  if (room.owner_id === user.id) {
    await supabase
      .from("group_rooms")
      .update({ archived: true })
      .eq("id", parsed.data.group_id);
    revalidatePath("/groups");
    redirect("/groups");
  }

  await supabase
    .from("group_members")
    .delete()
    .eq("group_id", parsed.data.group_id)
    .eq("user_id", user.id);
  revalidatePath("/groups");
  redirect("/groups");
}

export async function archiveGroup(formData: FormData): Promise<void> {
  const parsed = idSchema.safeParse({ group_id: formData.get("group_id") });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Only owners archive — the .eq filter on owner_id makes this a no-op
  // for non-owners.
  await supabase
    .from("group_rooms")
    .update({ archived: true })
    .eq("id", parsed.data.group_id)
    .eq("owner_id", user.id);
  revalidatePath("/groups");
}
