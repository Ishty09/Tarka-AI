"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { type Tier } from "@quarrel/shared/constants";
import { hashUserId, trackServer } from "@/lib/analytics";
import { serverEnv } from "@/lib/env";
import { createServerSupabase } from "@/lib/supabase/server";
import { activeCoupleLimitFor, generateInviteCode, inviteExpiry } from "@/lib/couples";

// All couple-link mutations run as the authenticated user — RLS
// (§6.7 couple_links_member, profiles_self_*) gates everything.
// Service-role stays in workers (§1.3).

export type ActionResult = { ok: true; payload?: unknown } | { ok: false; error: string };

// ----- Create invite (§9.3.1 step 1) ----------------------------------------

const createInviteSchema = z.object({
  partner_email: z
    .string()
    .trim()
    .max(254)
    .email("Enter a valid email.")
    .or(z.literal(""))
    .optional(),
});

export async function createInvite(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = createInviteSchema.safeParse({
    partner_email: (formData.get("partner_email") ?? "").toString(),
  });
  if (!parsed.success) {
    return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid input." };
  }
  const partnerEmail = parsed.data.partner_email?.trim() || null;

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

  // Count active links + pending links that haven't expired yet. An old
  // invite the user never shared (status=pending, invite_expires_at <
  // now()) still has status='pending' until something sweeps it —
  // including it in the cap locks a free-tier user out of creating
  // their one allowed link forever.
  const nowIso = new Date().toISOString();
  const { count: activeCount } = await supabase
    .from("couple_links")
    .select("id", { count: "exact", head: true })
    .eq("status", "active")
    .or(`user_a.eq.${user.id},user_b.eq.${user.id}`);
  const { count: pendingCount } = await supabase
    .from("couple_links")
    .select("id", { count: "exact", head: true })
    .eq("status", "pending")
    .gt("invite_expires_at", nowIso)
    .or(`user_a.eq.${user.id},user_b.eq.${user.id}`);
  const liveCount = (activeCount ?? 0) + (pendingCount ?? 0);
  if (liveCount >= limit) {
    return {
      ok: false,
      error: `You're at your ${tier} cap of ${limit} active couple link${limit === 1 ? "" : "s"}. Revoke one to send another invite.`,
    };
  }

  // Stale-pending sweep: any rows belonging to this user that have aged
  // past invite_expires_at get flipped to 'expired'. Best-effort — if it
  // fails for any reason we still let the new invite go through.
  await supabase
    .from("couple_links")
    .update({ status: "expired" })
    .eq("status", "pending")
    .lt("invite_expires_at", nowIso)
    .or(`user_a.eq.${user.id},user_b.eq.${user.id}`);

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

  await trackServer("couple_link_created", { user_id: hashUserId(user.id) });

  // Fire-and-forget partner email if the creator chose to send one.
  // Out-of-band sharing (WhatsApp / iMessage / Signal) remains the
  // default — this is just an alternate channel.
  if (partnerEmail) {
    void emailCoupleInvite(insertedRow.id, partnerEmail);
  }

  revalidatePath("/couples");
  return {
    ok: true,
    payload: { link_id: insertedRow.id, invite_code: insertedRow.invite_code },
  };
}

async function emailCoupleInvite(
  linkId: string,
  partnerEmail: string,
): Promise<void> {
  if (!serverEnv.WORKERS_URL || !serverEnv.WORKERS_INTERNAL_SECRET) return;
  try {
    await fetch(`${serverEnv.WORKERS_URL}/couples/invites/${linkId}/email`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${serverEnv.WORKERS_INTERNAL_SECRET}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ partner_email: partnerEmail }),
    });
  } catch {
    // Best-effort: the user still has the shareable link to copy.
  }
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

  // Atomic accept via couples_accept_invite() SECURITY DEFINER function
  // (migration 20260530130000). All the validation (existence, expiry,
  // self-invite, already-accepted, tier cap, stale-pending sweep) AND
  // the actual UPDATE happen in one transaction inside the function,
  // bypassing the RLS gotcha where the would-be partner can't UPDATE
  // a pending row because they're not yet user_b. Returns either the
  // link_id (success) or an error_code (which we map to copy here).
  const { data: rpcData, error: rpcError } = await supabase.rpc(
    "couples_accept_invite",
    { p_invite_code: parsed.data.invite_code },
  );
  if (rpcError) {
    return { ok: false, error: "Couldn't accept invite. Try again." };
  }
  const result = (rpcData as Array<{ link_id: string | null; error_code: string | null }> | null)?.[0];
  if (!result) {
    return { ok: false, error: "Couldn't accept invite. Try again." };
  }

  if (result.error_code) {
    const messages: Record<string, string> = {
      unauthenticated: "Please sign in to accept this invite.",
      not_found: "Invite not found.",
      self_invite:
        "You created this invite — share the link with your partner instead.",
      already_accepted: "This invite has already been accepted.",
      expired: "This invite expired.",
      tier_free_no_couples:
        "Free tier doesn't include couples mode. Upgrade to accept.",
      cap_exceeded: `You're at your tier cap of active couple links. Revoke an existing one (on /couples) to accept this invite.`,
    };
    return {
      ok: false,
      error: messages[result.error_code] ?? `Couldn't accept invite: ${result.error_code}.`,
    };
  }

  if (!result.link_id) {
    return { ok: false, error: "Couldn't accept invite. Try again." };
  }

  await trackServer("couple_link_accepted", { user_id: hashUserId(user.id) });
  revalidatePath("/couples");
  revalidatePath(`/couples/${result.link_id}`);
  redirect(`/couples/${result.link_id}`);
}

// ----- Revoke link (§9.3.1 UI state "Revoked") -----------------------------

const idSchema = z.object({ id: z.string().uuid() });

// ----- Cross-fact consent toggle (§9.3.1 step 4) ----------------------------
//
// Each user toggles only their own column. When BOTH cross_fact_consent_a
// and cross_fact_consent_b flip to true (AND both base consents are set,
// AND the link is active), the SQL function get_couple_facts() (defined
// in 20260516121100_couple_facts_function.sql) starts returning both
// partners' active facts to the chat route. The function writes an
// audit_log row on every retrieval.

const consentSchema = z.object({
  link_id: z.string().uuid(),
  enabled: z.union([z.literal("true"), z.literal("false")]).transform((v) => v === "true"),
});

export async function setCrossFactConsent(formData: FormData): Promise<void> {
  const parsed = consentSchema.safeParse({
    link_id: formData.get("link_id"),
    enabled: formData.get("enabled"),
  });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: link } = await supabase
    .from("couple_links")
    .select("id, user_a, user_b")
    .eq("id", parsed.data.link_id)
    .maybeSingle();
  if (!link) return;

  const column =
    link.user_a === user.id
      ? "cross_fact_consent_a"
      : link.user_b === user.id
      ? "cross_fact_consent_b"
      : null;
  if (column === null) return; // caller isn't a member; RLS would also reject

  await supabase
    .from("couple_links")
    .update({ [column]: parsed.data.enabled })
    .eq("id", parsed.data.link_id);

  if (parsed.data.enabled) {
    await trackServer("couple_cross_fact_enabled", {
      user_id: hashUserId(user.id),
      link_id: parsed.data.link_id,
    });
  }
  revalidatePath(`/couples/${parsed.data.link_id}`);
}


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
