#!/usr/bin/env node
/**
 * Print the cohort_retention view as a human-readable table
 * (CLAUDE.md §27 step 73).
 *
 * Reads the view via Supabase REST using the service-role key. No
 * admin login required — this is a terminal report.
 *
 * Usage:
 *   pnpm report:retention                       # all cohorts
 *   pnpm report:retention -- --cohort wave-1    # one cohort
 *   pnpm report:retention -- --json             # machine-readable
 *
 * Exit codes:
 *   0 — at least one cohort hits the §28 gate (or no cohorts present)
 *   1 — every cohort with signups is below the gate
 *   2 — invocation / network error
 */

const args = process.argv.slice(2);

function flag(name, fallback) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : fallback;
}

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SERVICE_ROLE = process.env.SUPABASE_SERVICE_ROLE_KEY;
const cohort = flag("--cohort", null);
const jsonMode = args.includes("--json");
const LAUNCH_GATE = 0.3;

if (!SUPABASE_URL || !SERVICE_ROLE) {
  console.error(
    "report-retention: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set",
  );
  process.exit(2);
}

const url = new URL(`${SUPABASE_URL.replace(/\/+$/, "")}/rest/v1/cohort_retention`);
url.searchParams.set(
  "select",
  "cohort_tag,invited,sent,signed_up,retained_d2_d7,activation_rate,retention_rate",
);
url.searchParams.set("order", "cohort_tag.asc");
if (cohort) url.searchParams.set("cohort_tag", `eq.${cohort}`);

const res = await fetch(url, {
  headers: {
    apikey: SERVICE_ROLE,
    authorization: `Bearer ${SERVICE_ROLE}`,
  },
});
if (!res.ok) {
  console.error(`report-retention: ${res.status} ${res.statusText}`);
  console.error(await res.text());
  process.exit(2);
}

const rows = await res.json();

if (jsonMode) {
  console.log(JSON.stringify({ launch_gate: LAUNCH_GATE, rows }, null, 2));
  const anyMet = rows.some((r) => r.signed_up > 0 && r.retention_rate >= LAUNCH_GATE);
  const anyWithSignups = rows.some((r) => r.signed_up > 0);
  process.exit(!anyWithSignups || anyMet ? 0 : 1);
}

if (rows.length === 0) {
  console.log("No cohorts found.");
  process.exit(0);
}

const pct = (n) => `${(n * 100).toFixed(1)}%`;
const header = ["Cohort", "Invited", "Sent", "Signed up", "Activation", "D2-D7", "Retention"];
const widths = header.map((h) => h.length);

const formatted = rows.map((r) => {
  const cells = [
    r.cohort_tag,
    String(r.invited),
    String(r.sent),
    String(r.signed_up),
    pct(r.activation_rate),
    String(r.retained_d2_d7),
    pct(r.retention_rate),
  ];
  cells.forEach((c, i) => {
    if (c.length > widths[i]) widths[i] = c.length;
  });
  return { cells, retentionRate: r.retention_rate, signedUp: r.signed_up };
});

const pad = (s, w) => s + " ".repeat(Math.max(0, w - s.length));
console.log(header.map((h, i) => pad(h, widths[i])).join("  "));
console.log(widths.map((w) => "-".repeat(w)).join("  "));

let metGate = false;
let withSignups = false;
for (const row of formatted) {
  const line = row.cells.map((c, i) => pad(c, widths[i])).join("  ");
  let suffix = "";
  if (row.signedUp > 0) {
    withSignups = true;
    if (row.retentionRate >= LAUNCH_GATE) {
      suffix = "  ✓ gate met";
      metGate = true;
    } else {
      suffix = "  ✗ below gate";
    }
  }
  console.log(line + suffix);
}

console.log("");
console.log(`§28 launch gate: ${pct(LAUNCH_GATE)} retention D2-D7.`);
if (!withSignups) {
  console.log("No cohorts have signups yet — gate not evaluated.");
} else if (metGate) {
  console.log("At least one cohort meets the gate.");
} else {
  console.log("No cohort with signups currently meets the gate.");
}

process.exit(!withSignups || metGate ? 0 : 1);
