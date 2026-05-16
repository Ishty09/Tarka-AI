"use client";

import { useActionState, useState } from "react";
import { submitPersonaPick, type ActionResult } from "../actions";

interface Persona {
  slug: string;
  name: string;
  description: string | null;
  category: string;
  locale: string;
}

export function PersonaPicker({ personas }: { personas: Persona[] }) {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(submitPersonaPick, null);
  const [picked, setPicked] = useState<string | null>(null);

  if (personas.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          No personas seeded yet for your locale. Skip for now — you can install one later.
        </p>
        <a
          href="/onboarding/daily-roast"
          className="inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
        >
          Skip
        </a>
      </div>
    );
  }

  return (
    <form action={action} className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        {personas.map((p) => {
          const checked = picked === p.slug;
          return (
            <label
              key={p.slug}
              className={`flex flex-col gap-1 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm ${checked ? "border-primary bg-primary/5" : ""}`}
            >
              <div className="flex items-center gap-3">
                <input
                  type="radio"
                  name="persona_slug"
                  value={p.slug}
                  checked={checked}
                  onChange={() => setPicked(p.slug)}
                  className="size-4"
                />
                <span className="font-medium">{p.name}</span>
                <span className="ml-auto text-xs text-muted-foreground">{p.category}</span>
              </div>
              {p.description && <p className="pl-7 text-xs text-muted-foreground">{p.description}</p>}
            </label>
          );
        })}
      </div>

      {state?.ok === false && <p role="alert" className="text-sm text-destructive">{state.error}</p>}

      <button
        type="submit"
        disabled={pending || !picked}
        className="mt-2 inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Saving..." : "Install and continue"}
      </button>
    </form>
  );
}
