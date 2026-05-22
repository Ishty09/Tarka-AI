"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { hashUserId, trackServer } from "@/lib/analytics";
import { createServerSupabase } from "@/lib/supabase/server";
import {
  cancelSubscriptionAtPeriodEnd,
  changeSubscriptionProduct,
  createCheckout,
  uncancelSubscription,
  type IntervalKey,
  type TierKey,
} from "@/lib/polar";

// Server actions for the billing page. `startCheckout` is a redirect
// action — on success it 303s to the Polar hosted URL; on failure it
// returns an ActionResult so the form can surface the error inline.

export type ActionResult = { ok: true } | { ok: false; error: string };

const checkoutSchema = z.object({
  tier: z.enum(["pro", "max"]),
  interval: z.enum(["monthly", "annual"]),
});

export async function startCheckout(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = checkoutSchema.safeParse({
    tier: (formData.get("tier") ?? "").toString() as TierKey,
    interval: (formData.get("interval") ?? "").toString() as IntervalKey,
  });
  if (!parsed.success) {
    return { ok: false, error: "Pick a tier and an interval." };
  }

  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  if (!user.email) return { ok: false, error: "Account is missing an email." };

  const result = await createCheckout({
    tier: parsed.data.tier,
    interval: parsed.data.interval,
    userId: user.id,
    email: user.email,
  });

  if (!result.ok) {
    return { ok: false, error: friendlyPolarError(result.error, result.status) };
  }

  // §20 upgrade_clicked — fires when the user commits to a checkout
  // (just before the Polar redirect). The matching upgrade_completed
  // fires from the Polar webhook handler in apps/workers.
  await trackServer("upgrade_clicked", {
    user_id: hashUserId(user.id),
    tier: parsed.data.tier,
    interval: parsed.data.interval,
  });

  redirect(result.url);
}

// ----- Cancel + resume + cross-tier swap ----------------------------------


/** Look up the user's active Polar subscription id under their session. */
async function findActivePolarSubscriptionId(): Promise<string | null> {
  const supabase = await createServerSupabase();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data } = await supabase
    .from("subscriptions")
    .select("external_subscription_id, source, status")
    .eq("user_id", user.id)
    .eq("source", "polar")
    .in("status", ["active", "trialing", "past_due"])
    .order("current_period_end", { ascending: false })
    .limit(1);

  const row = (data ?? [])[0];
  return row?.external_subscription_id ?? null;
}


export async function cancelSubscriptionAction(): Promise<ActionResult> {
  const externalId = await findActivePolarSubscriptionId();
  if (!externalId) return { ok: false, error: "No active subscription to cancel." };
  const res = await cancelSubscriptionAtPeriodEnd(externalId);
  if (!res.ok) return { ok: false, error: friendlyPolarError(res.error, res.status) };
  await trackServer("downgrade_clicked", { external_subscription_id: externalId });
  revalidatePath("/settings/billing");
  return { ok: true };
}


export async function resumeSubscriptionAction(): Promise<ActionResult> {
  const externalId = await findActivePolarSubscriptionId();
  if (!externalId) return { ok: false, error: "No subscription to resume." };
  const res = await uncancelSubscription(externalId);
  if (!res.ok) return { ok: false, error: friendlyPolarError(res.error, res.status) };
  revalidatePath("/settings/billing");
  return { ok: true };
}


const switchSchema = z.object({
  tier: z.enum(["pro", "max"]),
  interval: z.enum(["monthly", "annual"]),
});


export async function switchTierAction(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = switchSchema.safeParse({
    tier: (formData.get("tier") ?? "").toString() as TierKey,
    interval: (formData.get("interval") ?? "").toString() as IntervalKey,
  });
  if (!parsed.success) return { ok: false, error: "Pick a tier and an interval." };

  const externalId = await findActivePolarSubscriptionId();
  if (!externalId) return { ok: false, error: "No active subscription to switch." };

  const res = await changeSubscriptionProduct(
    externalId,
    parsed.data.tier,
    parsed.data.interval,
  );
  if (!res.ok) return { ok: false, error: friendlyPolarError(res.error, res.status) };
  revalidatePath("/settings/billing");
  return { ok: true };
}


function friendlyPolarError(error: string, status: number): string {
  if (error === "polar_disabled") return "Payments aren't live yet.";
  if (error === "polar_access_token_unset") return "Polar access token isn't configured.";
  if (error.startsWith("polar_product_unset")) return "That product isn't configured yet.";
  if (error === "polar_network") return "Couldn't reach Polar. Try again in a minute.";
  return `Request failed (${status}).`;
}
