"use client";

import { useTransition } from "react";
import { setCrossFactConsent } from "../actions";

interface Props {
  linkId: string;
  yourConsent: boolean;
  partnerConsent: boolean;
  partnerName: string;
}

// §9.3.1 cross-fact consent strip. Renders inside the couples chat
// header so partners can see at a glance whether the mediator can read
// each other's facts — and flip their own toggle off any time.

export function CrossFactConsent({
  linkId,
  yourConsent,
  partnerConsent,
  partnerName,
}: Props) {
  const [pending, startTransition] = useTransition();

  const bothOn = yourConsent && partnerConsent;
  const status = bothOn
    ? `On — mediator can reference both your facts and ${partnerName}'s.`
    : yourConsent
    ? `Waiting on ${partnerName}. Mediator only sees the current speaker's facts.`
    : partnerConsent
    ? `${partnerName} said yes; toggle yours to enable.`
    : "Off — mediator only sees the current speaker's facts.";

  function toggle() {
    const form = new FormData();
    form.set("link_id", linkId);
    form.set("enabled", String(!yourConsent));
    startTransition(async () => {
      await setCrossFactConsent(form);
    });
  }

  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 border-b px-4 py-2 text-xs ${
        bothOn
          ? "border-emerald-500/30 bg-emerald-500/5"
          : "border-input bg-muted/40"
      }`}
    >
      <div className="flex flex-col">
        <span className="font-medium">Cross-fact retrieval</span>
        <span className="text-muted-foreground">{status}</span>
      </div>
      <button
        type="button"
        onClick={toggle}
        disabled={pending}
        aria-pressed={yourConsent}
        className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 font-medium transition disabled:opacity-50 ${
          yourConsent
            ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200"
            : "border-input bg-background hover:bg-accent"
        }`}
      >
        <span
          aria-hidden
          className={`size-2 rounded-full ${yourConsent ? "bg-emerald-500" : "bg-muted-foreground/50"}`}
        />
        {pending ? "Saving…" : yourConsent ? "Your consent: on" : "Your consent: off"}
      </button>
    </div>
  );
}
