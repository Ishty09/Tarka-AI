"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { type Tier } from "@quarrel/shared/constants";
import { createServerSupabase } from "@/lib/supabase/server";
import {
  maxActiveWagersForTier,
  maxStakeCentsForTier,
  minStakeCents,
  polarEnabled,
} from "@/lib/wagers";

// Wager creation. Polar auth-and-capture is stubbed behind the
// ENABLE_POLAR env (§3 stack). Until that flag flips:
//   - status goes straight to 'active' (no funds actually held)
//   - polar_payment_id stays null
//   - evaluator (step 40) treats these as ordinary wagers
// Once §27 step 47 wires Polar, creation moves rows to 'pending' and
// the step 48 webhook handler advances them to 'active'.

export type ActionResult = { ok: true; payload?: unknown } | { ok: false; error: string };

const createSchema = z.object({
  goal: z.string().min(10).max(500),
  start_at: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  end_at: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  stake_cents: z.coerce.number().int(),
  currency: z.string().default("usd"),
  anti_charity_slug: z.string().min(1).max(120),
  referee_id: z.string().uuid().optional().or(z.literal("")).transform((v) => (v ? v : undefined)),
});

export async function createWager(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = createSchema.safeParse({
    goal: (formData.get("goal") ?? "").toString().trim(),
    start_at: formData.get("start_at"),
    end_at: formData.get("end_at"),
    stake_cents: formData.get("stake_cents"),
    currency: formData.get("currency") ?? "usd",
    anti_charity_slug: formData.get("anti_charity_slug"),
    referee_id: formData.get("referee_id") ?? "",
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

  const maxActive = maxActiveWagersForTier(tier);
  if (maxActive === 0) {
    return {
      ok: false,
      error: "Free tier doesn't include wagers. Upgrade to stake one.",
    };
  }

  const maxStake = maxStakeCentsForTier(tier);
  if (parsed.data.stake_cents < minStakeCents()) {
    return { ok: false, error: `Minimum stake is $${(minStakeCents() / 100).toFixed(2)}.` };
  }
  if (parsed.data.stake_cents > maxStake) {
    return {
      ok: false,
      error: `Your ${tier} tier caps stakes at $${(maxStake / 100).toFixed(2)}.`,
    };
  }

  if (new Date(parsed.data.end_at).getTime() <= new Date(parsed.data.start_at).getTime()) {
    return { ok: false, error: "End date must be after the start date." };
  }

  // Anti-charity must exist and be active.
  const { data: antiCharity } = await supabase
    .from("anti_charities")
    .select("slug, active")
    .eq("slug", parsed.data.anti_charity_slug)
    .maybeSingle();
  if (!antiCharity || !antiCharity.active) {
    return { ok: false, error: "Pick a valid anti-charity." };
  }

  // Tier cap on currently-active wagers.
  const { count: activeCount } = await supabase
    .from("wagers")
    .select("id", { count: "exact", head: true })
    .eq("user_id", user.id)
    .in("status", ["pending", "active"]);
  if ((activeCount ?? 0) >= maxActive) {
    return {
      ok: false,
      error: `You're at your ${tier} cap of ${maxActive} active wager${maxActive === 1 ? "" : "s"}. Resolve one to start another.`,
    };
  }

  // Referee must be an existing profile (we don't check it's reachable —
  // a real implementation would email them; that lands with step 44).
  if (parsed.data.referee_id) {
    if (tier === "pro" || tier === "max") {
      const { data: refereeProfile } = await supabase
        .from("profiles")
        .select("id")
        .eq("id", parsed.data.referee_id)
        .maybeSingle();
      if (!refereeProfile) {
        return { ok: false, error: "Referee profile not found." };
      }
    } else {
      return { ok: false, error: "Referees are a Pro / Max feature." };
    }
  }

  // Status decision:
  //   Polar disabled (default during pre-launch) → 'active' immediately.
  //   Polar enabled → 'pending'; the webhook handler (§27 step 48) will
  //     advance to 'active' on order.paid.
  const status = polarEnabled() ? "pending" : "active";

  const { data: wagerRow, error } = await supabase
    .from("wagers")
    .insert({
      user_id: user.id,
      goal: parsed.data.goal,
      stake_cents: parsed.data.stake_cents,
      currency: parsed.data.currency,
      anti_charity_slug: parsed.data.anti_charity_slug,
      referee_id: parsed.data.referee_id ?? null,
      start_at: parsed.data.start_at,
      end_at: parsed.data.end_at,
      status,
    })
    .select("id, status")
    .maybeSingle();
  if (error || !wagerRow) {
    return { ok: false, error: "Couldn't create wager. Try again." };
  }

  revalidatePath("/wagers");
  return {
    ok: true,
    payload: {
      wager_id: wagerRow.id,
      status: wagerRow.status,
      polar_enabled: polarEnabled(),
    },
  };
}

// ----- Cancel pending / refund-pending wager --------------------------------

const idSchema = z.object({ id: z.string().uuid() });

export async function cancelPendingWager(formData: FormData): Promise<void> {
  const parsed = idSchema.safeParse({ id: formData.get("id") });
  if (!parsed.success) return;

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Only allow cancelling our own wagers, and only while still pending —
  // active wagers can't be cancelled because the stake is committed.
  await supabase
    .from("wagers")
    .update({ status: "refunded" })
    .eq("id", parsed.data.id)
    .eq("user_id", user.id)
    .eq("status", "pending");

  revalidatePath("/wagers");
}
