import { z } from "zod";
import { userFactCategorySchema } from "../enums";

// Fact extraction output (Phase C step 13). One LLM call per user turn,
// returns 0-N facts plus optional supersession pointers.
export const extractedFactSchema = z.object({
  fact: z.string().min(1).max(500),
  category: userFactCategorySchema,
  confidence: z.number().min(0).max(1),
  // If this fact supersedes an existing one, the previous fact's id goes here.
  supersedes_fact_id: z.number().int().nonnegative().nullable(),
});
export type ExtractedFact = z.infer<typeof extractedFactSchema>;

export const factExtractionResultSchema = z.object({
  facts: z.array(extractedFactSchema),
});
export type FactExtractionResult = z.infer<typeof factExtractionResultSchema>;
