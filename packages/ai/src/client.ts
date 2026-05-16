// LiteLLM proxy client. Thin fetch wrapper — no SDK dependency, no streaming
// framework. Streaming returns an async iterator of deltas so callers (Vercel
// AI SDK, custom SSE relays, batch jobs) can adapt to their own protocol.
//
// CLAUDE.md §1.4: every LLM call from apps/web flows through this client.
// CLAUDE.md §7.6: cache_control blocks are forwarded verbatim — that's how
//                 Anthropic prompt caching is hinted via LiteLLM.

import type { z } from "zod";
import { LiteLLMError, LiteLLMNetworkError, LiteLLMSchemaError } from "./errors";
import {
  type ChatRequest,
  type ChatResponse,
  type ChatStreamDelta,
  type EmbedRequest,
  type EmbedResponse,
  chatResponseSchema,
  embedResponseSchema,
} from "./types";

export interface LiteLLMClientConfig {
  /** e.g. https://litellm.quarrel.ai — no trailing slash. */
  baseURL: string;
  /** LITELLM_MASTER_KEY from §5, or a per-tier virtual key from §23. */
  apiKey: string;
  /** Additional default headers (e.g. Langfuse passthrough). */
  defaultHeaders?: Record<string, string>;
  /** Per-request timeout in ms (default 60_000 per §7.1 request_timeout). */
  timeoutMs?: number;
  /** Injection point for tests. Defaults to global fetch. */
  fetch?: typeof fetch;
}

export interface LiteLLMClient {
  chat(req: ChatRequest, opts?: RequestOptions): Promise<ChatResponse>;
  chatStream(req: ChatRequest, opts?: RequestOptions): AsyncIterable<ChatStreamDelta>;
  embed(req: EmbedRequest, opts?: RequestOptions): Promise<EmbedResponse>;
  jsonChat<T>(
    req: ChatRequest,
    schema: z.ZodType<T>,
    opts?: RequestOptions,
  ): Promise<{ data: T; response: ChatResponse }>;
}

export interface RequestOptions {
  /** AbortSignal to cancel in-flight requests (request handler aborts). */
  signal?: AbortSignal;
  /** Langfuse passthrough — proxy reads these from `metadata`. */
  trace?: {
    name?: string;
    user_id?: string;
    session_id?: string;
    tags?: string[];
    metadata?: Record<string, unknown>;
  };
  /** Idempotency-Key header value (§1.11). */
  idempotencyKey?: string;
}

