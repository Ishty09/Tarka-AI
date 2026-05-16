import { z } from "zod";
import {
  antiCharityIdeologicalTagSchema,
  wagerCheckinStatusSchema,
  wagerStatusSchema,
} from "./enums";

// §6.4 anti_charities
export const antiCharitiesRowSchema = z.object({
  slug: z.string(),
  name: z.string(),
  description: z.string(),
  url: z.string().url(),
  ideological_tag: antiCharityIdeologicalTagSchema,
  active: z.boolean(),
});
export type AntiCharitiesRow = z.infer<typeof antiCharitiesRowSchema>;

// §6.4 wagers — stake_cents in [500, 100000], end_at > start_at (DB CHECK).
export const wagersRowSchema = z
  .object({
    id: z.string().uuid(),
    user_id: z.string().uuid(),
    goal: z.string(),
    stake_cents: z.number().int().min(500).max(100_000),
    currency: z.string(),
    anti_charity_slug: z.string(),
    referee_id: z.string().uuid().nullable(),
    start_at: z.string().date(),
    end_at: z.string().date(),
    status: wagerStatusSchema,
    polar_payment_id: z.string().nullable(),
    polar_charge_id: z.string().nullable(),
    evaluation_notes: z.string().nullable(),
    evaluated_at: z.string().datetime().nullable(),
    disputed_at: z.string().datetime().nullable(),
    dispute_resolution: z.string().nullable(),
    created_at: z.string().datetime(),
  })
  .refine((w) => w.end_at > w.start_at, {
    message: "end_at must be strictly after start_at",
    path: ["end_at"],
  });
export type WagersRow = z.infer<typeof wagersRowSchema>;

// §6.4 wager_checkins
export const wagerCheckinsRowSchema = z.object({
  id: z.number().int().nonnegative(),
  wager_id: z.string().uuid(),
  user_id: z.string().uuid(),
  checkin_date: z.string().date(),
  status: wagerCheckinStatusSchema,
  notes: z.string().nullable(),
  proof_url: z.string().nullable(),
  created_at: z.string().datetime(),
});
export type WagerCheckinsRow = z.infer<typeof wagerCheckinsRowSchema>;

// §6.4 streaks
export const streaksRowSchema = z.object({
  id: z.number().int().nonnegative(),
  user_id: z.string().uuid(),
  habit: z.string(),
  current_streak: z.number().int().nonnegative(),
  longest_streak: z.number().int().nonnegative(),
  last_checkin_at: z.string().date().nullable(),
  created_at: z.string().datetime(),
});
export type StreaksRow = z.infer<typeof streaksRowSchema>;
