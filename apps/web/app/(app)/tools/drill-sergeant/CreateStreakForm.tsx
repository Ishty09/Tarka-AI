"use client";

import { useActionState } from "react";
import { createStreak, type ActionResult } from "./actions";

export function CreateStreakForm() {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(
    createStreak,
    null,
  );

  return (
    <form action={action} className="flex flex-col gap-2 sm:flex-row">
      <input
        name="habit"
        required
        minLength={3}
        maxLength={200}
        placeholder="e.g. Run 4x/week, write 500 words/day"
        className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
      />
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Adding…" : "Add habit"}
      </button>
      {state?.ok === false && (
        <p role="alert" className="text-sm text-destructive sm:absolute sm:mt-12">{state.error}</p>
      )}
    </form>
  );
}
