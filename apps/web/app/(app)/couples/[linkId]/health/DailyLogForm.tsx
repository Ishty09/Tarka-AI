"use client";

import { useActionState, useState } from "react";
import { saveDailyLog, type ActionResult } from "./actions";

interface InitialLog {
  effort_rating: number;
  partner_appreciation: string | null;
  frustration: string | null;
}

export function DailyLogForm({
  linkId,
  initial,
}: {
  linkId: string;
  initial: InitialLog | null;
}) {
  const [state, formAction, pending] = useActionState<ActionResult | null, FormData>(
    saveDailyLog,
    null,
  );
  const [effort, setEffort] = useState(initial?.effort_rating ?? 3);

  return (
    <form action={formAction} className="mt-3 flex flex-col gap-3">
      <input type="hidden" name="link_id" value={linkId} />

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Effort today
        </span>
        <div className="flex items-center gap-3">
          <input
            type="range"
            name="effort_rating"
            min={1}
            max={5}
            step={1}
            value={effort}
            onChange={(e) => setEffort(Number(e.target.value))}
            className="flex-1 accent-primary"
          />
          <span className="w-12 text-right text-lg font-semibold tabular-nums">
            {effort}/5
          </span>
        </div>
        <div className="flex justify-between px-0.5 text-[10px] text-muted-foreground">
          <span>phoning it in</span>
          <span>showed up fully</span>
        </div>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Best thing your partner did today
        </span>
        <input
          type="text"
          name="partner_appreciation"
          defaultValue={initial?.partner_appreciation ?? ""}
          maxLength={300}
          placeholder="optional — one sentence"
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Something that frustrated you
        </span>
        <input
          type="text"
          name="frustration"
          defaultValue={initial?.frustration ?? ""}
          maxLength={300}
          placeholder="optional — one sentence. They see this."
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </label>

      {state?.ok === false && (
        <p role="alert" className="text-sm text-destructive">{state.error}</p>
      )}
      {state?.ok === true && (
        <p className="text-sm text-emerald-600 dark:text-emerald-400">Saved.</p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="inline-flex w-fit items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Saving…" : initial ? "Update today" : "Save check-in"}
      </button>
    </form>
  );
}
