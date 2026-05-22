#!/usr/bin/env node
/**
 * Production smoke harness (CLAUDE.md §27 step 71).
 *
 * Hits the canonical public surface and reports per-check pass/fail.
 * Designed to run after every deploy and before any launch milestone.
 * No auth required for the default set; pass --cron-secret <secret> to
 * also probe the workers cron endpoints.
 *
 * Usage:
 *   node scripts/smoke.mjs                          # defaults to https://quarrel.ai
 *   node scripts/smoke.mjs --base https://staging.quarrel.ai
 *   node scripts/smoke.mjs --workers https://api.quarrel.ai
 *   node scripts/smoke.mjs --cron-secret $CRON_SECRET
 *   node scripts/smoke.mjs --json
 *
 * Exit codes:
 *   0 — all checks passed
 *   1 — at least one check failed
 *   2 — invocation error (bad flag, etc.)
 */

const args = process.argv.slice(2);

function flag(name, fallback) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : fallback;
}

const BASE = (flag("--base", process.env.SMOKE_BASE_URL ?? "https://quarrel.ai")).replace(
  /\/+$/,
  "",
);
const WORKERS = (flag(
  "--workers",
  process.env.SMOKE_WORKERS_URL ?? "https://api.quarrel.ai",
)).replace(/\/+$/, "");
const CRON_SECRET = flag("--cron-secret", process.env.CRON_SECRET ?? null);
const JSON_MODE = args.includes("--json");
const TIMEOUT_MS = 10_000;

/** @type {{ name: string, expect: number, contains?: string | RegExp, fn: () => Promise<Response> }[]} */
const CHECKS = [
  {
    name: "web /api/health",
    expect: 200,
    contains: "ok",
    fn: () => fetchWithTimeout(`${BASE}/api/health`),
  },
  {
    name: "apex /",
    expect: 200,
    contains: /Quarrel/i,
    fn: () => fetchWithTimeout(`${BASE}/`),
  },
  {
    name: "pricing",
    expect: 200,
    contains: /\$9\.99/,
    fn: () => fetchWithTimeout(`${BASE}/pricing`),
  },
  {
    name: "legal hub",
    expect: 200,
    contains: /Privacy/i,
    fn: () => fetchWithTimeout(`${BASE}/legal`),
  },
  {
    name: "legal — privacy en",
    expect: 200,
    contains: /Privacy Policy/i,
    fn: () => fetchWithTimeout(`${BASE}/legal/privacy/en`),
  },
  {
    name: "roast — linkedin",
    expect: 200,
    contains: /LinkedIn/i,
    fn: () => fetchWithTimeout(`${BASE}/roast/linkedin`),
  },
  {
    name: "sitemap.xml",
    expect: 200,
    contains: /<urlset/,
    fn: () => fetchWithTimeout(`${BASE}/sitemap.xml`),
  },
  {
    name: "robots.txt",
    expect: 200,
    contains: /Sitemap:/,
    fn: () => fetchWithTimeout(`${BASE}/robots.txt`),
  },
  {
    name: "login",
    expect: 200,
    contains: /(sign in|continue|email)/i,
    fn: () => fetchWithTimeout(`${BASE}/login`),
  },
  {
    name: "signup",
    expect: 200,
    contains: /(sign up|continue|email)/i,
    fn: () => fetchWithTimeout(`${BASE}/signup`),
  },
  // Protected app routes should bounce to /login, not 5xx.
  {
    name: "chat (unauth → redirect)",
    expect: 200,
    contains: /(sign in|email)/i,
    fn: () =>
      fetchWithTimeout(`${BASE}/chat`, {
        redirect: "follow",
      }),
  },
  // Workers
  {
    name: "workers /health",
    expect: 200,
    contains: "ok",
    fn: () => fetchWithTimeout(`${WORKERS}/health`),
  },
];

if (CRON_SECRET) {
  // Cron endpoints respond 200 with a tally — POST with the bearer token
  // and an empty body.
  for (const name of [
    "contradiction-batch",
    "mirror-mode",
    "eulogy",
    "daily-roast",
    "wager-evaluator",
    "drill-sergeant",
    "data-export",
    "account-deletion",
  ]) {
    CHECKS.push({
      name: `cron /${name} (auth)`,
      expect: 200,
      fn: () =>
        fetchWithTimeout(`${WORKERS}/cron/${name}`, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            authorization: `Bearer ${CRON_SECRET}`,
          },
          body: JSON.stringify({}),
        }),
    });
  }

  // Negative check: same endpoints reject without the secret.
  CHECKS.push({
    name: "cron /daily-roast (no auth → 401)",
    expect: 401,
    fn: () =>
      fetchWithTimeout(`${WORKERS}/cron/daily-roast`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
  });
}

async function fetchWithTimeout(url, init = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function runCheck(check) {
  const started = Date.now();
  try {
    const res = await check.fn();
    const took = Date.now() - started;
    if (res.status !== check.expect) {
      return {
        ok: false,
        name: check.name,
        ms: took,
        reason: `expected ${check.expect}, got ${res.status}`,
      };
    }
    if (check.contains !== undefined) {
      const body = await res.text();
      const matches =
        check.contains instanceof RegExp
          ? check.contains.test(body)
          : body.includes(check.contains);
      if (!matches) {
        return {
          ok: false,
          name: check.name,
          ms: took,
          reason: `body did not contain ${check.contains}`,
        };
      }
    }
    return { ok: true, name: check.name, ms: took };
  } catch (err) {
    return {
      ok: false,
      name: check.name,
      ms: Date.now() - started,
      reason: err instanceof Error ? err.message : String(err),
    };
  }
}

const results = [];
for (const check of CHECKS) {
  const result = await runCheck(check);
  results.push(result);
  if (!JSON_MODE) {
    const mark = result.ok ? "✓" : "✗";
    const tail = result.reason ? ` — ${result.reason}` : "";
    console.log(`${mark} ${result.name} (${result.ms}ms)${tail}`);
  }
}

const failed = results.filter((r) => !r.ok);

if (JSON_MODE) {
  console.log(
    JSON.stringify(
      {
        base: BASE,
        workers: WORKERS,
        checked: results.length,
        passed: results.length - failed.length,
        failed: failed.length,
        results,
      },
      null,
      2,
    ),
  );
} else {
  console.log("");
  console.log(`${results.length - failed.length}/${results.length} checks passed`);
  if (failed.length) {
    console.log(`${failed.length} failed.`);
  }
}

process.exit(failed.length === 0 ? 0 : 1);
