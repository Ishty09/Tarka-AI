#!/usr/bin/env node
/**
 * §28 launch gate runner (CLAUDE.md §27 step 75).
 *
 * Runs every automated check in sequence and aggregates pass/fail.
 * Each step here mirrors a row in the §28 checklist in
 * infra/runbooks/public-launch.md. The non-automated rows (legal
 * review, mental load, crisis flow native-speaker tests) are NOT
 * covered — those require a human and are tracked in the runbook.
 *
 * Usage:
 *   pnpm launch-check                              # run everything
 *   pnpm launch-check -- --skip-smoke              # skip a step
 *   pnpm launch-check -- --json                    # CI output
 *
 * Steps and their commands:
 *   verify-env   — pnpm verify:env
 *   typecheck    — pnpm typecheck
 *   test         — pnpm test
 *   smoke        — pnpm smoke (passes CRON_SECRET env through)
 *   retention    — pnpm report:retention
 *
 * Exit code: 0 if every step passes (or was skipped); 1 if any failed;
 * 2 on invocation error.
 *
 * The script intentionally streams each step's output so a long-running
 * pytest doesn't look hung. Step boundaries are clearly marked with
 * "==> step" headers.
 */

import { spawn } from "node:child_process";

const args = process.argv.slice(2);
const jsonMode = args.includes("--json");

const STEPS = [
  {
    id: "verify-env",
    description: "All required env vars set",
    cmd: ["pnpm", "verify:env"],
    skip: args.includes("--skip-verify-env"),
  },
  {
    id: "typecheck",
    description: "TS + mypy clean across the monorepo",
    cmd: ["pnpm", "typecheck"],
    skip: args.includes("--skip-typecheck"),
  },
  {
    id: "test",
    description: "Workers tests + any web tests",
    cmd: ["pnpm", "test"],
    skip: args.includes("--skip-test"),
  },
  {
    id: "smoke",
    description: "Production smoke harness (apex + workers + cron with secret)",
    cmd: process.env.CRON_SECRET
      ? ["pnpm", "smoke", "--", "--cron-secret", process.env.CRON_SECRET]
      : ["pnpm", "smoke"],
    skip: args.includes("--skip-smoke"),
  },
  {
    id: "retention",
    description: "Beta cohort week-1 retention ≥ §28 gate",
    cmd: ["pnpm", "report:retention"],
    skip: args.includes("--skip-retention"),
  },
];

async function run(step) {
  return new Promise((resolve) => {
    const started = Date.now();
    if (!jsonMode) {
      console.log("");
      console.log(`==> ${step.id} — ${step.description}`);
      console.log(`    ${step.cmd.join(" ")}`);
    }
    const child = spawn(step.cmd[0], step.cmd.slice(1), {
      stdio: jsonMode ? "pipe" : "inherit",
      shell: process.platform === "win32",
      env: process.env,
    });
    let captured = "";
    if (jsonMode) {
      child.stdout?.on("data", (d) => {
        captured += d.toString();
      });
      child.stderr?.on("data", (d) => {
        captured += d.toString();
      });
    }
    child.on("close", (code) => {
      resolve({
        id: step.id,
        description: step.description,
        ok: code === 0,
        exit_code: code,
        ms: Date.now() - started,
        ...(jsonMode ? { output: captured.slice(-4000) } : {}),
      });
    });
    child.on("error", (err) => {
      resolve({
        id: step.id,
        description: step.description,
        ok: false,
        exit_code: -1,
        ms: Date.now() - started,
        error: err.message,
      });
    });
  });
}

const results = [];
for (const step of STEPS) {
  if (step.skip) {
    results.push({
      id: step.id,
      description: step.description,
      ok: true,
      skipped: true,
      exit_code: 0,
      ms: 0,
    });
    if (!jsonMode) console.log(`==> ${step.id} — SKIPPED`);
    continue;
  }
  const result = await run(step);
  results.push(result);
}

const failed = results.filter((r) => !r.ok);

if (jsonMode) {
  console.log(
    JSON.stringify(
      {
        passed: results.length - failed.length,
        failed: failed.length,
        skipped: results.filter((r) => r.skipped).length,
        results,
      },
      null,
      2,
    ),
  );
} else {
  console.log("");
  console.log("=".repeat(60));
  console.log(`Launch check summary`);
  console.log("=".repeat(60));
  for (const r of results) {
    const mark = r.skipped ? "·" : r.ok ? "✓" : "✗";
    const note = r.skipped ? " (skipped)" : ` (${(r.ms / 1000).toFixed(1)}s)`;
    console.log(`  ${mark} ${r.id}${note} — ${r.description}`);
  }
  console.log("");
  if (failed.length === 0) {
    console.log("All automated gates passed.");
    console.log("");
    console.log("Now finish the manual rows in infra/runbooks/public-launch.md:");
    console.log("  - legal review note recorded in 1Password");
    console.log("  - crisis flow tested with native speakers (≥ 5 locales)");
    console.log("  - $1 Polar test purchase + downgrade");
    console.log("  - on-call SMS test");
    console.log("  - founder mental-load check");
  } else {
    console.log(`${failed.length} gate(s) failed. Launch is BLOCKED.`);
  }
}

process.exit(failed.length === 0 ? 0 : 1);
