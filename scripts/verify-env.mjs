#!/usr/bin/env node
/**
 * Production env verification (CLAUDE.md §27 step 70).
 *
 * Reads .env.example as the canonical "what we need" list and reports
 * which entries are unset in the current process env. Two output modes:
 *
 *   - default: human-readable, exits non-zero if any REQUIRED var is
 *     missing.
 *   - --json: machine-readable for CI integration.
 *
 * Required = the var has no default in .env.example (the line is
 * `KEY=`). Optional = the var has a default value (`KEY=...`).
 *
 * Usage:
 *   node scripts/verify-env.mjs                 # check process.env
 *   node scripts/verify-env.mjs --env path.env  # check a specific file
 *   node scripts/verify-env.mjs --json
 */

import { readFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, "..");

function parseEnvFile(content) {
  const entries = [];
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim().replace(/^"|"$/g, "");
    entries.push({ key, hasDefault: value.length > 0 });
  }
  return entries;
}

function loadEnvFile(path) {
  if (!existsSync(path)) return {};
  const env = {};
  for (const rawLine of readFileSync(path, "utf-8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim().replace(/^"|"$/g, "");
    env[key] = value;
  }
  return env;
}

const args = process.argv.slice(2);
const jsonMode = args.includes("--json");
const envFlagIndex = args.indexOf("--env");
const envFile = envFlagIndex >= 0 ? args[envFlagIndex + 1] : null;

const examplePath = resolve(REPO_ROOT, ".env.example");
if (!existsSync(examplePath)) {
  console.error("verify-env: .env.example not found at", examplePath);
  process.exit(2);
}

const expected = parseEnvFile(readFileSync(examplePath, "utf-8"));
const sourceEnv = envFile ? loadEnvFile(resolve(envFile)) : process.env;

const missingRequired = [];
const missingOptional = [];
const present = [];

for (const { key, hasDefault } of expected) {
  const value = sourceEnv[key];
  if (value && value.length > 0) {
    present.push(key);
  } else if (hasDefault) {
    missingOptional.push(key);
  } else {
    missingRequired.push(key);
  }
}

if (jsonMode) {
  console.log(
    JSON.stringify(
      {
        present,
        missing_required: missingRequired,
        missing_optional: missingOptional,
        ok: missingRequired.length === 0,
      },
      null,
      2,
    ),
  );
} else {
  console.log(`Checked ${expected.length} expected env vars`);
  console.log(`  present:           ${present.length}`);
  console.log(`  missing required:  ${missingRequired.length}`);
  console.log(`  missing optional:  ${missingOptional.length}`);
  if (missingRequired.length) {
    console.log("\nREQUIRED but unset:");
    for (const k of missingRequired) console.log("  ✗", k);
  }
  if (missingOptional.length) {
    console.log("\nOptional, unset (defaults kick in):");
    for (const k of missingOptional) console.log("  ·", k);
  }
  if (missingRequired.length === 0) {
    console.log("\nAll required env vars are set.");
  }
}

process.exit(missingRequired.length === 0 ? 0 : 1);
