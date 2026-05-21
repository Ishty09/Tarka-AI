"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useTransition } from "react";
import { acknowledgeAiDisclosure } from "../_actions/eu-ai-act";

// First-run EU AI Act Article 50 modal (CLAUDE.md §27 step 55).
//
// Renders only when the parent server layout passes `show={true}` — that flag
// comes from hasAcknowledgedAiDisclosure() in lib/eu-ai-act.ts. The modal has
// no close affordance other than the explicit acknowledgement button: the
// disclosure is mandatory before further interaction.

interface Props {
  show: boolean;
  locale: string;
}

export function EuAiActModal({ show, locale }: Props) {
  const t = useTranslations();
  const [pending, startTransition] = useTransition();

  if (!show) return null;

  const handleAck = (): void => {
    startTransition(async () => {
      await acknowledgeAiDisclosure();
      // Server action will set the cookie; we trigger a soft reload of the
      // current route so the layout re-reads the cookie and stops rendering
      // this modal. router.refresh() preserves scroll + form state.
      window.location.reload();
    });
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="eu-ai-act-title"
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
    >
      <div className="w-full max-w-md rounded-lg bg-background p-6 shadow-xl">
        <h2 id="eu-ai-act-title" className="text-lg font-semibold tracking-tight">
          {t("ai_disclosure.title")}
        </h2>
        <p className="mt-3 text-sm text-muted-foreground">
          {t("ai_disclosure.body")}
        </p>
        <p className="mt-4 text-sm">
          <Link
            href={`/legal/ai-disclosure/${locale}`}
            className="underline underline-offset-2"
          >
            {t("ai_disclosure.detail_link")} →
          </Link>
        </p>
        <div className="mt-6 flex justify-end">
          <button
            type="button"
            onClick={handleAck}
            disabled={pending}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
          >
            {pending ? "…" : t("ai_disclosure.acknowledge")}
          </button>
        </div>
      </div>
    </div>
  );
}
