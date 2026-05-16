"use client";

import { useActionState } from "react";
import { submitEmergency, type ActionResult } from "../actions";

export function EmergencyForm({ personaCarry }: { personaCarry: string }) {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(submitEmergency, null);

  return (
    <form action={action} className="flex flex-col gap-3">
      <input type="hidden" name="persona_carry" value={personaCarry} />

      <label htmlFor="name" className="text-sm font-medium">Name</label>
      <input
        id="name"
        name="name"
        maxLength={120}
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
      />

      <label htmlFor="email" className="text-sm font-medium">Email</label>
      <input
        id="email"
        name="email"
        type="email"
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
      />

      <p className="text-xs text-muted-foreground">
        We will only contact this person if you express clear crisis signals more than once in 24 hours.
      </p>

      {state?.ok === false && <p role="alert" className="text-sm text-destructive">{state.error}</p>}

      <div className="mt-2 flex gap-2">
        <button
          type="submit"
          name="skip"
          value="true"
          disabled={pending}
          className="flex-1 inline-flex items-center justify-center rounded-md border border-input bg-background px-3 py-2 text-sm font-medium shadow-sm hover:bg-accent disabled:opacity-50"
        >
          Skip
        </button>
        <button
          type="submit"
          disabled={pending}
          className="flex-1 inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "Saving..." : "Save and continue"}
        </button>
      </div>
    </form>
  );
}
