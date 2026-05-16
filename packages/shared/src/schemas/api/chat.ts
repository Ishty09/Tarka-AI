import { z } from "zod";
import { conversationModeSchema } from "../enums";

// Wire shape for apps/web/api/chat/stream -> apps/workers POST /chat/stream.
// Streaming response is SSE (Vercel AI SDK), not modelled here.

export const chatStreamRequestSchema = z.object({
  conversation_id: z.string().uuid().nullable(),
  // Persona slug is preferred when starting a brand-new conversation; once a
  // conversation exists the worker reads its persona_id off the row.
  persona_slug: z.string().nullable(),
  mode: conversationModeSchema,
  message: z.string().min(1).max(8000),
  // §1.11 idempotency: client mints a key per send; worker checks
  // idempotency_keys before doing work.
  idempotency_key: z.string().min(8).max(128),
  // Optional couple/group binding for shared conversations (§9.3.1, §9.3.4).
  couple_link_id: z.string().uuid().nullable().optional(),
  group_room_id: z.string().uuid().nullable().optional(),
});
export type ChatStreamRequest = z.infer<typeof chatStreamRequestSchema>;

// 429 over-quota response payload (§8.3 step 3).
export const chatQuotaExceededSchema = z.object({
  error: z.literal("quota_exceeded"),
  tier: z.string(),
  limit: z.number().int().nonnegative(),
  used: z.number().int().nonnegative(),
  reset_at: z.string().datetime(),
  upgrade_url: z.string().url().nullable(),
});
export type ChatQuotaExceeded = z.infer<typeof chatQuotaExceededSchema>;
