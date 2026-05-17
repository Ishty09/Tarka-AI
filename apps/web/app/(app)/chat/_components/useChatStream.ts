"use client";

import { useCallback, useRef, useState } from "react";

// Custom streaming hook for the worker's SSE protocol.
//
// Why not @ai-sdk/react useChat: workers emits a domain-specific event set
// (delta / done / safety / quota_exceeded / error) that doesn't match the
// AI SDK Data Stream Protocol. Wrapping it in an adapter would add a second
// translation hop with no benefit since apps/web never calls the LLM
// directly. This hook is ~80 lines and shaped exactly to our wire.

export interface ContradictionCallout {
  id: number;
  severity: number;
  summary: string;
  fact_a: { text: string; created_at: string };
  fact_b: { text: string; created_at: string };
}

export interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Set on assistant turns that were short-circuited by the safety screen. */
  safetyVerdict?: string;
  safetyReason?: string;
  /** Contradiction surfaced inline §9.4.4 — pinned above the assistant bubble. */
  contradiction?: ContradictionCallout;
}

export interface QuotaExceeded {
  tier: string;
  limit: number;
  used: number;
  reset_at: string;
  upgrade_url: string | null;
}

export interface UseChatStreamOptions {
  conversationId: string | null;
  personaSlug: string | null;
  mode: "argue" | "roast" | "mediate" | "council" | "negotiate" | "custom";
  initialMessages: ChatTurn[];
  /** Called when workers persisted the assistant message. */
  onAssistantPersisted?: (info: { assistantMessageId: number | null }) => void;
}

export function useChatStream(opts: UseChatStreamOptions) {
  const [messages, setMessages] = useState<ChatTurn[]>(opts.initialMessages);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quotaExceeded, setQuotaExceeded] = useState<QuotaExceeded | null>(null);
  const [safetyEvent, setSafetyEvent] = useState<{ verdict: string; reason: string } | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(async (text: string) => {
    if (pending || !text.trim()) return;
    setError(null);
    setQuotaExceeded(null);
    setSafetyEvent(null);

    const userTurn: ChatTurn = {
      id: `local-${crypto.randomUUID()}`,
      role: "user",
      content: text,
    };
    const assistantTurn: ChatTurn = {
      id: `local-${crypto.randomUUID()}`,
      role: "assistant",
      content: "",
    };
    setMessages((prev) => [...prev, userTurn, assistantTurn]);
    setPending(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          conversation_id: opts.conversationId,
          persona_slug: opts.personaSlug,
          mode: opts.mode,
          message: text,
          idempotency_key: crypto.randomUUID(),
        }),
        signal: controller.signal,
      });

      if (res.status === 401) {
        setError("Your session expired. Sign in again.");
        return;
      }
      if (!res.body) {
        setError("No response body from server.");
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let blockEnd: number;
        while ((blockEnd = buffer.indexOf("\n\n")) >= 0) {
          const block = buffer.slice(0, blockEnd);
          buffer = buffer.slice(blockEnd + 2);
          const parsed = parseSseBlock(block);
          if (!parsed) continue;

          if (parsed.event === "contradiction") {
            const data = parsed.data as ContradictionCallout;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantTurn.id ? { ...m, contradiction: data } : m,
              ),
            );
          } else if (parsed.event === "delta") {
            const text = (parsed.data as { text?: string }).text ?? "";
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantTurn.id ? { ...m, content: m.content + text } : m)),
            );
          } else if (parsed.event === "safety") {
            const data = parsed.data as { verdict: string; reason: string };
            setSafetyEvent(data);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantTurn.id
                  ? { ...m, content: refusalCopy(data.verdict), safetyVerdict: data.verdict, safetyReason: data.reason }
                  : m,
              ),
            );
          } else if (parsed.event === "quota_exceeded") {
            setQuotaExceeded(parsed.data as QuotaExceeded);
            // Drop the placeholder assistant turn since nothing was streamed.
            setMessages((prev) => prev.filter((m) => m.id !== assistantTurn.id));
          } else if (parsed.event === "done") {
            const data = parsed.data as { assistant_message_id?: number };
            opts.onAssistantPersisted?.({ assistantMessageId: data.assistant_message_id ?? null });
          } else if (parsed.event === "error") {
            const reason = (parsed.data as { reason?: string }).reason ?? "unknown_error";
            setError(`Stream failed: ${reason}`);
          }
        }
      }
    } catch (err) {
      if ((err as { name?: string }).name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setPending(false);
      abortRef.current = null;
    }
  }, [opts, pending]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setPending(false);
  }, []);

  return { messages, send, stop, pending, error, quotaExceeded, safetyEvent };
}

function parseSseBlock(block: string): { event: string; data: unknown } | null {
  let event = "message";
  let dataLine = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
  }
  if (!dataLine) return null;
  try {
    return { event, data: JSON.parse(dataLine) };
  } catch {
    return null;
  }
}

function refusalCopy(verdict: string): string {
  switch (verdict) {
    case "crisis":
      return "I'm not going to argue this one. If you're in danger or thinking about hurting yourself, please reach out to a hotline now.";
    case "abuse":
      return "What you're describing isn't something I can help with through argument. Talk to a trusted person or hotline first.";
    case "minor_self_sexualization":
      return "I can't engage with this.";
    case "jailbreak":
      return "Not going to do that. Try a real question.";
    default:
      return "I can't respond to that.";
  }
}
