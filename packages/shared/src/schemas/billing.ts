import { z } from "zod";
import {
  paidTierSchema,
  subscriptionSourceSchema,
  subscriptionStatusSchema,
} from "./enums";

// §6.5 subscriptions
export const subscriptionsRowSchema = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  tier: paidTierSchema,
  status: subscriptionStatusSchema,
  source: subscriptionSourceSchema,
  external_subscription_id: z.string(),
  current_period_start: z.string().datetime(),
  current_period_end: z.string().datetime(),
  cancel_at_period_end: z.boolean(),
  canceled_at: z.string().datetime().nullable(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type SubscriptionsRow = z.infer<typeof subscriptionsRowSchema>;

// §6.5 usage_quotas (composite PK on (user_id, period_start))
export const usageQuotasRowSchema = z.object({
  user_id: z.string().uuid(),
  period_start: z.string().date(),
  messages_used: z.number().int().nonnegative(),
  council_runs_used: z.number().int().nonnegative(),
  voice_seconds_used: z.number().int().nonnegative(),
  voice_clips_exported: z.number().int().nonnegative(),
  roast_feed_posts_used: z.number().int().nonnegative(),
  active_personas: z.number().int().nonnegative(),
  active_wagers: z.number().int().nonnegative(),
});
export type UsageQuotasRow = z.infer<typeof usageQuotasRowSchema>;

// §6.5 idempotency_keys (internal — only apps/workers touches it)
export const idempotencyKeysRowSchema = z.object({
  key: z.string(),
  scope: z.string(),
  user_id: z.string().uuid().nullable(),
  payload_hash: z.string(),
  response_status: z.number().int().nullable(),
  response_body: z.unknown().nullable(),
  created_at: z.string().datetime(),
  expires_at: z.string().datetime(),
});
export type IdempotencyKeysRow = z.infer<typeof idempotencyKeysRowSchema>;
