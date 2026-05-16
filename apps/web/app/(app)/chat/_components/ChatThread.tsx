"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { type ChatTurn, useChatStream } from "./useChatStream";

// Client-side chat thread. Composer pinned to the bottom; messages reflow
// upward as deltas stream in.
//
// Worker's wire creates the conversation on first user turn when
// conversationId is null + personaSlug is set. After the first response, we
// refresh() to pull the new conversation_id into the URL (the /chat/[id]
// page sets it; /chat/new doesn't have one yet).

interface Props {
  conversationId: string | null;
  personaSlug: string | null;
  personaName: string;
  mode: "argue" | "roast" | "mediate" | "council" | "negotiate" | "custom";
  initialMessages: ChatTurn[];
}

export function ChatThread({
  conversationId,
  personaSlug,
  personaName,
  mode,
  initialMessages,
}: Props) {
  const router = useRouter();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const { messages, send, pending, error, quotaExceeded, safetyEvent } = useChatStream({
    conversationId,
    personaSlug: conversationId ? null : personaSlug,
    mode,
    initialMessages,
    onAssistantPersisted: () => {
      if (!conversationId) {
        // First turn on /chat/new — refresh so the server re-resolves and
        // pushes us toward /chat/[newId] (driven by the conversations list).
        router.refresh();
      }
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const text = input.trim();
    if (!text || pending) return;
    setInput("");
    void send(text);
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <header className="border-b px-4 py-3">
        <div className="text-sm font-medium">{personaName}</div>
        <div className="text-xs text-muted-foreground capitalize">{mode}</div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
          {messages.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Say something worth pushing back on.
            </p>
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} turn={m} />
          ))}
          {quotaExceeded && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
              You hit your {quotaExceeded.tier} tier limit ({quotaExceeded.used}/{quotaExceeded.limit}).
              Resets {new Date(quotaExceeded.reset_at).toLocaleString()}.{" "}
              {quotaExceeded.upgrade_url && (
                <a href={quotaExceeded.upgrade_url} className="underline">Upgrade</a>
              )}
            </div>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">{error}</p>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <form onSubmit={onSubmit} className="border-t bg-background p-3">
        <div className="mx-auto flex w-full max-w-2xl items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSubmit(e as unknown as React.FormEvent<HTMLFormElement>);
              }
            }}
            placeholder={safetyEvent ? "Try a different angle." : "Say something..."}
            rows={2}
            disabled={pending || !!quotaExceeded}
            className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={pending || !input.trim() || !!quotaExceeded}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
          >
            {pending ? "..." : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}

function MessageBubble({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm shadow-sm ${
          isUser
            ? "bg-primary text-primary-foreground"
            : turn.safetyVerdict
            ? "border border-amber-500/40 bg-amber-500/10"
            : "border border-input bg-background"
        }`}
      >
        {turn.content || (turn.role === "assistant" && <span className="text-muted-foreground">...</span>)}
      </div>
    </div>
  );
}
