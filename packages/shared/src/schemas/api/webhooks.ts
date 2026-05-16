import { z } from "zod";

// Webhook payloads we *do* handle. Signature verification (HMAC-SHA256 per §3)
// happens before parsing in apps/web/api/webhooks/*; these schemas validate
// the post-verification body. Vendor docs may add fields — schemas allow that
// via .passthrough() so unknown fields don't fail parsing.

// ----- Polar -----------------------------------------------------------------

const polarSubscriptionData = z
  .object({
    id: z.string(),
    customer_id: z.string(),
    product_id: z.string(),
    status: z.enum(["active", "past_due", "canceled", "paused", "trialing"]),
    current_period_start: z.string().datetime(),
    current_period_end: z.string().datetime(),
    cancel_at_period_end: z.boolean().optional(),
    canceled_at: z.string().datetime().nullable().optional(),
    metadata: z.record(z.string(), z.unknown()).optional(),
  })
  .passthrough();
export type PolarSubscriptionData = z.infer<typeof polarSubscriptionData>;

export const polarSubscriptionEventSchema = z
  .object({
    type: z.enum([
      "subscription.created",
      "subscription.updated",
      "subscription.canceled",
      "subscription.past_due",
    ]),
    data: polarSubscriptionData,
  })
  .passthrough();
export type PolarSubscriptionEvent = z.infer<typeof polarSubscriptionEventSchema>;

// Wager funding via Polar checkout (§9.5.5). `order` is the auth-and-capture
// envelope; `paid` fires when the authorization succeeds.
export const polarOrderPaidEventSchema = z
  .object({
    type: z.literal("order.paid"),
    data: z
      .object({
        id: z.string(),
        customer_id: z.string(),
        amount: z.number().int().nonnegative(),
        currency: z.string(),
        status: z.string(),
        // Wager id is round-tripped through metadata so we can locate the row.
        metadata: z.record(z.string(), z.unknown()).optional(),
      })
      .passthrough(),
  })
  .passthrough();
export type PolarOrderPaidEvent = z.infer<typeof polarOrderPaidEventSchema>;

export const polarWebhookEventSchema = z.union([
  polarSubscriptionEventSchema,
  polarOrderPaidEventSchema,
]);
export type PolarWebhookEvent = z.infer<typeof polarWebhookEventSchema>;

// ----- RevenueCat ------------------------------------------------------------
// Docs: https://www.revenuecat.com/docs/integrations/webhooks/event-types

const revenueCatEventBase = z
  .object({
    id: z.string(),
    type: z.enum([
      "INITIAL_PURCHASE",
      "RENEWAL",
      "PRODUCT_CHANGE",
      "CANCELLATION",
      "UNCANCELLATION",
      "EXPIRATION",
      "BILLING_ISSUE",
      "SUBSCRIBER_ALIAS",
    ]),
    app_user_id: z.string(),
    original_app_user_id: z.string().optional(),
    product_id: z.string().optional(),
    period_type: z.string().optional(),
    purchased_at_ms: z.number().int().optional(),
    expiration_at_ms: z.number().int().nullable().optional(),
    environment: z.enum(["SANDBOX", "PRODUCTION"]).optional(),
    store: z.enum(["APP_STORE", "PLAY_STORE", "PROMOTIONAL", "AMAZON", "STRIPE"]).optional(),
  })
  .passthrough();

export const revenueCatWebhookEventSchema = z
  .object({
    event: revenueCatEventBase,
    api_version: z.string().optional(),
  })
  .passthrough();
export type RevenueCatWebhookEvent = z.infer<typeof revenueCatWebhookEventSchema>;
