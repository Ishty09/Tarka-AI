"use client";

import Link from "next/link";
import { useActionState } from "react";
import { submitLegal, type ActionResult } from "../actions";

export function LegalForm({ personaCarry }: { personaCarry: string }) {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(submitLegal, null);

  return (
    <form action={action} className="flex flex-col gap-3">
      <input type="hidden" name="persona_carry" value={personaCarry} />

      <label className="flex items-start gap-3 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm">
        <input type="checkbox" name="privacy" value="on" required className="mt-0.5 size-4" />
        <span>
          I have read the <Link href="/legal/privacy/en" className="underline">Privacy Policy</Link>.
        </span>
      </label>

      <label className="flex items-start gap-3 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm">
        <input type="checkbox" name="terms" value="on" required className="mt-0.5 size-4" />
        <span>
          I accept the <Link href="/legal/terms/en" className="underline">Terms of Service</Link>.
        </span>
      </label>

      <label className="flex items-start gap-3 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm">
        <input type="checkbox" name="marketing" value="on" className="mt-0.5 size-4" />
        <span>Send me product updates by email. (Optional)</span>
      </label>

      {state?.ok === false && <p role="alert" className="text-sm text-destructive">{state.error}</p>}

      <button
        type="submit"
        disabled={pending}
        className="mt-2 inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Finishing..." : "Start fighting"}
      </button>
    </form>
  );
}
