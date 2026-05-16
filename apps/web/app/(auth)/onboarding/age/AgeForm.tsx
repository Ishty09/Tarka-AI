"use client";

import { useActionState } from "react";
import { submitAge, type ActionResult } from "../actions";

const OPTIONS = [
  { value: "under_16", label: "Under 16" },
  { value: "16_17", label: "16 or 17" },
  { value: "18_plus", label: "18 or older" },
] as const;

export function AgeForm() {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(submitAge, null);

  return (
    <form action={action} className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        {OPTIONS.map((o) => (
          <label
            key={o.value}
            className="flex items-center gap-3 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5"
          >
            <input type="radio" name="age_range" value={o.value} required className="size-4" />
            <span>{o.label}</span>
          </label>
        ))}
      </div>

      {state?.ok === false && <p role="alert" className="text-sm text-destructive">{state.error}</p>}

      <button
        type="submit"
        disabled={pending}
        className="mt-2 inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Saving..." : "Continue"}
      </button>
    </form>
  );
}
