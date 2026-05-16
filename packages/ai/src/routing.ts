// CLAUDE.md §7.2 task-to-model routing table. Every place we call the LLM,
// we name the *task* and let this map pick the model — so the §3 stack rule
// "no direct OpenAI / Anthropic calls" is enforced by routing, not by manual
// model strings sprinkled through the codebase.

import { QUARREL_MODELS, type QuarrelModel } from "./models";

export const LLM_TASKS = [
  // Reasoning tier — quarrel-argue
  "argue",
  "roast",
  "mediate",
  "council_member",
  "council_judge",
  "contradiction_detection",
  "mirror_mode",
  "eulogy",
  "decision_killer",
  "cope_detector",
  "steelman",
  "past_self",
  "future_self",
  "negotiation_sparring",
  "breakup_analyzer",

  // Cheap tier — quarrel-cheap
  "fact_extraction",
  "title_generation",
  "safety_screen",
  "persona_moderation",
  "feed_moderation",
  "drill_sergeant",
  "daily_roast",

  // Embedding tier — quarrel-embed
  "embedding",
] as const;
export type LlmTask = (typeof LLM_TASKS)[number];

export const TASK_MODEL: Record<LlmTask, QuarrelModel> = {
  // §7.2 row "Argue / Roast / Mediate / Council main reply"
  argue: QUARREL_MODELS.argue,
  roast: QUARREL_MODELS.argue,
  mediate: QUARREL_MODELS.argue,
  council_member: QUARREL_MODELS.argue,
  council_judge: QUARREL_MODELS.argue,
  // §7.2 row "Contradiction detection (nightly batch)"
  contradiction_detection: QUARREL_MODELS.argue,
  // §7.2 row "Mirror Mode weekly report"
  mirror_mode: QUARREL_MODELS.argue,
  // §7.2 row "Eulogy quarterly"
  eulogy: QUARREL_MODELS.argue,
  // §7.2 row "Decision Killer / Cope Detector / Steelman tools"
  decision_killer: QUARREL_MODELS.argue,
  cope_detector: QUARREL_MODELS.argue,
  steelman: QUARREL_MODELS.argue,
  // Past/Future Self + Negotiation + Breakup are in the same family (§9.1.5,
  // §9.1.6, §9.5.3, §9.3.3) — they need reasoning, not classification.
  past_self: QUARREL_MODELS.argue,
  future_self: QUARREL_MODELS.argue,
  negotiation_sparring: QUARREL_MODELS.argue,
  breakup_analyzer: QUARREL_MODELS.argue,

  // §7.2 row "Fact extraction from user messages"
  fact_extraction: QUARREL_MODELS.cheap,
  // §7.2 row "Title generation"
  title_generation: QUARREL_MODELS.cheap,
  // §7.2 row "Safety screen classification"
  safety_screen: QUARREL_MODELS.cheap,
  // §7.2 row "Moderation of personas + roast feed posts"
  persona_moderation: QUARREL_MODELS.cheap,
  feed_moderation: QUARREL_MODELS.cheap,
  // §7.2 row "Drill Sergeant streak punishment (high volume)"
  drill_sergeant: QUARREL_MODELS.cheap,
  // §9.2.1 push notification copy — high volume, fits cheap tier
  daily_roast: QUARREL_MODELS.cheap,

  // §7.2 row "Embeddings"
  embedding: QUARREL_MODELS.embed,
};

export function modelForTask(task: LlmTask): QuarrelModel {
  return TASK_MODEL[task];
}
