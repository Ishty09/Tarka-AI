"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChatThread } from "@/app/(app)/chat/_components/ChatThread";
import type { ChatTurn } from "@/app/(app)/chat/_components/useChatStream";
import { createBrowserSupabase } from "@/lib/supabase/browser";

// CouplesChat wraps the existing ChatThread with a Supabase Realtime
// subscription so partner-side INSERTs into messages show up live (§9.3.1
// "shared conversation"). We only relay turns that AREN'T from the
// current user — their own messages come through useChatStream's stream.

interface PartnerNames {
  user_a: { id: string; name: string };
  user_b: { id: string; name: string };
}

interface Props {
  conversationId: string;
  currentUserId: string;
  partners: PartnerNames;
  initialMessages: ChatTurn[];
  initialTitle: string | null;
}

interface RealtimePayload {
  new: {
    id: number;
    role: string;
    content: string;
    redacted_content: string | null;
    user_id: string | null;
    conversation_id: string;
    safety_verdict: string | null;
  };
}

export function CouplesChat({
  conversationId,
  currentUserId,
  partners,
  initialMessages,
  initialTitle,
}: Props) {
  const appenderRef = useRef<((turn: ChatTurn) => void) | null>(null);
  const [partnerActive, setPartnerActive] = useState(false);

  const register = useCallback((fn: (turn: ChatTurn) => void) => {
    appenderRef.current = fn;
  }, []);

  useEffect(() => {
    const supabase = createBrowserSupabase();
    const channel = supabase
      .channel(`couple-${conversationId}`)
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
          // Skip messages we sent — our local stream already rendered them.
          if (row.role === "user" && row.user_id === currentUserId) return;
          // Skip assistant turns we streamed locally — those came in via
          // useChatStream's `delta` + `done` and are already in state with
          // persistedMessageId set. The Realtime INSERT would arrive after
          // the SSE-driven update; appendExternalTurn dedupes on
          // persistedMessageId.
          appenderRef.current?.({
            id: String(row.id),
            role: row.role as "user" | "assistant",
            content: row.redacted_content ?? row.content,
            persistedMessageId: row.id,
          });
          if (row.role === "user" && row.user_id && row.user_id !== currentUserId) {
            setPartnerActive(true);
            setTimeout(() => setPartnerActive(false), 4000);
          }
        },
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [conversationId, currentUserId]);

  const partnerName =
    currentUserId === partners.user_a.id
      ? partners.user_b.name
      : partners.user_a.name;

  return (
    <div className="relative">
      {partnerActive && (
        <div className="pointer-events-none absolute right-4 top-3 z-10 rounded-full border border-input bg-background/90 px-2 py-1 text-[10px] uppercase tracking-wide text-muted-foreground shadow">
          {partnerName} sent a message
        </div>
      )}
      <ChatThread
        conversationId={conversationId}
        personaSlug={null}
        personaName={`You + ${partnerName}`}
        mode="mediate"
        initialMessages={initialMessages}
        initialTitle={initialTitle}
        registerExternalAppender={register}
      />
    </div>
  );
}
