import { z } from "zod";
import { llmSafetyVerdictSchema } from "../enums";

// §7.5 safety classifier output. The model is instructed to emit ONLY this
// JSON object (no prose). Parse with .safeParse and treat parse failure as
// verdict='safe' is NOT acceptable — fall through to a defensive deny instead
// (handled in apps/workers/services/safety.py).

export const piiCategorySchema = z.enum(["phone", "email", "address", "id", "cc"]);
export type PiiCategory = z.infer<typeof piiCategorySchema>;

export const safetyScreenRedactionSchema = z.object({
  start: z.number().int().nonnegative(),
  end: z.number().int().nonnegative(),
  category: piiCategorySchema,
});
export type SafetyScreenRedaction = z.infer<typeof safetyScreenRedactionSchema>;

export const safetyScreenResultSchema = z.object({
  verdict: llmSafetyVerdictSchema,
  confidence: z.number().min(0).max(1),
  reason: z.string(),
  redactions: z.array(safetyScreenRedactionSchema),
});
export type SafetyScreenResult = z.infer<typeof safetyScreenResultSchema>;
