"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { type ChatTurn, useChatStream } from "./useChatStream";
import { ChatHeader } from "./ChatHeader";
import { ShareToFeedDialog } from "./ShareToFeedDialog";

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
  initialTitle?: string | null;
  /**
   * Wrapper callback — ChatThread calls this with its `appendExternalTurn`
   * function once mounted so wrappers (CouplesChat) can push partner
   * messages from Realtime events into the running thread.
   */
  registerExternalAppender?: (fn: (turn: ChatTurn) => void) => void;
}

export function ChatThread({
  conversationId,
  personaSlug,
  personaName,
  mode,
  initialMessages,
  initialTitle = null,
  registerExternalAppender,
}: Props) {
  const router = useRouter();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const {
    messages,
    send,
    pending,
    error,
    quotaExceeded,
    safetyEvent,
    appendExternalTurn,
  } = useChatStream({
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
    registerExternalAppender?.(appendExternalTurn);
  }, [appendExternalTurn, registerExternalAppender]);

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
      <ChatHeader
        conversationId={conversationId}
        initialTitle={initialTitle}
        personaName={personaName}
        mode={mode}
      />

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
  const [shareOpen, setShareOpen] = useState(false);
  const canShare =
    !isUser
    && !turn.safetyVerdict
    && typeof turn.persistedMessageId === "number"
    && turn.content.length >= 30;

  return (
    <div className={`flex flex-col gap-2 ${isUser ? "items-end" : "items-start"}`}>
      {turn.contradiction && (
        <ContradictionCallout callout={turn.contradiction} />
      )}
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
      {canShare && (
        <>
          <button
            type="button"
            onClick={() => setShareOpen(true)}
            className="text-[11px] text-muted-foreground underline-offset-2 hover:underline"
          >
            Share to feed
          </button>
          <ShareToFeedDialog
            messageId={turn.persistedMessageId!}
            open={shareOpen}
            onClose={() => setShareOpen(false)}
          />
        </>
      )}
    </div>
  );
}

function ContradictionCallout({ callout }: { callout: NonNullable<ChatTurn["contradiction"]> }) {
  // §9.4.4 inline callout. Severity 7+ leans red, 4-6 amber, lower stays
  // neutral — mirrors the Contradiction Wall (§9.4.1) palette.
  const tone =
    callout.severity >= 7
      ? "border-red-500/40 bg-red-500/10 text-red-900 dark:text-red-200"
      : callout.severity >= 4
      ? "border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-200"
      : "border-input bg-muted/30";
  return (
    <div className={`w-full max-w-[85%] rounded-md border p-3 text-xs shadow-sm ${tone}`}>
      <div className="flex items-center justify-between font-medium">
        <span>Heads up — contradiction</span>
        <span className="font-mono">{callout.severity}/10</span>
      </div>
      <p className="mt-1 text-sm">{callout.summary}</p>
      <div className="mt-2 grid gap-1 text-[11px] opacity-80">
        <span>
          <strong>Earlier ({new Date(callout.fact_a.created_at).toLocaleDateString()}):</strong>{" "}
          {callout.fact_a.text}
        </span>
        <span>
          <strong>Now ({new Date(callout.fact_b.created_at).toLocaleDateString()}):</strong>{" "}
          {callout.fact_b.text}
        </span>
      </div>
    </div>
  );
}
