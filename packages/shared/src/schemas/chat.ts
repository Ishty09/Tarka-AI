import { z } from "zod";
import {
  conversationModeSchema,
  messageRoleSchema,
  safetyVerdictSchema,
} from "./enums";

// jsonb columns surface as arbitrary JSON; consumers narrow further as needed.
const jsonObject = z.record(z.string(), z.unknown());

// §6.1 conversations
export const conversationsRowSchema = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  persona_id: z.string().uuid(),
  mode: conversationModeSchema,
  title: z.string().nullable(),
  archived: z.boolean(),
  couple_link_id: z.string().uuid().nullable(),
  group_room_id: z.string().uuid().nullable(),
  metadata: jsonObject.nullable(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type ConversationsRow = z.infer<typeof conversationsRowSchema>;

// §6.1 messages (id is bigserial — values up to 2^53 - 1 fit a JS number safely).
export const messagesRowSchema = z.object({
  id: z.number().int().nonnegative(),
  conversation_id: z.string().uuid(),
  user_id: z.string().uuid().nullable(),
  role: messageRoleSchema,
  content: z.string(),
  redacted_content: z.string().nullable(),
  model: z.string().nullable(),
  input_tokens: z.number().int().nonnegative().nullable(),
  output_tokens: z.number().int().nonnegative().nullable(),
  cached_input_tokens: z.number().int().nonnegative().nullable(),
  safety_verdict: safetyVerdictSchema.nullable(),
  latency_ms: z.number().int().nonnegative().nullable(),
  langfuse_trace_id: z.string().nullable(),
  metadata: jsonObject.nullable(),
  created_at: z.string().datetime(),
});
export type MessagesRow = z.infer<typeof messagesRowSchema>;
