import type { LocalisedContent } from "../types";

const en = `# Cookie Policy

Quarrel AI is intentionally light on cookies. Our analytics tool (Umami, self-hosted) is **cookieless** and does not assign persistent visitor identifiers. The cookies we do set are listed below; each one is either strictly necessary for the Service to work or a clearly named preference cookie.

We do not set advertising cookies. We do not embed third-party trackers (no Google Analytics, no Meta Pixel, no LinkedIn Insight Tag, no TikTok Pixel).

## 1. Strictly necessary cookies

These cookies are required for the Service to function. You cannot opt out of them without breaking core flows like sign-in.

- **Supabase Auth session cookies** (\`sb-*\`) — set by Supabase to keep you signed in. Lifetime is the session timeout you configured (default 1 hour for the access token, 7 days for the refresh token). Domain: our app domain.
- **CSRF token cookie** (\`__quarrel_csrf\`) — protects form submissions against cross-site request forgery. Lifetime: session.
- **Polar checkout cookies** — set by Polar.sh on the checkout subdomain during payment. We do not control these; Polar's cookie disclosure applies on their pages.

## 2. Preference cookies

- **\`NEXT_LOCALE\`** — stores the language you have chosen. Set when you change your locale in onboarding, in \`/settings\`, or via the language switcher. Lifetime: 1 year. Domain: our app domain.

That is the complete list. We will update this page if we add anything.

## 3. Analytics (cookieless)

Our product analytics use Umami, which fingerprints by salt-of-the-day + truncated IP + user agent to derive a daily-rotating, non-personal "visitor" identifier. No cookie is set. The identifier resets every day; it cannot be used to track you across days or sessions, and it is not joined with your account.

The data we collect is page paths, event names, country (from IP geolocation, then IP discarded), referrer, browser, and OS. The §20 analytics event list in our product reference enumerates the named events.

## 4. Do Not Track

We honour Global Privacy Control (GPC) signals on the legal documents and marketing pages — analytics is suppressed when GPC is set. We do not currently honour browser-level "Do Not Track" headers because the standard has been deprecated; GPC is the de-facto replacement.

## 5. Controlling cookies

You can clear or block cookies in your browser settings. Blocking the strictly-necessary cookies will sign you out and prevent you from logging back in. Blocking the preference cookie resets your locale on each visit.

## 6. Changes

We update this policy when our cookie use changes. Material changes will be announced at least 14 days in advance.

Questions: **privacy@quarrel.ai**.
`;

export const cookies: LocalisedContent = {
  en: {
    title: "Cookie Policy",
    lastUpdated: "2026-05-21",
    summary:
      "Quarrel uses only the cookies necessary for sign-in, CSRF, payments, and your locale preference. Analytics are cookieless.",
    markdown: en,
  },
  bn: null,
  hi: null,
  es: null,
  pt: null,
  ar: null,
};
