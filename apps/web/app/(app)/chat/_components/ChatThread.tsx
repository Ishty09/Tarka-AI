"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ChatTurn, useChatStream } from "./useChatStream";
import { ChatHeader } from "./ChatHeader";
import { ShareToFeedDialog } from "./ShareToFeedDialog";

// Client-side chat thread. Composer pinned to the bottom; messages reflow
// upward as deltas stream in. The composer now exposes mode + persona
// switchers inline so users can pivot mid-conversation without leaving
// the page, plus suggested starter prompts on empty threads and a slash-
// command palette for power users.

type Mode = "argue" | "roast" | "mediate" | "council" | "negotiate" | "custom";

interface Props {
  conversationId: string | null;
  personaSlug: string | null;
  personaName: string;
  mode: Mode;
  initialMessages: ChatTurn[];
  initialTitle?: string | null;
  registerExternalAppender?: (fn: (turn: ChatTurn) => void) => void;
}

const MODES: { value: Mode; label: string; icon: string; hint: string }[] = [
  { value: "argue", label: "Argue", icon: "⚔", hint: "Devil's advocate pushes on your reasoning" },
  { value: "roast", label: "Roast", icon: "🔥", hint: "Cutting commentary, no comfort" },
  { value: "mediate", label: "Mediate", icon: "⚖", hint: "Three-way conflict resolution" },
  { value: "council", label: "Council", icon: "👥", hint: "5 personas + a judge" },
  { value: "negotiate", label: "Negotiate", icon: "🤝", hint: "Sparring partner for hard conversations" },
];

const STARTERS: Record<Mode, string[]> = {
  argue: [
    "Convince me I'm wrong about quitting my job",
    "Steelman the opposite of my last belief",
    "Why is my plan a fantasy?",
  ],
  roast: [
    "Roast my LinkedIn bio",
    "Roast my morning routine",
    "Roast my last excuse",
  ],
  mediate: [
    "My partner and I disagree about money. Help us see it.",
    "My cofounder won't move on equity. What are we missing?",
    "Why does this fight keep happening?",
  ],
  council: [
    "Should I take this job offer?",
    "Am I underpricing my service?",
    "Should I move countries?",
  ],
  negotiate: [
    "Role-play my boss in a raise conversation",
    "Play the landlord — I'm asking for a rent reduction",
    "I'm breaking up. Play the other side.",
  ],
  custom: [
    "Tell me something I don't want to hear",
    "What's the question I should be asking?",
    "What am I avoiding?",
  ],
};

const SLASH_COMMANDS = [
  { cmd: "/argue", mode: "argue" as Mode, label: "Switch to Argue mode" },
  { cmd: "/roast", mode: "roast" as Mode, label: "Switch to Roast mode" },
  { cmd: "/mediate", mode: "mediate" as Mode, label: "Switch to Mediate mode" },
  { cmd: "/council", mode: "council" as Mode, label: "Switch to Council mode" },
  { cmd: "/negotiate", mode: "negotiate" as Mode, label: "Switch to Negotiate mode" },
];

