"use server";

import { cookies } from "next/headers";
import {
  COOKIE_NOTICE_COOKIE,
  COOKIE_NOTICE_TTL_SECONDS,
} from "@/lib/cookie-notice";

// Server action invoked from the "Got it" button on the global cookie
// banner. Sets a 1-year cookie carrying the dismissal timestamp so the
// banner stops rendering for this device.

export async function acknowledgeCookieNotice(): Promise<void> {
  const store = await cookies();
  store.set({
    name: COOKIE_NOTICE_COOKIE,
    value: new Date().toISOString(),
    maxAge: COOKIE_NOTICE_TTL_SECONDS,
    path: "/",
    sameSite: "lax",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
  });
}
