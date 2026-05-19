"use client";

import { useFormState, useFormStatus } from "react-dom";
import {
  startCheckout,
  type ActionResult,
} from "@/app/(app)/settings/billing/actions";

interface Props {
  tier: "pro" | "max";
  interval: "monthly" | "annual";
}

const initialState: ActionResult | null = null;

export function CheckoutForm({ tier, interval }: Props) {
  const [state, formAction] = useFormState(startCheckout, initialState);
  return (
    <form action={formAction} className="flex flex-col gap-2">
      <input type="hidden" name="tier" value={tier} />
      <input type="hidden" name="interval" value={interval} />
      <SubmitButton tier={tier} />
      {state && !state.ok && (
        <p role="alert" className="text-xs text-destructive">
          {state.error}
        </p>
      )}
    </form>
  );
}

function SubmitButton({ tier }: { tier: "pro" | "max" }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
    >
      {pending ? "Redirecting..." : `Upgrade to ${tier === "pro" ? "Pro" : "Max"}`}
    </button>
  );
}