export function ChatThread({
  conversationId,
  personaSlug,
  personaName,
  mode: initialMode,
  initialMessages,
  initialTitle = null,
  registerExternalAppender,
}: Props) {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode>(initialMode);
  const [showSlash, setShowSlash] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
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
      if (!conversationId) router.refresh();
    },
  });

  useEffect(() => {
    registerExternalAppender?.(appendExternalTurn);
  }, [appendExternalTurn, registerExternalAppender]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  // Auto-resize textarea up to a sensible max.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [input]);

  // Slash-command detection: show palette when the input starts with "/"
  // and is just one token (no space yet).
  useEffect(() => {
    setShowSlash(input.startsWith("/") && !input.includes(" "));
  }, [input]);

  function applySlashCommand(cmd: typeof SLASH_COMMANDS[number]) {
    setMode(cmd.mode);
    setInput("");
    setShowSlash(false);
    textareaRef.current?.focus();
  }

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const text = input.trim();
    if (!text || pending) return;

    // Inline slash-command: switches mode and clears.
    const slashMatch = SLASH_COMMANDS.find((s) => text.toLowerCase() === s.cmd);
    if (slashMatch) {
      applySlashCommand(slashMatch);
      return;
    }

    setInput("");
    void send(text);
  }

  const showEmpty = messages.length === 0;
  const starters = useMemo(() => STARTERS[mode] ?? STARTERS.custom, [mode]);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col bg-background">
      <ChatHeader
        conversationId={conversationId}
        initialTitle={initialTitle}
        personaName={personaName}
        mode={mode}
      />

      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
          {showEmpty && (
            <EmptyState
              personaName={personaName}
              mode={mode}
              starters={starters}
              onPick={(text) => {
                setInput(text);
                textareaRef.current?.focus();
              }}
            />
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} turn={m} personaName={personaName} />
          ))}
          {quotaExceeded && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
              You hit your {quotaExceeded.tier} tier limit ({quotaExceeded.used}/
              {quotaExceeded.limit}). Resets{" "}
              {new Date(quotaExceeded.reset_at).toLocaleString()}.{" "}
              {quotaExceeded.upgrade_url && (
                <a href={quotaExceeded.upgrade_url} className="font-medium underline">
                  Upgrade
                </a>
              )}
            </div>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Composer */}
      <div className="border-t bg-background">
        <div className="mx-auto w-full max-w-2xl px-3 pt-3">
          {/* Mode quick-switcher only on /chat/new — once a conversation
              exists, mode is locked at the DB level. To start a new mode,
              users click + New Chat in the sidebar. */}
          {!conversationId && (
            <div className="mb-2 flex flex-wrap items-center gap-1.5 text-xs">
              {MODES.map((m) => {
                const active = mode === m.value;
                return (
                  <button
                    key={m.value}
                    type="button"
                    onClick={() => setMode(m.value)}
                    title={m.hint}
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 transition ${
                      active
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "border border-input bg-background text-muted-foreground hover:bg-accent hover:text-foreground"
                    }`}
                  >
                    <span aria-hidden>{m.icon}</span>
                    {m.label}
                  </button>
                );
              })}
              <span className="mx-1 h-3 w-px bg-border" aria-hidden />
              <Link
                href="/personas"
                className="inline-flex items-center gap-1 rounded-full border border-input px-2.5 py-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                title="Switch persona"
              >
                👤 {personaName}
              </Link>
            </div>
          )}

          {showSlash && (
            <div className="mb-2 overflow-hidden rounded-md border border-input bg-popover shadow-md">
              {SLASH_COMMANDS.filter((c) => c.cmd.startsWith(input.toLowerCase()))
                .slice(0, 5)
                .map((c) => (
                  <button
                    type="button"
                    key={c.cmd}
                    onClick={() => applySlashCommand(c)}
                    className="flex w-full items-center justify-between px-3 py-1.5 text-left text-xs hover:bg-accent"
                  >
                    <span className="font-mono text-foreground">{c.cmd}</span>
                    <span className="text-muted-foreground">{c.label}</span>
                  </button>
                ))}
            </div>
          )}
        </div>

        <form onSubmit={onSubmit} className="px-3 pb-3">
          <div className="mx-auto flex w-full max-w-2xl items-end gap-2 rounded-2xl border border-input bg-background px-3 py-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSubmit(e as unknown as React.FormEvent<HTMLFormElement>);
                }
              }}
              placeholder={
                safetyEvent
                  ? "Try a different angle."
                  : `Say something${personaName ? ` to ${personaName}` : ""}...  (Enter to send · Shift+Enter for newline · / for commands)`
              }
              rows={1}
              disabled={pending || !!quotaExceeded}
              className="flex-1 resize-none bg-transparent text-sm outline-none disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={pending || !input.trim() || !!quotaExceeded}
              aria-label="Send"
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm transition hover:opacity-90 disabled:opacity-50"
            >
              {pending ? (
                <span className="text-xs">·</span>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              )}
            </button>
          </div>
          <p className="mx-auto mt-1 max-w-2xl text-center text-[10px] text-muted-foreground">
            Quarrel can be wrong, cutting, and contradicts itself when called out.
            That&apos;s the point. Not legal, medical, or crisis advice.
          </p>
        </form>
      </div>
    </div>
  );
}

// ----- Empty state with suggested prompts ------------------------------------

function EmptyState({
  personaName,
  mode,
  starters,
  onPick,
}: {
  personaName: string;
  mode: Mode;
  starters: string[];
  onPick: (text: string) => void;
}) {
  const modeMeta = MODES.find((m) => m.value === mode);
  return (
    <div className="flex flex-col items-center gap-4 py-12 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-2xl">
        {modeMeta?.icon ?? "💬"}
      </div>
      <div>
        <h2 className="text-lg font-semibold tracking-tight">
          {personaName} is ready to push back.
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {modeMeta?.hint ?? "Say something worth disagreeing with."}
        </p>
      </div>
      <ul className="grid w-full max-w-md gap-2">
        {starters.map((s) => (
          <li key={s}>
            <button
              type="button"
              onClick={() => onPick(s)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-left text-sm text-muted-foreground transition hover:border-primary/40 hover:bg-accent hover:text-foreground"
            >
              {s}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ----- Message bubble + actions ----------------------------------------------

function MessageBubble({ turn, personaName }: { turn: ChatTurn; personaName: string }) {
  const isUser = turn.role === "user";
  const [shareOpen, setShareOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const canShare =
    !isUser &&
    !turn.safetyVerdict &&
    typeof turn.persistedMessageId === "number" &&
    turn.content.length >= 30;

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(turn.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* noop */
    }
  }

  return (
    <div className={`flex items-start gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <Avatar label={isUser ? "you" : personaName} muted={isUser} />
      <div className={`flex max-w-[85%] flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
        {turn.contradiction && <ContradictionCallout callout={turn.contradiction} />}
        <div
          className={`whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm shadow-sm ${
            isUser
              ? "rounded-tr-sm bg-primary text-primary-foreground"
              : turn.safetyVerdict
              ? "rounded-tl-sm border border-amber-500/40 bg-amber-500/10"
              : "rounded-tl-sm border border-input bg-card"
          }`}
        >
          {turn.content || (
            // Empty assistant turn = streaming hasn't sent first delta yet.
            // Show three pulsing dots INSIDE the bubble so it doubles as
            // the typing indicator. No second bubble outside.
            <span className="inline-flex items-center gap-1 py-0.5">
              <Dot delay="0ms" />
              <Dot delay="150ms" />
              <Dot delay="300ms" />
            </span>
          )}
        </div>
        {!isUser && turn.content.length > 0 && (
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
            <button
              type="button"
              onClick={onCopy}
              className="underline-offset-2 hover:underline"
            >
              {copied ? "Copied" : "Copy"}
            </button>
            {canShare && (
              <>
                <span className="text-border">·</span>
                <button
                  type="button"
                  onClick={() => setShareOpen(true)}
                  className="underline-offset-2 hover:underline"
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
        )}
      </div>
    </div>
  );
}

// ----- Small atoms -----------------------------------------------------------

function Avatar({ label, muted = false }: { label: string; muted?: boolean }) {
  const initial = (label?.trim()?.[0] ?? "?").toUpperCase();
  return (
    <div
      aria-hidden
      className={`flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-full text-xs font-medium ${
        muted
          ? "bg-muted text-muted-foreground"
          : "bg-gradient-to-br from-primary to-primary/70 text-primary-foreground"
      }`}
    >
      {initial}
    </div>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      aria-hidden
      style={{ animationDelay: delay }}
      className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground/60"
    />
  );
}

// ----- Contradiction callout (unchanged from prior) --------------------------

function ContradictionCallout({
  callout,
}: {
  callout: NonNullable<ChatTurn["contradiction"]>;
}) {
  const tone =
    callout.severity >= 7
      ? "border-red-500/40 bg-red-500/10 text-red-900 dark:text-red-200"
      : callout.severity >= 4
      ? "border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-200"
      : "border-input bg-muted/30";
  return (
    <div className={`w-full rounded-md border p-3 text-xs shadow-sm ${tone}`}>
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
