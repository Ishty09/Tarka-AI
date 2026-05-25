"use client";

import { useState } from "react";
import { ThemeToggle } from "@/app/_components/ThemeToggle";
import { Sidebar, type ConversationSummary } from "./Sidebar";

// Client wrapper that owns the sidebar open/close state on mobile.
// Server component (app)/layout.tsx fetches the data + renders this.

interface Props {
  conversations: ConversationSummary[];
  username: string;
  tier: string;
  children: React.ReactNode;
}

export function AppShell({ conversations, username, tier, children }: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex min-h-screen">
      <Sidebar
        conversations={conversations}
        username={username}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <div className="flex flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center justify-between border-b bg-background/80 px-3 py-2 backdrop-blur-md md:px-4">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open sidebar"
              className="-ml-1 inline-flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground hover:bg-accent md:hidden"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                tier === "max"
                  ? "bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white"
                  : tier === "pro"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {tier}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <form action="/auth/signout" method="post">
              <button
                type="submit"
                className="rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                Sign out
              </button>
            </form>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
