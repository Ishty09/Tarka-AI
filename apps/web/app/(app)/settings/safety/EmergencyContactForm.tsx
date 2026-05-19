"use client";

import { useFormState, useFormStatus } from "react-dom";
import { updateEmergencyContact, type ActionResult } from "../actions";

interface Props {
  initial: { name: string; email: string };
}

const initialState: ActionResult | null = null;

export function EmergencyContactForm({ initial }: Props) {
  const [state, formAction] = useFormState(updateEmergencyContact, initialState);
  return (
    <form action={formAction} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">Contact name</span>
        <input
          type="text"
          name="emergency_contact_name"
          defaultValue={initial.name}
          maxLength={120}
          placeholder="A trusted friend or family member"
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">Contact email</span>
        <input
          type="email"
          name="emergency_contact_email"
          defaultValue={initial.email}
          maxLength={254}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </label>
      <p className="text-[11px] text-muted-foreground">
        We will only contact this person if you express clear crisis signals
        more than once in 24 hours. Clear both fields to remove.
      </p>
      <div className="flex items-center justify-between">
        {state && !state.ok && (
          <p role="alert" className="text-sm text-destructive">{state.error}</p>
        )}
        {state?.ok && <p className="text-sm text-emerald-600">Saved.</p>}
        <SubmitButton />
      </div>
    </form>
  );
}

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="ml-auto inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
    >
      {pending ? "Saving..." : "Save"}
    </button>
  );
}
