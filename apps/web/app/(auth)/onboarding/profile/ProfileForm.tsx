"use client";

import { useActionState } from "react";
import { submitProfile, type ActionResult } from "../actions";

export function ProfileForm({
  defaultUsername,
  defaultDisplayName,
}: {
  defaultUsername: string;
  defaultDisplayName: string;
}) {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(submitProfile, null);

  return (
    <form action={action} className="flex flex-col gap-3">
      <label htmlFor="username" className="text-sm font-medium">Username</label>
      <input
        id="username"
        name="username"
        required
        minLength={3}
        maxLength={30}
        pattern="^[a-z0-9_]+$"
        defaultValue={defaultUsername}
        autoComplete="username"
        placeholder="e.g. honest_rabbi"
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />

      <label htmlFor="display_name" className="text-sm font-medium">Display name</label>
      <input
        id="display_name"
        name="display_name"
        required
        maxLength={60}
        defaultValue={defaultDisplayName}
        autoComplete="name"
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />

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
