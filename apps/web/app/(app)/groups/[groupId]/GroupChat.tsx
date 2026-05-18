"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { ChatTurn } from "@/app/(app)/chat/_components/useChatStream";
import { useChatStream } from "@/app/(app)/chat/_components/useChatStream";
import { createBrowserSupabase } from "@/lib/supabase/browser";

// Slack-style group chat (§9.3.4). Reuses useChatStream for posting +
// streaming AI replies, but renders Slack-style (author on top of each
// message, AI visually distinct). Realtime subscription pushes other
// members' messages into the running thread.
//
// AI turn-taking is enforced server-side: the worker returns a
// `group_saved` SSE event when the current user's turn doesn't trigger
// an AI reply (consecutive humans < 3). The client treats `group_saved`
// the same as `done` — render the user message, close out the in-flight
// state.

interface Member {
  id: string;
  name: string;
}

interface Props {
  groupId: string;
  conversationId: string;
  currentUserId: string;
  mediatorName: string;
  members: Member[];
  initialMessages: ChatTurn[];
}

interface RealtimePayload {
  new: {
    id: number;
    role: string;
    content: string;
    redacted_content: string | null;
    user_id: string | null;
    conversation_id: string;
  };
}

const AI_THRESHOLD = 3;

export function GroupChat({
  groupId,
  conversationId,
  currentUserId,
  mediatorName,
  members,
  initialMessages,
}: Props) {
  const router = useRouter();
  const memberById = useRef<Map<string, Member>>(
    new Map(members.map((m) => [m.id, m])),
  );
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const {
    messages,
    send,
    pending,
    error,
    quotaExceeded,
    appendExternalTurn,
  } = useChatStream({
    conversationId,
    personaSlug: null,
    mode: "mediate",
    initialMessages,
  });

  // Realtime — relay every INSERT that didn't come from this client's stream.
  useEffect(() => {
    const supabase = createBrowserSupabase();
    const channel = supabase
      .channel(`group-${conversationId}`)
      .on(
        "postgres_changes" as never,
        {
          event: "INSERT",
          schema: "public",
          table: "messages",
          filter: `conversation_id=eq.${conversationId}`,
        },
        (payload: RealtimePayload) => {
          const row = payload.new;
          if (!row) return;
          // Skip our own user messages — they came in via the local stream.
          if (row.role === "user" && row.user_id === currentUserId) return;
          const authorId = row.user_id ?? undefined;
          const authorName =
            row.role === "assistant"
              ? mediatorName
              : authorId
              ? memberById.current.get(authorId)?.name ?? "Member"
              : undefined;
          appendExternalTurn({
            id: String(row.id),
            role: row.role as "user" | "assistant",
            content: row.redacted_content ?? row.content,
            persistedMessageId: row.id,
            authorId,
            authorName,
          });
        },
      )
      .subscribe();
    return () => {
      void supabase.removeChannel(channel);
    };
  }, [appendExternalTurn, conversationId, currentUserId, mediatorName]);

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

  // Compute consecutive-human streak so the UI can hint when the AI will
  // intervene next. Counts back from the most recent message.
  const streak = (() => {
    let n = 0;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") n += 1;
      else break;
    }
    return n;
  })();
  const turnsUntilAI = Math.max(0, AI_THRESHOLD - streak);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <header className="flex items-center justify-between border-b px-4 py-2 text-xs">
        <div className="flex flex-col">
          <span className="font-medium text-foreground">Group chat</span>
          <span className="text-muted-foreground">
            Mediator: <span className="font-medium">{mediatorName}</span> ·{" "}
            {members.length} member{members.length === 1 ? "" : "s"}
          </span>
        </div>
        <span className="text-muted-foreground">
          {turnsUntilAI === 0
            ? `${mediatorName} will weigh in on the next message`
            : `AI joins after ${turnsUntilAI} more message${turnsUntilAI === 1 ? "" : "s"}`}
        </span>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
          {messages.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Open with the question. {mediatorName} weighs in after every {AI_THRESHOLD} member messages.
            </p>
          )}
          {messages.map((m) => (
            <SlackBubble
              key={m.id}
              turn={m}
              isMine={m.role === "user" && m.authorId === currentUserId}
              mediatorName={mediatorName}
              memberById={memberById.current}
            />
          ))}
          {quotaExceeded && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
              You hit your {quotaExceeded.tier} tier limit ({quotaExceeded.used}/{quotaExceeded.limit}).
              Resets {new Date(quotaExceeded.reset_at).toLocaleString()}.
            </div>
          )}
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
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
            placeholder={
              turnsUntilAI === 0
                ? `Anyone can post. ${mediatorName} will weigh in.`
                : "Add to the conversation…"
            }
            rows={2}
            disabled={pending || !!quotaExceeded}
            className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={pending || !input.trim() || !!quotaExceeded}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
          >
            {pending ? "Sending…" : "Send"}
          </button>
        </div>
        <p className="mt-2 text-center text-[10px] text-muted-foreground">
          <button
            type="button"
            onClick={() => router.refresh()}
            className="underline-offset-2 hover:underline"
          >
            Refresh
          </button>
        </p>
      </form>
    </div>
  );
}

function SlackBubble({
  turn,
  isMine,
  mediatorName,
  memberById,
}: {
  turn: ChatTurn;
  isMine: boolean;
  mediatorName: string;
  memberById: Map<string, { id: string; name: string }>;
}) {
  const isAI = turn.role === "assistant";
  let displayName: string;
  if (isAI) {
    displayName = mediatorName;
  } else if (isMine) {
    displayName = "You";
  } else if (turn.authorName) {
    displayName = turn.authorName;
  } else if (turn.authorId) {
    displayName = memberById.get(turn.authorId)?.name ?? "Member";
  } else {
    displayName = "Member";
  }

  return (
    <article
      className={`flex flex-col rounded-md px-4 py-3 text-sm shadow-sm ${
        isAI
          ? "border border-primary/40 bg-primary/5"
          : "border border-input bg-background"
      }`}
    >
      <header className="text-xs">
        <span className={isAI ? "font-semibold text-primary" : "font-semibold"}>
          {displayName}
        </span>
        {isAI && (
          <span className="ml-2 rounded-full bg-primary/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-primary">
            mediator
          </span>
        )}
      </header>
      <p className="mt-1 whitespace-pre-wrap leading-relaxed">
        {turn.content || (isAI && <span className="text-muted-foreground">…</span>)}
      </p>
    </article>
  );
}
