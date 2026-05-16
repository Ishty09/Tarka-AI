// CLAUDE.md §7.6 caching helpers.
//
// LiteLLM passes Anthropic `cache_control` annotations through to Claude;
// OpenAI prompt caching is automatic on identical leading content. So a single
// content shape — text block + optional cache_control — works for both
// providers, and the proxy strips the annotation before forwarding to OpenAI.
//
// Strategy targets:
//   - system prompt + persona overlay → 1-hour TTL (mark "static")
//   - user facts bundle               → 5-min TTL (mark "userFacts")
//   - conversation history            → no marker (let provider auto-cache)
//
// Anthropic's ephemeral cache TTL is currently 5 minutes; their 1-hour beta
// is not in the locked stack. So both `static` and `userFacts` use ephemeral
// for now — the helper exists so we can swap in 1h cache without touching
// callers when Anthropic ships it. OpenAI prompt caching handles the longer
// reuse window automatically.

import type { ChatMessage, ContentBlock } from "./types";

/**
 * Wrap a plain string into a single text content block with a cache-control
 * marker. Use for the anti-sycophant base prompt + persona overlay (the
 * "static" leading segment that should hit the cache on every turn).
 */
export function staticCacheBlock(text: string): ContentBlock[] {
  return [{ type: "text", text, cache_control: { type: "ephemeral" } }];
}

/**
 * Same shape as `staticCacheBlock` but semantically tagged for the user-facts
 * bundle. Kept as a distinct helper so future per-segment TTL config doesn't
 * require a callsite migration.
 */
export function userFactsCacheBlock(text: string): ContentBlock[] {
  return [{ type: "text", text, cache_control: { type: "ephemeral" } }];
}

/**
 * Compose the system message used at the head of every chat turn (§7.3 + §7.4).
 *
 * @param antiSycophantBase - verbatim §7.3 string
 * @param personaOverlay    - rendered §7.4 block for the active persona
 * @param userFacts         - serialized facts/contradictions block, or null
 */
export function buildSystemMessage(
  antiSycophantBase: string,
  personaOverlay: string,
  userFacts: string | null,
): ChatMessage {
  const blocks: ContentBlock[] = [
    // Single cached segment for the long-lived system+persona prefix.
    {
      type: "text",
      text: `${antiSycophantBase}\n\n${personaOverlay}`,
      cache_control: { type: "ephemeral" },
    },
  ];
  if (userFacts) {
    blocks.push({
      type: "text",
      text: `<user_facts>\n${userFacts}\n</user_facts>`,
      cache_control: { type: "ephemeral" },
    });
  }
  return { role: "system", content: blocks };
}
