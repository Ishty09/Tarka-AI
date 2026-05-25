"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

// Persistent left sidebar — conversation list + quick filters + nav links.
// Sticky on desktop (>=md), drawer on mobile (toggled via header button).
//
// Conversations come from a server fetch in (app)/layout.tsx and arrive
// here as props. Search + mode filter are client-side over that list.

export interface ConversationSummary {
  id: string;
  title: string | null;
  mode: string;
  updated_at: string;
  persona_name: string | null;
  archived: boolean;
}

interface Props {
  conversations: ConversationSummary[];
  username: string;
  open: boolean;
  onClose: () => void;
}

const MODE_META: Record<string, { icon: string; label: string; tone: string }> = {
  argue: { icon: "⚔", label: "Argue", tone: "text-red-500" },
  roast: { icon: "🔥", label: "Roast", tone: "text-orange-500" },
  mediate: { icon: "⚖", label: "Mediate", tone: "text-emerald-500" },
  council: { icon: "👥", label: "Council", tone: "text-violet-500" },
  negotiate: { icon: "🤝", label: "Negotiate", tone: "text-blue-500" },
  custom: { icon: "💬", label: "Custom", tone: "text-muted-foreground" },
};

const FILTER_OPTIONS = ["all", "argue", "roast", "mediate", "council", "negotiate"] as const;
type Filter = (typeof FILTER_OPTIONS)[number];

const NAV_LINKS = [
  { href: "/chat", label: "Chat", icon: "💬" },
  { href: "/personas", label: "Personas", icon: "👤" },
  { href: "/contradictions", label: "Contradictions", icon: "⚡" },
  { href: "/mirror", label: "Mirror", icon: "🪞" },
  { href: "/wagers", label: "Wagers", icon: "💰" },
  { href: "/tools/council", label: "Council", icon: "🏛" },
  { href: "/feed", label: "Feed", icon: "📣" },
  { href: "/settings", label: "Settings", icon: "⚙" },
] as const;

