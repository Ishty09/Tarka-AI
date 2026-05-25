"use client";

import { useActionState, useState } from "react";
import { createIssue, type ActionResult } from "./actions";

export function NewIssueForm({ linkId }: { linkId: string }) {
  const [state, formAction, pending] = useActionState<ActionResult | null, FormData>(
    createIssue,
    null,
  );
  const [severity, setSeverity] = useState(5);

  return (
    <form action={formAction} className="mt-3 flex flex-col gap-3">
      <input type="hidden" name="link_id" value={linkId} />
      <input
        type="text"
        name="theme"
        required
        minLength={2}
        maxLength={100}
        placeholder="Theme — e.g. 'splitting bills', 'visiting in-laws', 'late nights'"
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <textarea
        name="description"
        maxLength={1000}
        rows={2}
        placeholder="Optional — context, what each of you wants out of resolving this."
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <label className="flex items-center gap-3 text-xs text-muted-foreground">
        <span className="w-20 shrink-0 font-medium uppercase tracking-wide">Severity</span>
        <input
          type="range"
          name="severity"
          min={1}
          max={10}
          step={1}
          value={severity}
          onChange={(e) => setSeverity(Number(e.target.value))}
          className="flex-1 accent-primary"
        />
        <span className="w-10 text-right text-sm font-semibold tabular-nums">{severity}/10</span>
      </label>
      {state?.ok === false && (
        <p role="alert" className="text-sm text-destructive">{state.error}</p>
      )}
      <button
        type="submit"
        disabled={pending}
        className="inline-flex w-fit items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Saving…" : "Add issue"}
      </button>
    </form>
  );
}
