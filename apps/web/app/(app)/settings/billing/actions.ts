"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { createServerSupabase } from "@/lib/supabase/server";
import {
  createCheckout,
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
    // Surface dev-friendly text for the known "off" states; let unknown
    // upstream errors flow through verbatim.
    const friendly =
      result.error === "polar_disabled"
        ? "Payments aren't live yet."
        : result.error === "polar_access_token_unset"
          ? "Polar access token isn't configured."
          : result.error.startsWith("polar_product_unset")
            ? "That product isn't configured yet."
            : null;
    return { ok: false, error: friendly ?? `Checkout failed (${result.status}).` };
  }

  redirect(result.url);
}
