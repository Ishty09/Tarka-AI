import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import type { Locale } from "@quarrel/shared/constants";
import { isSupportedLocale, negotiateLocale } from "@/i18n/routing";
import {
  DOCUMENT_LABELS,
  LEGAL_DOC_TYPES,
  LEGAL_LOCALES,
  resolveDocument,
} from "@/lib/legal";

export const metadata: Metadata = {
  title: "Legal | Quarrel",
  description:
    "Quarrel AI legal documents — Privacy, Terms, AI Disclosure, Acceptable Use, Cookies, and the Data Processing Agreement.",
};

// Legal hub. Auto-detects locale from Accept-Language and links each
// document to the matching /legal/<type>/<locale> route. We don't read the
// LOCALE cookie here on purpose — this page is also surfaced from emails
// and SEO snippets where the visitor may not be signed in.

async function detectLocale(): Promise<Locale> {
  const h = await headers();
  const cookieLocale = h.get("x-locale-hint");
  if (cookieLocale && isSupportedLocale(cookieLocale)) return cookieLocale;
  return negotiateLocale(h.get("accept-language"));
}

export default async function LegalIndexPage() {
  const locale = await detectLocale();

  return (
    <main className="mx-auto w-full max-w-2xl px-6 py-12">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Legal</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The terms, policies, and disclosures that govern Quarrel AI. Each
          document is available in the launch six locales:{" "}
          {LEGAL_LOCALES.join(", ")}. Other locales fall back to the English
          source until a localised version lands.
        </p>
      </header>

      <ul className="mt-8 grid gap-4">
        {LEGAL_DOC_TYPES.map((type) => {
          const resolved = resolveDocument(type, locale);
          const summary = resolved?.content.summary ?? "";
          const lastUpdated = resolved?.content.lastUpdated ?? "";
          return (
            <li
              key={type}
              className="rounded-lg border bg-card p-5 text-sm shadow-sm"
            >
              <div className="flex items-baseline justify-between gap-4">
                <Link
                  href={`/legal/${type}/${locale}`}
                  className="text-base font-semibold underline underline-offset-2"
                >
                  {DOCUMENT_LABELS[type]}
                </Link>
                {lastUpdated ? (
                  <span className="text-xs uppercase tracking-wide text-muted-foreground">
                    Updated {lastUpdated}
                  </span>
                ) : null}
              </div>
              <p className="mt-2 text-muted-foreground">{summary}</p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                {LEGAL_LOCALES.map((loc) => (
                  <Link
                    key={loc}
                    href={`/legal/${type}/${loc}`}
                    className="rounded-full border px-2 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                  >
                    {loc}
                  </Link>
                ))}
              </div>
            </li>
          );
        })}
      </ul>

      <footer className="mt-10 text-xs text-muted-foreground">
        Privacy contact: <a href="mailto:privacy@quarrel.ai" className="underline">privacy@quarrel.ai</a>{" · "}
        DPO: <a href="mailto:dpo@quarrel.ai" className="underline">dpo@quarrel.ai</a>
      </footer>
    </main>
  );
}
