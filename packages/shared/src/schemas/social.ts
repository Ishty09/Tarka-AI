import { z } from "zod";
import {
  coupleLinkStatusSchema,
  groupMemberRoleSchema,
  moderationStatusSchema,
  roastFeedVisibilitySchema,
} from "./enums";

// §6.3 couple_links
export const coupleLinksRowSchema = z.object({
  id: z.string().uuid(),
  user_a: z.string().uuid(),
  user_b: z.string().uuid().nullable(),
  invite_code: z.string().nullable(),
  invite_expires_at: z.string().datetime().nullable(),
  consent_a: z.boolean(),
  consent_b: z.boolean(),
  cross_fact_consent_a: z.boolean(),
  cross_fact_consent_b: z.boolean(),
  status: coupleLinkStatusSchema,
  revoked_at: z.string().datetime().nullable(),
  revoked_by: z.string().uuid().nullable(),
  created_at: z.string().datetime(),
});
export type CoupleLinksRow = z.infer<typeof coupleLinksRowSchema>;

// §6.3 group_rooms
export const groupRoomsRowSchema = z.object({
  id: z.string().uuid(),
  owner_id: z.string().uuid(),
  name: z.string(),
  invite_code: z.string(),
  max_members: z.number().int().positive(),
  mediator_persona_id: z.string().uuid().nullable(),
  archived: z.boolean(),
  created_at: z.string().datetime(),
});
export type GroupRoomsRow = z.infer<typeof groupRoomsRowSchema>;

// §6.3 group_members (composite PK)
export const groupMembersRowSchema = z.object({
  group_id: z.string().uuid(),
  user_id: z.string().uuid(),
  role: groupMemberRoleSchema,
  joined_at: z.string().datetime(),
});
export type GroupMembersRow = z.infer<typeof groupMembersRowSchema>;

// §6.3 roast_feed_posts
export const roastFeedPostsRowSchema = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  conversation_id: z.string().uuid(),
  message_id: z.number().int().nonnegative(),
  caption: z.string().nullable(),
  upvotes: z.number().int().nonnegative(),
  downvotes: z.number().int().nonnegative(),
  is_safe: z.boolean(),
  moderation_status: moderationStatusSchema,
  visibility: roastFeedVisibilitySchema,
  share_count: z.number().int().nonnegative(),
  created_at: z.string().datetime(),
});
export type RoastFeedPostsRow = z.infer<typeof roastFeedPostsRowSchema>;

// §6.3 roast_feed_votes (vote stored as smallint -1 | 1)
export const roastFeedVotesRowSchema = z.object({
  post_id: z.string().uuid(),
  user_id: z.string().uuid(),
  vote: z.union([z.literal(-1), z.literal(1)]),
  created_at: z.string().datetime(),
});
export type RoastFeedVotesRow = z.infer<typeof roastFeedVotesRowSchema>;
