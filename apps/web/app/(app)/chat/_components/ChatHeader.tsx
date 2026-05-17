"use client";

import { useState } from "react";
import { archiveAndReturnHome, renameConversation } from "../actions";

// Header strip for /chat/[id]. Inline rename (server action via form submit
// — keeps state on the server, no client-side cache to invalidate) and an
// archive button that redirects back to /chat after success.
//
// New conversations (conversationId === null on /chat/new) get the header
// stripped of controls — there's nothing to rename or archive yet.

interface Props {
  conversationId: string | null;
  initialTitle: string | null;
  personaName: string;
  mode: string;
}

export function ChatHeader({ conversationId, initialTitle, personaName, mode }: Props) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(initialTitle ?? "");

  if (conversationId === null) {
    return (
      <header className="border-b px-4 py-3">
        <div className="text-sm font-medium">{personaName}</div>
        <div className="text-xs text-muted-foreground capitalize">{mode}</div>
      </header>
    );
  }

  return (
    <header className="flex items-start justify-between gap-3 border-b px-4 py-3">
      <div className="min-w-0 flex-1">
        {editing ? (
          <form
            action={async (formData: FormData) => {
              await renameConversation(formData);
              setEditing(false);
            }}
            className="flex items-center gap-2"
          >
            <input type="hidden" name="id" value={conversationId} />
            <input
              name="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
              maxLength={120}
              className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm shadow-sm"
            />
            <button
              type="submit"
              className="rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:opacity-90"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => {
                setEditing(false);
                setTitle(initialTitle ?? "");
              }}
              className="rounded-md border border-input bg-background px-2 py-1 text-xs text-muted-foreground hover:bg-accent"
            >
              Cancel
            </button>
          </form>
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="truncate text-left text-sm font-medium hover:underline"
            title="Rename conversation"
          >
            {initialTitle ?? "Untitled"}
          </button>
        )}
        <div className="text-xs text-muted-foreground capitalize">
          {personaName} · {mode}
        </div>
      </div>
      <form action={archiveAndReturnHome} className="shrink-0">
        <input type="hidden" name="id" value={conversationId} />
        <button
          type="submit"
          className="rounded-md border border-input bg-background px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          Archive
        </button>
      </form>
    </header>
  );
}
