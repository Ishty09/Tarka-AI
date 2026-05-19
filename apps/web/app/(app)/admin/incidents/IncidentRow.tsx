"use client";

import Link from "next/link";
import { useFormState, useFormStatus } from "react-dom";
import { reviewIncidentAction, type ActionResult } from "../actions";

interface Props {
  incident: {
    id: number;
    user_id: string | null;
    conversation_id: string | null;
    message_id: number | null;
    category: string;
    verdict: string;
    action_taken: string;
    created_at: string;
  };
}

const initialState: ActionResult | null = null;

export function IncidentRow({ incident }: Props) {
  const [state, action] = useFormState(reviewIncidentAction, initialState);
  return (
    <article className="flex flex-col gap-2 rounded-md border border-input bg-card p-4 shadow-sm">
      <header className="flex items-baseline justify-between">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-destructive">
            {incident.category}
          </h3>
          <p className="text-[11px] text-muted-foreground">
            #{incident.id} · verdict <code>{incident.verdict}</code> · action{" "}
            <code>{incident.action_taken}</code> ·{" "}
            {new Date(incident.created_at).toLocaleString()}
          </p>
        </div>
        {incident.conversation_id && (
          <Link
            href={`/chat/${incident.conversation_id}`}
            className="text-xs underline text-muted-foreground"
          >
            Open chat →
          </Link>
        )}
      </header>
      <form action={action} className="flex flex-wrap items-center gap-2">
        <input type="hidden" name="incident_id" value={incident.id} />
        <input
          type="text"
          name="notes"
          placeholder="Reviewer notes (optional)"
          maxLength={2000}
          className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-xs"
        />
        <ReviewButton />
      </form>
      {state && !state.ok && (
        <p role="alert" className="text-xs text-destructive">{state.error}</p>
      )}
      {state?.ok && <p className="text-xs text-emerald-600">Reviewed.</p>}
    </article>
  );
}

function ReviewButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
    >
      {pending ? "..." : "Mark reviewed"}
    </button>
  );
}
