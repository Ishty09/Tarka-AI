"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useTransition } from "react";
import { acknowledgeCookieNotice } from "../_actions/cookie-notice";

// Informational cookie banner (CLAUDE.md §27 step 56, cookie list at
// /legal/cookies). Since Umami is cookieless and the cookies we set are
// strictly necessary, the ePrivacy obligation is to *inform*, not to
// obtain consent for non-essential trackers we don't have.
//
// Pinned to the bottom of the viewport via fixed positioning. Mounts at the
// root layout so it appears on marketing, auth, and (app) routes; the EU
// AI Act modal lives one level deeper (only signed-in users) so the two
// can stack without conflict.

interface Props {
  show: boolean;
  locale: string;
}

export function CookieBanner({ show, locale }: Props) {
  const t = useTranslations();
  const [pending, startTransition] = useTransition();

  if (!show) return null;

  const handleAck = (): void => {
    startTransition(async () => {
      await acknowledgeCookieNotice();
      window.location.reload();
    });
  };

  return (
    <div
      role="region"
      aria-label="Cookie notice"
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 px-4 py-3 shadow-lg backdrop-blur"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-2 text-sm sm:flex-row sm:items-center sm:justify-between">
        <p className="text-muted-foreground">
          {t("cookie_banner.body")}{" "}
          <Link
            href={`/legal/cookies/${locale}`}
            className="underline underline-offset-2"
          >
            {t("cookie_banner.policy_link")}
          </Link>
          .
        </p>
        <button
          type="button"
          onClick={handleAck}
          disabled={pending}
          className="inline-flex shrink-0 items-center justify-center rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium hover:bg-accent hover:text-accent-foreground disabled:opacity-50"
        >
          {pending ? "…" : t("cookie_banner.acknowledge")}
        </button>
      </div>
    </div>
  );
}
