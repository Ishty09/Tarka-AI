import { z } from "zod";
import {
  crisisContextTagSchema,
  pushPlatformSchema,
  safetyIncidentCategorySchema,
} from "./enums";

// §6.6 push_subscriptions
export const pushSubscriptionsRowSchema = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  platform: pushPlatformSchema,
  token: z.string(),
  device_label: z.string().nullable(),
  last_seen_at: z.string().datetime(),
  created_at: z.string().datetime(),
});
export type PushSubscriptionsRow = z.infer<typeof pushSubscriptionsRowSchema>;

// §6.6 crisis_hotlines (composite PK on (locale, country_code, context_tag))
export const crisisHotlinesRowSchema = z.object({
  locale: z.string(),
  country_code: z.string(),
  name: z.string(),
  phone: z.string().nullable(),
  url: z.string().url().nullable(),
  context_tag: crisisContextTagSchema,
});
export type CrisisHotlinesRow = z.infer<typeof crisisHotlinesRowSchema>;

// §6.6 safety_incidents
export const safetyIncidentsRowSchema = z.object({
  id: z.number().int().nonnegative(),
  user_id: z.string().uuid().nullable(),
  message_id: z.number().int().nonnegative().nullable(),
  conversation_id: z.string().uuid().nullable(),
  category: safetyIncidentCategorySchema,
  verdict: z.string(),
  action_taken: z.string(),
  reviewed_by: z.string().uuid().nullable(),
  reviewed_at: z.string().datetime().nullable(),
  created_at: z.string().datetime(),
});
export type SafetyIncidentsRow = z.infer<typeof safetyIncidentsRowSchema>;

// §6.6 audit_log
export const auditLogRowSchema = z.object({
  id: z.number().int().nonnegative(),
  actor_user_id: z.string().uuid().nullable(),
  action: z.string(),
  entity_type: z.string(),
  entity_id: z.string(),
  metadata: z.record(z.string(), z.unknown()).nullable(),
  ip_address: z.string().nullable(),
  user_agent: z.string().nullable(),
  created_at: z.string().datetime(),
});
export type AuditLogRow = z.infer<typeof auditLogRowSchema>;
