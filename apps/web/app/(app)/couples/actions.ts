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
  // Cap check: count active + non-expired pending (mirror the createInvite
  // logic from 21aa2c2). Without the expiry filter, a free user with one
  // stale pending invite from days ago can never accept anyone else's
  // invite.
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
      error: `You're at your ${tier} cap of ${limit} active couple link${limit === 1 ? "" : "s"}. Revoke the existing one (on /couples) to accept this invite.`,
    };
  }

  // Opportunistic sweep: any stale-pending rows owned by this user get
  // flipped to 'expired' so they stop cluttering /couples. Best-effort.
  await supabase
    .from("couple_links")
    .update({ status: "expired" })
    .eq("status", "pending")
    .lt("invite_expires_at", nowIso)
    .or(`user_a.eq.${user.id},user_b.eq.${user.id}`);

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

  await trackServer("couple_link_accepted", { user_id: hashUserId(user.id) });
  revalidatePath("/couples");
  redirect(`/couples/${link.id}`);
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
