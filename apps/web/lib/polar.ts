// Polar.sh checkout client (CLAUDE.md §3, §8.2).
//
// Polar is the Merchant of Record for web subscriptions. We never touch a
// card on our side — the user is redirected to a Polar-hosted checkout,
// and on completion Polar fires a webhook (handled in apps/workers, §27
// step 48) that flips our `subscriptions` row to status='active'.
//
// This module is server-only: the access token is the most sensitive
// secret in apps/web (after the Supabase service role, which lives only
// in apps/workers per §1.3).

import "server-only";
import { env, serverEnv } from "@/lib/env";
import { polarEnabled } from "@/lib/wagers";

export type TierKey = "pro" | "max";
export type IntervalKey = "monthly" | "annual";

interface ProductRef {
  tier: TierKey;
  interval: IntervalKey;
  productId: string;
}

function productCatalog(): ProductRef[] {
  return [
    {
      tier: "pro",
      interval: "monthly",
      productId: serverEnv.POLAR_PRODUCT_ID_PRO_MONTHLY,
    },
    {
      tier: "pro",
      interval: "annual",
      productId: serverEnv.POLAR_PRODUCT_ID_PRO_ANNUAL,
    },
    {
      tier: "max",
      interval: "monthly",
      productId: serverEnv.POLAR_PRODUCT_ID_MAX_MONTHLY,
    },
    {
      tier: "max",
      interval: "annual",
      productId: serverEnv.POLAR_PRODUCT_ID_MAX_ANNUAL,
    },
  ];
}

export function resolveProductId(tier: TierKey, interval: IntervalKey): string {
  const match = productCatalog().find(
    (p) => p.tier === tier && p.interval === interval,
  );
  return match?.productId ?? "";
}

export type CheckoutResult =
  | { ok: true; url: string }
  | { ok: false; status: number; error: string };

interface CreateCheckoutInput {
  tier: TierKey;
  interval: IntervalKey;
  userId: string;
  email: string;
  successPath?: string;
}

/**
 * Create a Polar hosted checkout for the given (tier, interval) pair.
 *
 * Returns `{ ok: false, error: 'polar_disabled' }` when ENABLE_POLAR is
 * unset — callers should surface a clear "payments aren't live yet"
 * notice rather than letting the user click into a 500.
 */
export async function createCheckout(
  input: CreateCheckoutInput,
): Promise<CheckoutResult> {
  if (!polarEnabled()) {
    return { ok: false, status: 503, error: "polar_disabled" };
  }
  if (!serverEnv.POLAR_ACCESS_TOKEN) {
    return { ok: false, status: 503, error: "polar_access_token_unset" };
  }
  const productId = resolveProductId(input.tier, input.interval);
  if (!productId) {
    return {
      ok: false,
      status: 503,
      error: `polar_product_unset_${input.tier}_${input.interval}`,
    };
  }

  const successUrl = new URL(
    input.successPath ?? "/settings/billing",
    env.NEXT_PUBLIC_APP_URL,
  );
  successUrl.searchParams.set("polar_status", "success");

  const body = {
    products: [productId],
    customer_email: input.email,
    success_url: successUrl.toString(),
    metadata: {
      user_id: input.userId,
      tier: input.tier,
      interval: input.interval,
    },
  };

  let resp: Response;
  try {
    resp = await fetch(`${serverEnv.POLAR_API_URL}/v1/checkouts/`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${serverEnv.POLAR_ACCESS_TOKEN}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return { ok: false, status: 502, error: "polar_network" };
  }

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    return { ok: false, status: resp.status, error: text || resp.statusText };
  }

  const json = (await resp.json()) as { url?: string };
  if (typeof json.url !== "string" || json.url.length === 0) {
    return { ok: false, status: 502, error: "polar_missing_url" };
  }
  return { ok: true, url: json.url };
}
