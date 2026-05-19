"use client";

import { useFormState, useFormStatus } from "react-dom";
import { LOCALES } from "@quarrel/shared/constants";
import { updateProfile, type ActionResult } from "./actions";

interface Props {
  initial: {
    display_name: string;
    avatar_url: string;
    locale: string;
    country_code: string;
    timezone: string;
    username: string;
  };
}

const initialState: ActionResult | null = null;

export function ProfileForm({ initial }: Props) {
  const [state, formAction] = useFormState(updateProfile, initialState);

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <Field
        label="Username"
        hint="Username changes are restricted. Contact support to rename."
      >
        <input
          type="text"
          value={initial.username}
          readOnly
          className="cursor-not-allowed rounded-md border border-input bg-muted px-3 py-2 text-sm text-muted-foreground"
        />
      </Field>

      <Field label="Display name">
        <input
          type="text"
          name="display_name"
          defaultValue={initial.display_name}
          required
          maxLength={60}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </Field>

      <Field label="Avatar URL" hint="Optional. Paste a hosted image URL.">
        <input
          type="url"
          name="avatar_url"
          defaultValue={initial.avatar_url}
          maxLength={500}
          placeholder="https://"
          className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </Field>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Field label="Locale">
          <select
            name="locale"
            defaultValue={initial.locale}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {LOCALES.map((loc) => (
              <option key={loc} value={loc}>{loc}</option>
            ))}
          </select>
        </Field>

        <Field label="Country (ISO-3166)">
          <input
            type="text"
            name="country_code"
            defaultValue={initial.country_code}
            maxLength={2}
            minLength={2}
            required
            className="rounded-md border border-input bg-background px-3 py-2 text-sm uppercase shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </Field>

        <Field label="Timezone (IANA)">
          <input
            type="text"
            name="timezone"
            defaultValue={initial.timezone}
            required
            placeholder="America/New_York"
            className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </Field>
      </div>

      <div className="mt-2 flex items-center justify-between">
        {state && !state.ok && (
          <p role="alert" className="text-sm text-destructive">{state.error}</p>
        )}
        {state?.ok && (
          <p className="text-sm text-emerald-600">Saved.</p>
        )}
        <SubmitButton />
      </div>
    </form>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
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
