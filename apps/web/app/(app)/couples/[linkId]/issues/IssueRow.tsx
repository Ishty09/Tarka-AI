"use client";

import { useActionState, useState } from "react";
import { updateIssueStatus, type ActionResult } from "./actions";

interface Issue {
  id: string;
  theme: string;
  description: string | null;
  status: "discussed" | "agreed" | "resolved" | "recurring";
  severity: number;
  source: string;
  first_raised_at: string;
  last_discussed_at: string;
  resolved_at: string | null;
  recurrence_count: number;
  notes: string | null;
}

const NEXT_STATUSES: Record<Issue["status"], Issue["status"][]> = {
  discussed: ["agreed", "resolved", "recurring"],
  agreed: ["resolved", "recurring", "discussed"],
  recurring: ["discussed", "agreed", "resolved"],
  resolved: ["discussed"],
};

const STATUS_COLORS: Record<Issue["status"], string> = {
  discussed: "border-amber-500/40 bg-amber-500/10",
  agreed: "border-blue-500/40 bg-blue-500/10",
  recurring: "border-red-500/40 bg-red-500/10",
  resolved: "border-emerald-500/40 bg-emerald-500/10",
};

export function IssueRow({ issue }: { issue: Issue }) {
  const [open, setOpen] = useState(false);
  const [state, formAction, pending] = useActionState<ActionResult | null, FormData>(
    updateIssueStatus,
    null,
  );

  return (
    <article
      className={`rounded-lg border bg-card p-3 text-sm transition ${STATUS_COLORS[issue.status]}`}
    >
      <header className="flex items-start justify-between gap-3">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex-1 text-left"
        >
          <div className="flex items-center gap-2">
            <span className="font-medium">{issue.theme}</span>
            <span className="rounded-full bg-background/60 px-2 py-0.5 text-[10px] font-mono text-muted-foreground">
              {issue.severity}/10
            </span>
            {issue.source !== "manual" && (
              <span className="rounded-full bg-background/60 px-2 py-0.5 text-[10px] text-muted-foreground">
                from {issue.source.replace("_", " ")}
              </span>
            )}
          </div>
          {issue.description && (
            <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
              {issue.description}
            </p>
          )}
          <p className="mt-1 text-[10px] text-muted-foreground">
            First raised {new Date(issue.first_raised_at).toLocaleDateString()}{" "}
            · last discussed{" "}
            {new Date(issue.last_discussed_at).toLocaleDateString()}
            {issue.recurrence_count > 1 && ` · raised ${issue.recurrence_count}×`}
          </p>
        </button>
      </header>

      {open && (
        <div className="mt-3 border-t border-current/20 pt-3">
          {issue.notes && (
            <div className="mb-3 rounded-md bg-background/60 p-2 text-xs">
              <span className="text-muted-foreground">Notes: </span>
              {issue.notes}
            </div>
          )}

          <form action={formAction} className="flex flex-col gap-2">
            <input type="hidden" name="issue_id" value={issue.id} />
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Move to:
              </span>
              {NEXT_STATUSES[issue.status].map((s) => (
                <button
                  key={s}
                  type="submit"
                  name="status"
                  value={s}
                  disabled={pending}
                  className="rounded-full border border-input bg-background px-2.5 py-0.5 text-xs transition hover:bg-accent disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
            <textarea
              name="notes"
              maxLength={1000}
              rows={2}
              defaultValue={issue.notes ?? ""}
              placeholder="Optional notes — what changed, what you agreed on…"
              className="rounded-md border border-input bg-background px-2 py-1.5 text-xs shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            {state?.ok === false && (
              <p role="alert" className="text-xs text-destructive">{state.error}</p>
            )}
          </form>
        </div>
      )}
    </article>
  );
}
