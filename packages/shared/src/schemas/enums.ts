import { z } from "zod";

// CHECK-constraint mirrors. Keep in lockstep with supabase/migrations/*.
// Run-time validation everywhere; the `*Schema` is canonical, the type is its inference.

export const ageRangeSchema = z.enum(["under_16", "16_17", "18_plus"]);
export type AgeRange = z.infer<typeof ageRangeSchema>;

export const ageVerificationMethodSchema = z.enum([
  "apple_age_api",
  "google_age",
  "self_declared",
  "third_party",
]);
export type AgeVerificationMethod = z.infer<typeof ageVerificationMethodSchema>;

export const tierSchema = z.enum(["free", "pro", "max"]);
export type Tier = z.infer<typeof tierSchema>;

export const paidTierSchema = z.enum(["pro", "max"]);
export type PaidTier = z.infer<typeof paidTierSchema>;

export const tierSourceSchema = z.enum([
  "polar",
  "revenuecat_ios",
  "revenuecat_android",
  "manual",
]);
export type TierSource = z.infer<typeof tierSourceSchema>;

export const personaCategorySchema = z.enum([
  "argue",
  "roast",
  "mediate",
  "council",
  "productivity",
  "cultural",
]);
export type PersonaCategory = z.infer<typeof personaCategorySchema>;

export const voiceProviderSchema = z.enum(["chatterbox", "elevenlabs", "openai"]);
export type VoiceProvider = z.infer<typeof voiceProviderSchema>;

export const personaVisibilitySchema = z.enum([
  "private",
  "unlisted",
  "public",
  "official",
]);
export type PersonaVisibility = z.infer<typeof personaVisibilitySchema>;

export const moderationStatusSchema = z.enum([
  "pending",
  "approved",
  "rejected",
  "flagged",
]);
export type ModerationStatus = z.infer<typeof moderationStatusSchema>;

export const conversationModeSchema = z.enum([
  "argue",
  "roast",
  "mediate",
  "council",
  "negotiate",
  "custom",
  "roast_my_x",
  "decision_killer",
  "cope_detector",
  "steelman",
  "future_self",
  "past_self",
  "drill_sergeant",
]);
export type ConversationMode = z.infer<typeof conversationModeSchema>;

export const messageRoleSchema = z.enum(["user", "assistant", "tool", "system"]);
export type MessageRole = z.infer<typeof messageRoleSchema>;

// As stored in messages.safety_verdict — includes 'redacted' which is the
// post-redaction stamp applied by the worker, not a verdict the LLM returns.
export const safetyVerdictSchema = z.enum([
  "safe",
  "crisis",
  "abuse",
  "minor_self_sexualization",
  "jailbreak",
  "redacted",
]);
export type SafetyVerdict = z.infer<typeof safetyVerdictSchema>;

// What the §7.5 safety classifier may return (no "redacted").
export const llmSafetyVerdictSchema = z.enum([
  "safe",
  "crisis",
  "abuse",
  "minor_self_sexualization",
  "jailbreak",
]);
export type LlmSafetyVerdict = z.infer<typeof llmSafetyVerdictSchema>;

export const userFactCategorySchema = z.enum([
  "belief",
  "goal",
  "preference",
  "identity",
  "history",
  "commitment",
  "rationalization",
]);
export type UserFactCategory = z.infer<typeof userFactCategorySchema>;

export const coupleLinkStatusSchema = z.enum([
  "pending",
  "active",
  "revoked",
  "expired",
]);
export type CoupleLinkStatus = z.infer<typeof coupleLinkStatusSchema>;

export const groupMemberRoleSchema = z.enum(["owner", "member"]);
export type GroupMemberRole = z.infer<typeof groupMemberRoleSchema>;

export const roastFeedVisibilitySchema = z.enum(["public", "unlisted", "removed"]);
export type RoastFeedVisibility = z.infer<typeof roastFeedVisibilitySchema>;

export const antiCharityIdeologicalTagSchema = z.enum([
  "progressive_us",
  "conservative_us",
  "centrist",
  "religious_christian",
  "secular",
  "climate_action",
  "climate_skeptic",
  "gun_rights",
  "gun_control",
  "animal_welfare",
  "industry_lobby",
]);
export type AntiCharityIdeologicalTag = z.infer<typeof antiCharityIdeologicalTagSchema>;

export const wagerStatusSchema = z.enum([
  "pending",
  "active",
  "succeeded",
  "failed",
  "disputed",
  "refunded",
]);
export type WagerStatus = z.infer<typeof wagerStatusSchema>;

export const wagerCheckinStatusSchema = z.enum(["completed", "missed", "skipped"]);
export type WagerCheckinStatus = z.infer<typeof wagerCheckinStatusSchema>;

export const subscriptionStatusSchema = z.enum([
  "active",
  "past_due",
  "canceled",
  "paused",
  "trialing",
]);
export type SubscriptionStatus = z.infer<typeof subscriptionStatusSchema>;

export const subscriptionSourceSchema = z.enum([
  "polar",
  "revenuecat_ios",
  "revenuecat_android",
]);
export type SubscriptionSource = z.infer<typeof subscriptionSourceSchema>;

export const pushPlatformSchema = z.enum(["web", "ios", "android"]);
export type PushPlatform = z.infer<typeof pushPlatformSchema>;

export const crisisContextTagSchema = z.enum([
  "suicide",
  "abuse",
  "domestic_violence",
  "child_safety",
  "general",
]);
export type CrisisContextTag = z.infer<typeof crisisContextTagSchema>;

export const safetyIncidentCategorySchema = z.enum([
  "crisis",
  "abuse",
  "minor_self_sexualization",
  "jailbreak",
  "spam",
  "harassment",
]);
export type SafetyIncidentCategory = z.infer<typeof safetyIncidentCategorySchema>;
