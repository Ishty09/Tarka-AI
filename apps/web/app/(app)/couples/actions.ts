"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import { activeCoupleLimitFor, generateInviteCode, inviteExpiry } from "@/lib/couples";

// All couple-link mutations run as the authenticated user — RLS
// (§6.7 couple_links_member, profiles_self_*) gates everything.
// Service-role stays in workers (§1.3).

export type ActionResult = { ok: true; payload?: unknown } | { ok: false; error: string };

// ----- Create invite (§9.3.1 step 1) ----------------------------------------

export async function createInvite(
  _prev: ActionResult | null,
  _formData: FormData,
): Promise<ActionResult> {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";
  const limit = activeCoupleLimitFor(tier);
  if (limit === 0) {
    return {
      ok: false,
      error: "Free tier doesn't include couples mode. Upgrade to send an invite.",
    };
  }

  // Count active OR pending couple_links where this user is the creator
  // OR the accepter. RLS already scopes the read.
  const { count } = await supabase
    .from("couple_links")
    .select("id", { count: "exact", head: true })
    .in("status", ["pending", "active"])
    .or(`user_a.eq.${user.id},user_b.eq.${user.id}`);
  if ((count ?? 0) >= limit) {
    return {
      ok: false,
      error: `You're at your ${tier} cap of ${limit} active couple link${limit === 1 ? "" : "s"}. Revoke one to send another invite.`,
    };
  }

  const code = generateInviteCode();
  const expires = inviteExpiry();

  const { data: insertedRow, error } = await supabase
    .from("couple_links")
    .insert({
      user_a: user.id,
      invite_code: code,
      invite_expires_at: expires,
      consent_a: true, // creator consents implicitly by creating
      status: "pending",
    })
    .select("id, invite_code")
    .maybeSingle();
  if (error || !insertedRow) {
    return { ok: false, error: "Couldn't create invite. Try again." };
  }

  revalidatePath("/couples");
  return {
    ok: true,
    payload: { link_id: insertedRow.id, invite_code: insertedRow.invite_code },
  };
}

// ----- Accept invite (§9.3.1 step 3) ---------------------------------------

const acceptSchema = z.object({
  invite_code: z.string().min(8).max(64),
});

export async function acceptInvite(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = acceptSchema.safeParse({ invite_code: formData.get("invite_code") });
  if (!parsed.success) return { ok: false, error: "Bad invite code." };

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: link } = await supabase
    .from("couple_links")
    .select("id, user_a, user_b, invite_expires_at, status")
    .eq("invite_code", parsed.data.invite_code)
    .maybeSingle();
  if (!link) return { ok: false, error: "Invite not found." };
  if (link.user_a === user.id) {
    return { ok: false, error: "You created this invite — share it with your partner instead." };
  }
  if (link.user_b !== null) {
    return { ok: false, error: "This invite was already accepted." };
  }
  if (link.status !== "pending") {
    return { ok: false, error: `Invite is ${link.status}.` };
  }
  if (link.invite_expires_at && new Date(link.invite_expires_at) < new Date()) {
    await supabase
      .from("couple_links")
      .update({ status: "expired" })
      .eq("id", link.id);
    return { ok: false, error: "This invite expired." };
  }

  // Tier cap check for the accepter.
  const { data: profile } = await supabase
    .from("profiles")
    .select("tier")
    .eq("id", user.id)
    .maybeSingle();
  const tier: Tier = (profile?.tier as Tier) ?? "free";
  const limit = activeCoupleLimitFor(tier);
  if (limit === 0) {
    return {
      ok: false,
      error: "Free tier doesn't include couples mode. Upgrade to accept this invite.",
    };
  }
  const { count } = await supabase
    .from("couple_links")
    .select("id", { count: "exact", head: true })
    .in("status", ["pending", "active"])
    .or(`user_a.eq.${user.id},user_b.eq.${user.id}`);
  if ((count ?? 0) >= limit) {
    return {
      ok: false,
      error: `You're at your ${tier} cap of ${limit} active couple link${limit === 1 ? "" : "s"}.`,
    };
  }

  const { error } = await supabase
    .from("couple_links")
    .update({
      user_b: user.id,
      consent_b: true,
      status: "active",
      invite_code: null, // burn the code so the URL is one-shot
      invite_expires_at: null,
    })
    .eq("id", link.id);
  if (error) return { ok: false, error: "Couldn't accept invite." };

  revalidatePath("/couples");
  redirect(`/couples/${link.id}`);
}

// ----- Revoke link (§9.3.1 UI state "Revoked") -----------------------------

const idSchema = z.object({ id: z.string().uuid() });

export async function revokeLink(formData: FormData): Promise<void> {
  const parsed = idSchema.safeParse({ id: formData.get("id") });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  await supabase
    .from("couple_links")
    .update({
      status: "revoked",
      revoked_at: new Date().toISOString(),
      revoked_by: user.id,
    })
    .eq("id", parsed.data.id)
    .or(`user_a.eq.${user.id},user_b.eq.${user.id}`);

  revalidatePath("/couples");
}
