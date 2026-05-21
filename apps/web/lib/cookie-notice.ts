// Cookie notice helpers (CLAUDE.md §27 step 56, cookie list in
// /legal/cookies/en).
//
// Quarrel sets only strictly-necessary cookies (auth session, CSRF, locale,
// EU AI Act ack); product analytics (Umami) are cookieless. The banner is
// therefore informational — no accept/decline choice. Once the visitor
// dismisses it we set a long-lived cookie so the banner stays out of the
// way on future visits to this device.
//
// The write side lives in app/_actions/cookie-notice.ts because cookie
// mutation must happen in a Server Action.

import { cookies } from "next/headers";

export const COOKIE_NOTICE_COOKIE = "quarrel_cookie_notice_ack";
export const COOKIE_NOTICE_TTL_SECONDS = 60 * 60 * 24 * 365;

export async function hasAcknowledgedCookieNotice(): Promise<boolean> {
  const store = await cookies();
  const value = store.get(COOKIE_NOTICE_COOKIE)?.value;
  return Boolean(value && value.length > 0);
}
