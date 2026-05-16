"use client";

import { useActionState, useState } from "react";
import { submitIntent, type ActionResult } from "../actions";

const OPTIONS = [
  { value: "argue", label: "I want to argue with someone who'll fight back" },
  { value: "roast", label: "I want to be roasted into action" },
  { value: "mediate", label: "I want help with a relationship dispute" },
  { value: "track", label: "I want to track my own bullshit" },
  { value: "rehearse", label: "I want practice for hard conversations" },
  { value: "explore", label: "Just exploring" },
] as const;

const MAX = 3;

export function IntentForm() {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(submitIntent, null);
  const [picked, setPicked] = useState<Set<string>>(new Set());

  function toggle(v: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(v)) next.delete(v);
      else if (next.size < MAX) next.add(v);
      return next;
    });
  }

  return (
    <form action={action} className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        {OPTIONS.map((o) => {
          const checked = picked.has(o.value);
          const disabled = !checked && picked.size >= MAX;
          return (
            <label
              key={o.value}
              className={`flex items-start gap-3 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm ${checked ? "border-primary bg-primary/5" : ""} ${disabled ? "opacity-50" : ""}`}
            >
              <input
                type="checkbox"
                name="intents"
                value={o.value}
                checked={checked}
                disabled={disabled}
                onChange={() => toggle(o.value)}
                className="mt-0.5 size-4"
              />
              <span>{o.label}</span>
            </label>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground">{picked.size} / {MAX} selected</p>

      {state?.ok === false && <p role="alert" className="text-sm text-destructive">{state.error}</p>}

      <button
        type="submit"
        disabled={pending || picked.size === 0}
        className="mt-2 inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Saving..." : "Continue"}
      </button>
    </form>
  );
}