export function Sidebar({ conversations, username, open, onClose }: Props) {
  const pathname = usePathname();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const filteredConvos = useMemo(() => {
    const q = query.trim().toLowerCase();
    return conversations.filter((c) => {
      if (filter !== "all" && c.mode !== filter) return false;
      if (!q) return true;
      return (
        (c.title ?? "").toLowerCase().includes(q) ||
        (c.persona_name ?? "").toLowerCase().includes(q)
      );
    });
  }, [conversations, query, filter]);

  const grouped = useMemo(() => groupByDate(filteredConvos), [filteredConvos]);

  return (
    <>
      {/* Mobile backdrop */}
      {open && (
        <button
          type="button"
          aria-label="Close sidebar"
          onClick={onClose}
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-sm md:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r bg-card transition-transform md:sticky md:top-0 md:h-screen md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand + collapse for mobile */}
        <div className="flex items-center justify-between border-b px-4 py-3">
          <Link href="/chat" className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground text-xs">Q</span>
            Quarrel
          </Link>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close sidebar"
            className="rounded-md p-1 text-muted-foreground hover:bg-accent md:hidden"
          >
            ✕
          </button>
        </div>

        {/* New chat CTA */}
        <div className="border-b px-3 py-3">
          <Link
            href="/chat/new"
            onClick={onClose}
            className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm transition hover:opacity-90"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New chat
          </Link>
        </div>

        {/* Search */}
        <div className="border-b px-3 py-2">
          <div className="relative">
            <span className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
            </span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search conversations…"
              className="w-full rounded-md border border-input bg-background py-1.5 pl-7 pr-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
        </div>

        {/* Mode filter */}
        <div className="border-b px-3 py-2">
          <div className="flex flex-wrap gap-1">
            {FILTER_OPTIONS.map((f) => {
              const active = filter === f;
              const meta = f === "all" ? null : MODE_META[f];
              return (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFilter(f)}
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] transition ${
                    active
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground"
                  }`}
                >
                  {meta && <span aria-hidden>{meta.icon}</span>}
                  {f === "all" ? "All" : meta?.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto px-2 py-2">
          {filteredConvos.length === 0 ? (
            <p className="px-2 py-6 text-center text-xs text-muted-foreground">
              {conversations.length === 0
                ? "No conversations yet. Pick a persona to start."
                : "No matches."}
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              {grouped.map(([label, items]) => (
                <div key={label}>
                  <div className="px-2 pb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                    {label}
                  </div>
                  <ul className="flex flex-col gap-0.5">
                    {items.map((c) => {
                      const meta = MODE_META[c.mode] ?? MODE_META.custom;
                      const href = `/chat/${c.id}`;
                      const active = pathname === href;
                      const label = (c.title?.trim() || `New ${meta.label.toLowerCase()}`).slice(0, 60);
                      return (
                        <li key={c.id}>
                          <Link
                            href={href}
                            onClick={onClose}
                            className={`group relative flex items-start gap-2 rounded-md px-2 py-2 text-xs transition ${
                              active
                                ? "bg-accent text-accent-foreground"
                                : "text-foreground/80 hover:bg-accent/60 hover:text-accent-foreground"
                            }`}
                          >
                            {active && (
                              <span
                                aria-hidden
                                className={`absolute inset-y-1 left-0 w-0.5 rounded-r-full ${meta.tone.replace("text-", "bg-")}`}
                              />
                            )}
                            <span className={`mt-0.5 text-sm leading-none ${meta.tone}`} aria-hidden>
                              {meta.icon}
                            </span>
                            <span className="flex flex-1 flex-col gap-0.5 overflow-hidden">
                              <span className="truncate text-[13px] font-medium leading-tight">
                                {label}
                              </span>
                              <span className="flex items-center gap-1.5 truncate text-[11px] text-muted-foreground">
                                <span className="truncate">{c.persona_name ?? meta.label}</span>
                                <span aria-hidden>·</span>
                                <time>{formatRelative(c.updated_at)}</time>
                              </span>
                            </span>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer nav links */}
        <div className="border-t px-2 py-2">
          <ul className="grid grid-cols-2 gap-0.5">
            {NAV_LINKS.map((n) => {
              const active = pathname === n.href || pathname.startsWith(n.href + "/");
              return (
                <li key={n.href}>
                  <Link
                    href={n.href}
                    onClick={onClose}
                    className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-xs transition ${
                      active
                        ? "bg-accent text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground"
                    }`}
                  >
                    <span aria-hidden>{n.icon}</span>
                    {n.label}
                  </Link>
                </li>
              );
            })}
          </ul>
          <p className="mt-2 px-2 text-[10px] text-muted-foreground">
            @{username}
          </p>
        </div>
      </aside>
    </>
  );
}

function formatRelative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.floor(ms / 60000);
  if (min < 1) return "now";
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d`;
  if (day < 30) return `${Math.floor(day / 7)}w`;
  return `${Math.floor(day / 30)}mo`;
}

// Group conversations into Today / Yesterday / This week / Older.
function groupByDate(items: ConversationSummary[]): [string, ConversationSummary[]][] {
  const now = Date.now();
  const day = 24 * 60 * 60 * 1000;
  const today: ConversationSummary[] = [];
  const yesterday: ConversationSummary[] = [];
  const week: ConversationSummary[] = [];
  const older: ConversationSummary[] = [];

  for (const c of items) {
    const ageMs = now - new Date(c.updated_at).getTime();
    if (ageMs < day) today.push(c);
    else if (ageMs < day * 2) yesterday.push(c);
    else if (ageMs < day * 7) week.push(c);
    else older.push(c);
  }

  const out: [string, ConversationSummary[]][] = [];
  if (today.length) out.push(["Today", today]);
  if (yesterday.length) out.push(["Yesterday", yesterday]);
  if (week.length) out.push(["This week", week]);
  if (older.length) out.push(["Older", older]);
  return out;
}
