import { z } from "zod";
import {
  ageRangeSchema,
  ageVerificationMethodSchema,
  moderationStatusSchema,
  personaCategorySchema,
  personaVisibilitySchema,
  tierSchema,
  tierSourceSchema,
  voiceProviderSchema,
} from "./enums";

// §6.1 profiles
export const profilesRowSchema = z.object({
  id: z.string().uuid(),
  username: z.string().min(3).max(30),
  display_name: z.string().nullable(),
  avatar_url: z.string().nullable(),
  locale: z.string(),
  country_code: z.string(),
  timezone: z.string(),
  age_range: ageRangeSchema.nullable(),
  age_verified_at: z.string().datetime().nullable(),
  age_verification_method: ageVerificationMethodSchema.nullable(),
  tier: tierSchema,
  tier_source: tierSourceSchema.nullable(),
  onboarding_completed_at: z.string().datetime().nullable(),
  daily_roast_time: z.string().nullable(),
  daily_roast_persona_slug: z.string().nullable(),
  emergency_contact_email: z.string().email().nullable(),
  emergency_contact_name: z.string().nullable(),
  notification_email: z.boolean(),
  notification_push: z.boolean(),
  marketing_email_consent: z.boolean(),
  is_admin: z.boolean(),
  is_suspended: z.boolean(),
  suspension_reason: z.string().nullable(),
  data_deletion_requested_at: z.string().datetime().nullable(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type ProfilesRow = z.infer<typeof profilesRowSchema>;

// §6.1 personas
export const personasRowSchema = z.object({
  id: z.string().uuid(),
  slug: z.string(),
  owner_id: z.string().uuid().nullable(),
  name: z.string(),
  description: z.string().nullable(),
  locale: z.string(),
  cultural_tag: z.string().nullable(),
  category: personaCategorySchema,
  system_prompt: z.string(),
  voice_id: z.string().nullable(),
  voice_provider: voiceProviderSchema.nullable(),
  visibility: personaVisibilitySchema,
  price_cents: z.number().int().nonnegative(),
  install_count: z.number().int().nonnegative(),
  rating_avg: z.number().min(0).max(5).nullable(),
  rating_count: z.number().int().nonnegative(),
  is_safe: z.boolean(),
  moderation_status: moderationStatusSchema,
  moderation_notes: z.string().nullable(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type PersonasRow = z.infer<typeof personasRowSchema>;
