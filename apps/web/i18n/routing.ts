// i18n routing config (CLAUDE.md §8, §11 step 3, §27 step 52).
//
// We don't prefix URLs with locales — every authenticated user already
// has profile.locale and we set a cookie at sign-in to honor it. This
// keeps marketing pages (which already exist at `/`) from needing a
// `/en/` redirect, and simplifies the existing supabase + admin
// middleware chain.

import { LOCALES, DEFAULT_LOCALE, type Locale } from "@quarrel/shared/constants";

export const LOCALE_COOKIE = "NEXT_LOCALE";

export const supportedLocales: readonly Locale[] = LOCALES;
export const defaultLocale: Locale = DEFAULT_LOCALE;

export function isSupportedLocale(value: string | undefined | null): value is Locale {
  return typeof value === "string" && (supportedLocales as readonly string[]).includes(value);
}

/** Pick the best locale from an Accept-Language header. */
export function negotiateLocale(acceptLanguage: string | null): Locale {
  if (!acceptLanguage) return defaultLocale;
  const candidates = acceptLanguage
    .split(",")
    .map((part) => part.trim().split(";")[0]?.toLowerCase().split("-")[0])
    .filter((s): s is string => Boolean(s));
  for (const c of candidates) {
    if (isSupportedLocale(c)) return c;
  }
  return defaultLocale;
}
