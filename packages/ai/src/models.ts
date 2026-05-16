// CLAUDE.md §7.1 model_name values. These strings MUST match the LiteLLM
// proxy config at infra/litellm-config.yaml — they're the virtual model
// identifiers the proxy resolves to OpenAI or Anthropic via fallback.

export const QUARREL_MODELS = {
  /** Reasoning-grade. GPT-5 with Claude Sonnet 4.6 fallback. */
  argue: "quarrel-argue",
  /** Cheap classifier tier. GPT-5-mini with Claude Haiku 4.5 fallback. */
  cheap: "quarrel-cheap",
  /** OpenAI text-embedding-3-small (1536 dims — see schemas/memory.ts). */
  embed: "quarrel-embed",
} as const;

export type QuarrelModel = (typeof QUARREL_MODELS)[keyof typeof QUARREL_MODELS];

/** Dimensionality of `quarrel-embed` output — matches user_facts.embedding. */
export const EMBEDDING_DIMS = 1536;
