// OpenAI-compatible wire types we actually use. LiteLLM exposes the OpenAI
// shape (§7.1), so this file mirrors that subset without pulling in
// `openai`/`@anthropic-ai/sdk` (forbidden by §1 rule 4).

import { z } from "zod";

// ----- Messages --------------------------------------------------------------
//
// Anthropic-style `cache_control` is supported by LiteLLM as a passthrough
// content-block annotation; OpenAI prompt caching is automatic at the proxy
// level. We expose both surface shapes.

export type ContentBlock =
  | {
      type: "text";
      text: string;
      cache_control?: { type: "ephemeral" };
    }
  | { type: "image_url"; image_url: { url: string } };

export interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  /** String for the common case; array of blocks when caching segments. */
  content: string | ContentBlock[];
  name?: string;
  tool_call_id?: string;
}

// ----- Request / response ----------------------------------------------------

export interface ChatRequest {
  /** Quarrel virtual model name from QUARREL_MODELS. */
  model: string;
  messages: ChatMessage[];
  temperature?: number;
  max_tokens?: number;
  /** When set, asks the model for JSON. Pair with jsonChat to also parse. */
  response_format?: { type: "json_object" } | { type: "text" };
  /** Stops emitted at first match — used by tools that frame their output. */
  stop?: string[];
  /** Langfuse passes user_id / session_id through extra body params. */
  user?: string;
  metadata?: Record<string, unknown>;
}

export interface ChatUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  /**
   * Cached input tokens as reported by OpenAI prompt caching. Surfaces as
   * `prompt_tokens_details.cached_tokens`; we hoist it for ergonomics.
   */
  cached_tokens?: number;
}

export interface ChatChoice {
  index: number;
  message: ChatMessage;
  finish_reason: "stop" | "length" | "tool_calls" | "content_filter" | string;
}

export interface ChatResponse {
  id: string;
  object: "chat.completion";
  created: number;
  model: string;
  choices: ChatChoice[];
  usage: ChatUsage;
}

// ----- Streaming -------------------------------------------------------------

export interface ChatStreamDelta {
  /** Accumulated text delta for the chosen index (we don't support n>1). */
  delta: string;
  finish_reason?: string;
  /** Final usage block — emitted by LiteLLM on the last chunk. */
  usage?: ChatUsage;
  raw: unknown;
}

// ----- Embeddings ------------------------------------------------------------

export interface EmbedRequest {
  model: string;
  input: string | string[];
  user?: string;
}

export interface EmbedResponse {
  object: "list";
  data: Array<{ object: "embedding"; index: number; embedding: number[] }>;
  model: string;
  usage: { prompt_tokens: number; total_tokens: number };
}

// ----- Schemas (runtime guards on responses we parse defensively) -----------

export const chatResponseSchema: z.ZodType<ChatResponse> = z.object({
  id: z.string(),
  object: z.literal("chat.completion"),
  created: z.number(),
  model: z.string(),
  choices: z.array(
    z.object({
      index: z.number(),
      message: z.object({
        role: z.enum(["system", "user", "assistant", "tool"]),
        content: z.union([z.string(), z.array(z.any())]),
        name: z.string().optional(),
        tool_call_id: z.string().optional(),
      }) as unknown as z.ZodType<ChatMessage>,
      finish_reason: z.string(),
    }),
  ),
  usage: z.object({
    prompt_tokens: z.number().int().nonnegative(),
    completion_tokens: z.number().int().nonnegative(),
    total_tokens: z.number().int().nonnegative(),
    cached_tokens: z.number().int().nonnegative().optional(),
  }),
});

export const embedResponseSchema: z.ZodType<EmbedResponse> = z.object({
  object: z.literal("list"),
  data: z.array(
    z.object({
      object: z.literal("embedding"),
      index: z.number().int().nonnegative(),
      embedding: z.array(z.number()),
    }),
  ),
  model: z.string(),
  usage: z.object({
    prompt_tokens: z.number().int().nonnegative(),
    total_tokens: z.number().int().nonnegative(),
  }),
});
