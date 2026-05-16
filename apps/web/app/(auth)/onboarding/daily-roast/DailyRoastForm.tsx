"use client";

import { useActionState, useState } from "react";
import { submitDailyRoast, type ActionResult } from "../actions";

interface Persona { slug: string; name: string }

export function DailyRoastForm({
  personas,
  personaCarry,
}: {
  personas: Persona[];
  personaCarry: string;
}) {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(submitDailyRoast, null);
  const [enabled, setEnabled] = useState(true);

  return (
    <form action={action} className="flex flex-col gap-4">
      <input type="hidden" name="persona_carry" value={personaCarry} />
      <input type="hidden" name="enabled" value={enabled ? "on" : "off"} />

      <label className="flex items-center gap-3 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="size-4"
        />
        <span className="font-medium">Daily roast at a fixed time</span>
      </label>

      {enabled && (
        <>
          <label htmlFor="time" className="text-sm font-medium">Time (your timezone)</label>
          <input
            id="time"
            name="time"
            type="time"
            required={enabled}
            defaultValue="09:00"
            className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
          />

          <label htmlFor="persona_slug" className="text-sm font-medium">Persona</label>
          <select
            id="persona_slug"
            name="persona_slug"
            required={enabled}
            defaultValue={personaCarry || personas[0]?.slug || ""}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
          >
            {personas.map((p) => (
              <option key={p.slug} value={p.slug}>{p.name}</option>
            ))}
          </select>

          <p className="text-xs text-muted-foreground">
            We&apos;ll ask for push permission after this step. Email works as a fallback.
          </p>
        </>
      )}

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
