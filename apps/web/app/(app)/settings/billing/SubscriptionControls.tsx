"use client";

import { useFormState, useFormStatus } from "react-dom";
import type { Tier } from "@quarrel/shared/constants";
import {
  cancelSubscriptionAction,
  resumeSubscriptionAction,
  switchTierAction,
  type ActionResult,
} from "./actions";

interface Props {
  tier: Tier;
  cancelAtPeriodEnd: boolean;
  currentPeriodEnd: string;
}

const initialState: ActionResult | null = null;

export function SubscriptionControls({
  tier,
  cancelAtPeriodEnd,
  currentPeriodEnd,
}: Props) {
  // Three permutations: queued to cancel → show "Resume"; active and Pro →
  // offer "Switch to Max"; active and Max → only show "Cancel". Free is
  // handled upstream (the page renders an "Upgrade" CTA instead).
  if (cancelAtPeriodEnd) {
    return <ResumeBlock currentPeriodEnd={currentPeriodEnd} />;
  }

  return (
    <div className="flex flex-col gap-4">
      {tier === "pro" && <SwitchToMaxBlock />}
      <CancelBlock currentPeriodEnd={currentPeriodEnd} />
    </div>
  );
}

function CancelBlock({ currentPeriodEnd }: { currentPeriodEnd: string }) {
  const [state, formAction] = useFormState(
    async (_prev: ActionResult | null) => cancelSubscriptionAction(),
    initialState,
  );
  return (
    <form action={formAction} className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">
        Cancel keeps your tier active until{" "}
        <strong>{new Date(currentPeriodEnd).toLocaleDateString()}</strong>, then
        drops you to Free. You can resume any time before then.
      </p>
      <SubmitButton
        label="Cancel at period end"
        pendingLabel="Cancelling..."
        variant="ghost"
      />
      {state && !state.ok && (
        <p role="alert" className="text-xs text-destructive">{state.error}</p>
      )}
      {state?.ok && (
        <p className="text-xs text-emerald-600">
          Queued. You&apos;ll keep access until {new Date(currentPeriodEnd).toLocaleDateString()}.
        </p>
      )}
    </form>
  );
}

function ResumeBlock({ currentPeriodEnd }: { currentPeriodEnd: string }) {
  const [state, formAction] = useFormState(
    async (_prev: ActionResult | null) => resumeSubscriptionAction(),
    initialState,
  );
  return (
    <form action={formAction} className="flex flex-col gap-2">
      <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
        Cancellation queued for{" "}
        <strong>{new Date(currentPeriodEnd).toLocaleDateString()}</strong>.
      </div>
      <SubmitButton
        label="Resume subscription"
        pendingLabel="Resuming..."
        variant="primary"
      />
      {state && !state.ok && (
        <p role="alert" className="text-xs text-destructive">{state.error}</p>
      )}
      {state?.ok && <p className="text-xs text-emerald-600">Resumed.</p>}
    </form>
  );
}

function SwitchToMaxBlock() {
  const [state, formAction] = useFormState(switchTierAction, initialState);
  return (
    <form action={formAction} className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">
        Move to Max now and Polar prorates the rest of this billing period
        against the new plan.
      </p>
      <input type="hidden" name="tier" value="max" />
      <select
        name="interval"
        defaultValue="monthly"
        className="w-fit rounded-md border border-input bg-background px-2 py-1 text-xs"
      >
        <option value="monthly">Max — monthly</option>
        <option value="annual">Max — annual</option>
      </select>
      <SubmitButton
        label="Switch to Max"
        pendingLabel="Switching..."
        variant="primary"
      />
      {state && !state.ok && (
        <p role="alert" className="text-xs text-destructive">{state.error}</p>
      )}
      {state?.ok && (
        <p className="text-xs text-emerald-600">
          Switched. The tier badge will update once Polar fires the
          subscription.updated webhook.
        </p>
      )}
    </form>
  );
}

function SubmitButton({
  label,
  pendingLabel,
  variant,
}: {
  label: string;
  pendingLabel: string;
  variant: "primary" | "ghost";
}) {
  const { pending } = useFormStatus();
  const cls =
    variant === "primary"
      ? "bg-primary text-primary-foreground"
      : "border border-input bg-background";
  return (
    <button
      type="submit"
      disabled={pending}
      className={`inline-flex w-fit items-center justify-center rounded-md ${cls} px-3 py-1 text-xs font-medium shadow-sm hover:opacity-90 disabled:opacity-50`}
    >
      {pending ? pendingLabel : label}
    </button>
  );
}
