"use client";

import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";
import { updateNotifications, type ActionResult } from "../actions";

interface Persona {
  slug: string;
  name: string;
}

interface Props {
  initial: {
    notification_email: boolean;
    notification_push: boolean;
    marketing_email_consent: boolean;
    daily_roast_time: string;
    daily_roast_persona_slug: string;
  };
  personas: Persona[];
}

const initialState: ActionResult | null = null;

export function NotificationsForm({ initial, personas }: Props) {
  const [dailyOn, setDailyOn] = useState<boolean>(
    initial.daily_roast_time.length > 0 || initial.daily_roast_persona_slug.length > 0,
  );
  const [state, formAction] = useFormState(updateNotifications, initialState);

  return (
    <form action={formAction} className="flex flex-col gap-6">
      <ToggleField
        label="Daily Roast"
        hint="A scheduled push + email at your chosen time."
        name="daily_roast_enabled"
        checked={dailyOn}
        onChange={setDailyOn}
      />

      {dailyOn && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Field label="Time (24h)">
            <input
              type="time"
              name="daily_roast_time"
              defaultValue={initial.daily_roast_time}
              required
              className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </Field>
          <Field label="Roast persona">
            <select
              name="daily_roast_persona_slug"
              defaultValue={initial.daily_roast_persona_slug}
              required
              className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">Pick a persona…</option>
              {personas.map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
      )}

      <hr className="border-input" />

      <ToggleField
        label="Email notifications"
        hint="Includes the Daily Roast, Mirror Reports, and account events."
        name="notification_email"
        checked={initial.notification_email}
      />
      <ToggleField
        label="Push notifications"
        hint="Per-device subscriptions are managed at first use."
        name="notification_push"
        checked={initial.notification_push}
      />
      <ToggleField
        label="Marketing emails"
        hint="Tips, new personas, and launch announcements. Off by default."
        name="marketing_email_consent"
        checked={initial.marketing_email_consent}
      />

      <div className="mt-2 flex items-center justify-between">
        {state && !state.ok && (
          <p role="alert" className="text-sm text-destructive">{state.error}</p>
        )}
        {state?.ok && <p className="text-sm text-emerald-600">Saved.</p>}
        <SubmitButton />
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-sm font-medium">{label}</span>
      {children}
    </label>
  );
}

function ToggleField({
  label,
  hint,
  name,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  name: string;
  checked: boolean;
  onChange?: (next: boolean) => void;
}) {
  // Use defaultChecked when there's no external state binding so RSC props
  // can still flow through; otherwise treat it controlled.
  const controlled = onChange !== undefined;
  return (
    <label className="flex items-start justify-between gap-4">
      <div>
        <span className="text-sm font-medium">{label}</span>
        {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
      </div>
      <input
        type="checkbox"
        name={name}
        {...(controlled
          ? { checked, onChange: (e) => onChange!(e.currentTarget.checked) }
          : { defaultChecked: checked })}
        className="mt-1 size-4 rounded border-input"
      />
    </label>
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
