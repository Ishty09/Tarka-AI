"use client";

import { useActionState, useEffect, useState } from "react";
import { LOCALES } from "@quarrel/shared/constants";
import { submitLocale, type ActionResult } from "../actions";

const LOCALE_LABELS: Record<string, string> = {
  en: "English",
  bn: "বাংলা",
  hi: "हिन्दी",
  es: "Español",
  pt: "Português",
  it: "Italiano",
  ru: "Русский",
  ar: "العربية",
  ko: "한국어",
  ja: "日本語",
  de: "Deutsch",
  fr: "Français",
  zh: "中文",
  id: "Bahasa Indonesia",
  vi: "Tiếng Việt",
  he: "עברית",
};

export function LocaleForm({
  defaultLocale,
  defaultCountry,
  defaultTimezone,
}: {
  defaultLocale: string;
  defaultCountry: string;
  defaultTimezone: string;
}) {
  const [state, action, pending] = useActionState<ActionResult | null, FormData>(submitLocale, null);
  const [tz, setTz] = useState(defaultTimezone);
  const [country, setCountry] = useState(defaultCountry);

  useEffect(() => {
    // Auto-detect once on mount. User can override.
    try {
      const detectedTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (detectedTz && defaultTimezone === "UTC") setTz(detectedTz);
    } catch { /* ignore */ }
    try {
      const locale = navigator.language || "";
      const region = locale.split("-")[1];
      if (region && defaultCountry === "US") setCountry(region.toUpperCase());
    } catch { /* ignore */ }
  }, [defaultTimezone, defaultCountry]);

  return (
    <form action={action} className="flex flex-col gap-3">
      <label htmlFor="locale" className="text-sm font-medium">Language</label>
      <select
        id="locale"
        name="locale"
        defaultValue={defaultLocale}
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
      >
        {LOCALES.map((l) => (
          <option key={l} value={l}>{LOCALE_LABELS[l] ?? l}</option>
        ))}
      </select>

      <label htmlFor="country_code" className="text-sm font-medium">Country (ISO 2-letter)</label>
      <input
        id="country_code"
        name="country_code"
        required
        minLength={2}
        maxLength={2}
        value={country}
        onChange={(e) => setCountry(e.target.value.toUpperCase())}
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm uppercase"
      />

      <label htmlFor="timezone" className="text-sm font-medium">Timezone</label>
      <input
        id="timezone"
        name="timezone"
        required
        value={tz}
        onChange={(e) => setTz(e.target.value)}
        className="rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm"
      />

      {state?.ok === false && <p role="alert" className="text-sm text-destructive">{state.error}</p>}

      <button
        type="submit"
        disabled={pending}
        className="mt-2 inline-flex items-center justify-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Saving..." : "Continue"}
      </button>
    </form>
  );
}