export function createLiteLLMClient(config: LiteLLMClientConfig): LiteLLMClient {
  const baseURL = config.baseURL.replace(/\/+$/, "");
  const fetchImpl = config.fetch ?? globalThis.fetch;
  const timeoutMs = config.timeoutMs ?? 60_000;

  function buildHeaders(opts?: RequestOptions): Headers {
    const h = new Headers({
      "content-type": "application/json",
      authorization: `Bearer ${config.apiKey}`,
      ...(config.defaultHeaders ?? {}),
    });
    if (opts?.idempotencyKey) h.set("idempotency-key", opts.idempotencyKey);
    return h;
  }

  function buildBody(req: ChatRequest, opts?: RequestOptions, stream = false) {
    // LiteLLM accepts `metadata` at the top level and forwards to Langfuse.
    const traceMetadata = opts?.trace
      ? {
          generation_name: opts.trace.name,
          trace_user_id: opts.trace.user_id,
          session_id: opts.trace.session_id,
          tags: opts.trace.tags,
          ...(opts.trace.metadata ?? {}),
        }
      : undefined;

    const mergedMetadata =
      traceMetadata || req.metadata
        ? { ...(req.metadata ?? {}), ...(traceMetadata ?? {}) }
        : undefined;

    return JSON.stringify({
      ...req,
      stream,
      ...(opts?.trace?.user_id && !req.user ? { user: opts.trace.user_id } : {}),
      ...(mergedMetadata ? { metadata: mergedMetadata } : {}),
    });
  }

  function withTimeout(opts?: RequestOptions): AbortSignal {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(new Error("LiteLLM request timeout")), timeoutMs);
    if (opts?.signal) {
      if (opts.signal.aborted) ctrl.abort(opts.signal.reason);
      else opts.signal.addEventListener("abort", () => ctrl.abort(opts.signal!.reason), { once: true });
    }
    // The timer is cleared by the caller via ctrl.signal.addEventListener('abort', ...)
    // but we also rely on fetch's cleanup. Store the timer on the signal-ish:
    (ctrl.signal as AbortSignal & { __timer?: ReturnType<typeof setTimeout> }).__timer = timer;
    return ctrl.signal;
  }

  function clearTimer(signal: AbortSignal) {
    const timer = (signal as AbortSignal & { __timer?: ReturnType<typeof setTimeout> }).__timer;
    if (timer) clearTimeout(timer);
  }

  async function send(path: string, body: string, opts: RequestOptions | undefined): Promise<Response> {
    const signal = withTimeout(opts);
    try {
      const res = await fetchImpl(`${baseURL}${path}`, {
        method: "POST",
        headers: buildHeaders(opts),
        body,
        signal,
      });
      return res;
    } catch (err) {
      throw new LiteLLMNetworkError(`Failed to reach LiteLLM at ${baseURL}${path}`, err);
    } finally {
      clearTimer(signal);
    }
  }

  async function readJsonOrThrow(res: Response, path: string): Promise<unknown> {
    if (!res.ok) {
      const text = await res.text();
      let parsed: unknown = text;
      try { parsed = JSON.parse(text); } catch { /* keep raw */ }
      throw new LiteLLMError(
        `LiteLLM ${path} ${res.status} ${res.statusText}`,
        res.status,
        parsed,
      );
    }
    return res.json();
  }

  return {
    async chat(req, opts) {
      const res = await send("/chat/completions", buildBody(req, opts), opts);
      const json = await readJsonOrThrow(res, "/chat/completions");
      return chatResponseSchema.parse(json);
    },

    async embed(req, opts) {
      const res = await send("/embeddings", JSON.stringify(req), opts);
      const json = await readJsonOrThrow(res, "/embeddings");
      return embedResponseSchema.parse(json);
    },

    async jsonChat<T>(req: ChatRequest, schema: z.ZodType<T>, opts?: RequestOptions) {
      const response = await this.chat(
        { ...req, response_format: { type: "json_object" } },
        opts,
      );
      const raw = extractText(response);
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch (err) {
        throw new LiteLLMSchemaError("JSON mode returned non-JSON output", raw, err);
      }
      const result = schema.safeParse(parsed);
      if (!result.success) {
        throw new LiteLLMSchemaError(
          "JSON mode output failed schema validation",
          raw,
          result.error,
        );
      }
      return { data: result.data, response };
    },

    async *chatStream(req, opts): AsyncGenerator<ChatStreamDelta, void, void> {
      const res = await send("/chat/completions", buildBody(req, opts, true), opts);
      if (!res.ok) {
        const text = await res.text();
        let parsed: unknown = text;
        try { parsed = JSON.parse(text); } catch { /* keep raw */ }
        throw new LiteLLMError(
          `LiteLLM /chat/completions ${res.status} ${res.statusText}`,
          res.status,
          parsed,
        );
      }
      if (!res.body) {
        throw new LiteLLMNetworkError("Stream response had no body", null);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let nl: number;
          while ((nl = buffer.indexOf("\n")) >= 0) {
            const line = buffer.slice(0, nl).trim();
            buffer = buffer.slice(nl + 1);
            if (!line.startsWith("data:")) continue;
            const payload = line.slice(5).trim();
            if (payload === "[DONE]") return;

            let chunk: unknown;
            try {
              chunk = JSON.parse(payload);
            } catch {
              continue; // skip malformed lines defensively
            }

            const delta = extractStreamDelta(chunk);
            if (delta) yield delta;
          }
        }
      } finally {
        reader.releaseLock();
      }
    },
  };
}

// ----- Helpers ---------------------------------------------------------------

function extractText(response: ChatResponse): string {
  const message = response.choices[0]?.message;
  if (!message) return "";
  if (typeof message.content === "string") return message.content;
  // Aggregate text blocks. Cache-control / image blocks contribute no text.
  return message.content
    .filter((b): b is { type: "text"; text: string } => b.type === "text")
    .map((b) => b.text)
    .join("");
}

function extractStreamDelta(chunk: unknown): ChatStreamDelta | null {
  if (!chunk || typeof chunk !== "object") return null;
  const c = chunk as {
    choices?: Array<{ delta?: { content?: string }; finish_reason?: string | null }>;
    usage?: {
      prompt_tokens: number;
      completion_tokens: number;
      total_tokens: number;
      prompt_tokens_details?: { cached_tokens?: number };
    };
  };
  const first = c.choices?.[0];
  const text = first?.delta?.content ?? "";
  const finish = first?.finish_reason ?? undefined;
  const usage = c.usage
    ? {
        prompt_tokens: c.usage.prompt_tokens,
        completion_tokens: c.usage.completion_tokens,
        total_tokens: c.usage.total_tokens,
        cached_tokens: c.usage.prompt_tokens_details?.cached_tokens,
      }
    : undefined;
  if (!text && !finish && !usage) return null;
  return { delta: text, finish_reason: finish ?? undefined, usage, raw: chunk };
}
