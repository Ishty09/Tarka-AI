// next-intl request config: chooses the user's locale per request and
// loads the matching messages bundle. Called by the next-intl plugin
// for every server render.
//
// Resolution order:
//   1. Signed-in users → profiles.locale (Supabase RLS-bound read).
//   2. Cookie `NEXT_LOCALE` (set on sign-in + by the locale switcher).
//   3. Accept-Language header negotiation.
//   4. defaultLocale ("en").

import { cookies, headers } from "next/headers";
import { getRequestConfig } from "next-intl/server";
import { createServerSupabase } from "@/lib/supabase/server";
import {
  LOCALE_COOKIE,
  defaultLocale,
  isSupportedLocale,
  negotiateLocale,
} from "./routing";

async function loadMessages(locale: string): Promise<Record<string, string>> {
  // Static imports keep tree-shaking + edge-runtime compatibility intact.
  // Add new locales here as they land (§27 step 53 backfill).
  const bundles: Record<string, () => Promise<{ default: Record<string, string> }>> = {
    en: () => import("../messages/en.json"),
    bn: () => import("../messages/bn.json"),
    hi: () => import("../messages/hi.json"),
    es: () => import("../messages/es.json"),
    pt: () => import("../messages/pt.json"),
    ar: () => import("../messages/ar.json"),
  };
  const loader = bundles[locale] ?? bundles[defaultLocale];
  if (!loader) return {};
  const mod = await loader();
  return mod.default;
}

async function resolveLocale(): Promise<string> {
  // 1. Profile (only if a session exists).
  try {
    const supabase = await createServerSupabase();
    const { data: { user } } = await supabase.auth.getUser();
    if (user) {
      const { data } = await supabase
        .from("profiles")
        .select("locale")
        .eq("id", user.id)
        .maybeSingle();
      if (data?.locale && isSupportedLocale(data.locale)) return data.locale;
    }
  } catch {
    // Supabase unavailable mid-render — fall through.
  }

  // 2. Cookie.
  const store = await cookies();
  const cookieValue = store.get(LOCALE_COOKIE)?.value;
  if (isSupportedLocale(cookieValue)) return cookieValue;

  // 3. Accept-Language.
  const h = await headers();
  return negotiateLocale(h.get("accept-language"));
}

export default getRequestConfig(async () => {
  const locale = await resolveLocale();
  const messages = await loadMessages(locale);
  return { locale, messages };
});
