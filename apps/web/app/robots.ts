import type { MetadataRoute } from "next";

// robots.txt (CLAUDE.md §19, §27 step 69). Next.js generates /robots.txt
// from this default export.
//
// We let crawlers hit the marketing surface (/, /pricing, /roast/*,
// /legal/*) and explicitly disallow:
//   - /api/* (server endpoints; nothing useful to index, some are auth-
//     bound and emit JSON that confuses snippet extractors).
//   - /auth/* (callback + signout endpoints).
//   - /chat, /personas, /contradictions, /couples, /groups, /mirror,
//     /eulogy, /feed, /tools/*, /wagers, /settings, /admin — these all
//     live under the (app) route group, which requires auth. Crawlers
//     would just bounce to /login; disallowing keeps the crawl budget
//     focused on indexable pages.
//   - /monitoring (Sentry tunnel route from step 60).

const BASE_URL = (process.env.NEXT_PUBLIC_APP_URL ?? "https://quarrel.ai").replace(
  /\/+$/,
  "",
);

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/pricing", "/roast/", "/legal/", "/login", "/signup"],
        disallow: [
          "/api/",
          "/auth/",
          "/monitoring",
          "/chat",
          "/personas",
          "/contradictions",
          "/couples",
          "/groups",
          "/mirror",
          "/eulogy",
          "/feed",
          "/tools/",
          "/wagers",
          "/settings",
          "/admin",
        ],
      },
    ],
    sitemap: `${BASE_URL}/sitemap.xml`,
    host: BASE_URL,
  };
}
