// CLAUDE.md §21 — every LLM call wraps in a Langfuse trace.
//
// We don't import langfuse-node here (it would force apps/web to bundle it).
// Instead, we shape the metadata LiteLLM forwards to Langfuse via its
// success_callback, so the proxy-side Langfuse integration tags traces with
// the same fields whether the call originates from web, workers, or a job.

import type { LlmTask } from "./routing";
import type { RequestOptions } from "./client";

export interface TraceInput {
  /** §21 `name` — defaults to the task (e.g. `argue.devils_advocate`). */
  task: LlmTask;
  persona_slug?: string;
  user_id: string;
  conversation_id?: string;
  tier: "free" | "pro" | "max";
  locale: string;
  extra?: Record<string, unknown>;
}

export function buildTrace(input: TraceInput): NonNullable<RequestOptions["trace"]> {
  const name =
    input.persona_slug && input.task.startsWith("argue")
      ? `${input.task}.${input.persona_slug}`
      : input.task;

  return {
    name,
    user_id: input.user_id,
    session_id: input.conversation_id,
    tags: [
      input.task,
      `tier:${input.tier}`,
      `locale:${input.locale}`,
      ...(input.persona_slug ? [`persona:${input.persona_slug}`] : []),
    ],
    metadata: {
      task: input.task,
      tier: input.tier,
      locale: input.locale,
      ...(input.persona_slug ? { persona_slug: input.persona_slug } : {}),
      ...(input.extra ?? {}),
    },
  };
}
