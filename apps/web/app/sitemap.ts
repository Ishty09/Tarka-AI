import type { MetadataRoute } from "next";
import { ROAST_TARGETS } from "@quarrel/shared/constants";
import { LEGAL_DOC_TYPES, LEGAL_LOCALES } from "@/lib/legal";

// Programmatic sitemap (CLAUDE.md §19, §27 step 69).
//
// Next.js generates /sitemap.xml from this default export at build time.
// Every public route the marketing site reaches lives here so search
// engines have an authoritative list.
//
// Authenticated routes ((app)/* and (auth)/*) are NOT included — search
// engines shouldn't crawl them, and the page-level Supabase guards
// redirect away anyway.

const BASE_URL = (process.env.NEXT_PUBLIC_APP_URL ?? "https://quarrel.ai").replace(
  /\/+$/,
  "",
);

function url(path: string): string {
  return `${BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();

  const staticEntries: MetadataRoute.Sitemap = [
    { url: url("/"), lastModified: now, changeFrequency: "weekly", priority: 1.0 },
    { url: url("/pricing"), lastModified: now, changeFrequency: "weekly", priority: 0.9 },
    { url: url("/login"), lastModified: now, changeFrequency: "monthly", priority: 0.5 },
    { url: url("/signup"), lastModified: now, changeFrequency: "monthly", priority: 0.6 },
    { url: url("/legal"), lastModified: now, changeFrequency: "monthly", priority: 0.4 },
  ];

  // Roast My X — 20 programmatic SEO landing pages (§9.2.2). These are
  // the search-engine entry points for the long-tail "roast my <target>"
  // intent.
  const roastEntries: MetadataRoute.Sitemap = ROAST_TARGETS.map((target) => ({
    url: url(`/roast/${target}`),
    lastModified: now,
    changeFrequency: "weekly" as const,
    priority: 0.8,
  }));

  // Legal docs — 6 doc types × 6 publishing locales = 36 URLs (§16). We
  // emit one entry per (type, locale) so non-English variants are
  // discoverable even when the content falls back to English.
  const legalEntries: MetadataRoute.Sitemap = LEGAL_DOC_TYPES.flatMap((type) =>
    LEGAL_LOCALES.map((locale) => ({
      url: url(`/legal/${type}/${locale}`),
      lastModified: now,
      changeFrequency: "yearly" as const,
      priority: 0.3,
    })),
  );

  return [...staticEntries, ...roastEntries, ...legalEntries];
}
