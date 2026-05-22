#!/usr/bin/env node
/**
 * Enqueue beta-cohort invitees into the `beta_invites` table
 * (CLAUDE.md §27 step 72).
 *
 * Reads an invitees file (JSON or one-email-per-line) and INSERTs rows
 * via Supabase's REST API using the service-role key. The workers
 * cron at /cron/beta-invites then drains the queue, generating magic
 * links and sending the beta_invite email per row.
 *
 * Usage:
 *   node scripts/invite-beta.mjs --file invitees.json --cohort wave-1
 *   node scripts/invite-beta.mjs --file emails.txt --cohort founder-friends --dry-run
 *
 * invitees.json shape:
 *   [{ "email": "alice@example.com", "notes": "via Hacker News" }, ...]
 *
 * emails.txt shape (fallback when --file ends in .txt):
 *   one email per line, # for comments
 *
 * Environment:
 *   NEXT_PUBLIC_SUPABASE_URL    — e.g. https://<ref>.supabase.co
 *   SUPABASE_SERVICE_ROLE_KEY   — required, write access to beta_invites
 *   INVITED_BY                  — optional: profile UUID to credit as inviter
 *
 * --dry-run validates + prints what would be inserted, without writing.
 */

import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

function flag(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

const filePath = flag("--file", "data/invitees.json");
const cohort = flag("--cohort", null);
const dryRun = process.argv.includes("--dry-run");

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SERVICE_ROLE = process.env.SUPABASE_SERVICE_ROLE_KEY;
const INVITED_BY = process.env.INVITED_BY ?? null;

if (!cohort) {
  console.error(
    "invite-beta: --cohort <tag> is required (e.g. wave-1, founder-friends)",
  );
  process.exit(2);
}
if (!SUPABASE_URL || !SERVICE_ROLE) {
  console.error(
    "invite-beta: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set",
  );
  process.exit(2);
}

const absPath = resolve(filePath);
if (!existsSync(absPath)) {
  console.error(`invite-beta: file not found: ${absPath}`);
  process.exit(2);
}

const raw = readFileSync(absPath, "utf-8");
let parsed = [];
if (filePath.endsWith(".json")) {
  parsed = JSON.parse(raw);
  if (!Array.isArray(parsed)) {
    console.error("invite-beta: JSON file must be an array of objects");
    process.exit(2);
  }
} else {
  parsed = raw
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"))
    .map((email) => ({ email }));
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const rows = [];
const skipped = [];
for (const entry of parsed) {
  const email = String(entry.email ?? "").trim().toLowerCase();
  if (!EMAIL_RE.test(email)) {
    skipped.push({ email, reason: "invalid_format" });
    continue;
  }
  rows.push({
    email,
    cohort_tag: cohort,
    notes: entry.notes ?? null,
    invited_by: INVITED_BY,
  });
}

console.log(`Loaded ${rows.length} valid invitees (${skipped.length} skipped) for cohort "${cohort}"`);
if (skipped.length) {
  for (const s of skipped) console.log(`  · ${s.email || "<empty>"} — ${s.reason}`);
}

if (dryRun) {
  console.log("\n--dry-run — no inserts performed. Sample:");
  console.log(rows.slice(0, 3).map((r) => `  + ${r.email}`).join("\n"));
  process.exit(0);
}

if (rows.length === 0) {
  console.log("nothing to insert");
  process.exit(0);
}

const endpoint = `${SUPABASE_URL.replace(/\/+$/, "")}/rest/v1/beta_invites`;
const res = await fetch(endpoint, {
  method: "POST",
  headers: {
    "content-type": "application/json",
    apikey: SERVICE_ROLE,
    authorization: `Bearer ${SERVICE_ROLE}`,
    prefer: "return=representation,resolution=ignore-duplicates",
  },
  body: JSON.stringify(rows),
});

if (!res.ok) {
  const body = await res.text();
  console.error(`invite-beta: insert failed (${res.status})`);
  console.error(body);
  process.exit(1);
}

const inserted = await res.json();
console.log(`\nInserted ${inserted.length} new rows.`);
console.log(`${rows.length - inserted.length} duplicates skipped (already in cohort "${cohort}").`);
console.log(`\nNext step: trigger the cron once to drain immediately, or wait for the scheduler.`);
console.log(`  curl -X POST -H "Authorization: Bearer $CRON_SECRET" https://api.quarrel.ai/cron/beta-invites`);
