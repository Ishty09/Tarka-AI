import { z } from "zod";
import { userFactCategorySchema } from "./enums";

// §6.2 user_facts. embedding is vector(1536); the Supabase JS client returns
// it as number[] when selected, but most reads will omit the column.
export const userFactsRowSchema = z.object({
  id: z.number().int().nonnegative(),
  user_id: z.string().uuid(),
  fact: z.string(),
  embedding: z.array(z.number()).length(1536).nullable(),
  source_message_id: z.number().int().nonnegative().nullable(),
  confidence: z.number().min(0).max(1),
  category: userFactCategorySchema.nullable(),
  superseded_by: z.number().int().nonnegative().nullable(),
  is_active: z.boolean(),
  created_at: z.string().datetime(),
});
export type UserFactsRow = z.infer<typeof userFactsRowSchema>;

// §6.2 contradictions
export const contradictionsRowSchema = z.object({
  id: z.number().int().nonnegative(),
  user_id: z.string().uuid(),
  fact_a_id: z.number().int().nonnegative(),
  fact_b_id: z.number().int().nonnegative(),
  severity: z.number().min(0).max(10),
  summary: z.string(),
  surfaced_at: z.string().datetime().nullable(),
  acknowledged_at: z.string().datetime().nullable(),
  dismissed_at: z.string().datetime().nullable(),
  created_at: z.string().datetime(),
});
export type ContradictionsRow = z.infer<typeof contradictionsRowSchema>;

// §6.2 mirror_reports. patterns / dodges payloads aren't fully nailed down in
// §9.4.2 yet, so we accept arbitrary JSON arrays/objects until the generator
// job settles on a shape.
export const mirrorReportPatternsSchema = z.unknown();
export const mirrorReportDodgesSchema = z.unknown();

export const mirrorReportsRowSchema = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  period_start: z.string().date(),
  period_end: z.string().date(),
  summary: z.string(),
  patterns: mirrorReportPatternsSchema,
  dodges: mirrorReportDodgesSchema,
  generated_at: z.string().datetime(),
  viewed_at: z.string().datetime().nullable(),
});
export type MirrorReportsRow = z.infer<typeof mirrorReportsRowSchema>;

// §6.2 eulogy_reports. quarter is a freeform tag (e.g. "2026-Q2").
export const eulogyReportsRowSchema = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  quarter: z.string(),
  content: z.string(),
  generated_at: z.string().datetime(),
  viewed_at: z.string().datetime().nullable(),
});
export type EulogyReportsRow = z.infer<typeof eulogyReportsRowSchema>;
