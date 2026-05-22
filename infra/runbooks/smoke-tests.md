# Smoke tests

CLAUDE.md §27 step 71. Run after every production deploy and before any
launch milestone (§28). The script exercises the canonical public
surface in under a minute.

## Invocation

```bash
# Default — hits https://quarrel.ai + https://api.quarrel.ai.
pnpm smoke

# Staging or preview.
pnpm smoke -- --base https://staging.quarrel.ai \
              --workers https://api-staging.quarrel.ai

# Include cron-protected workers endpoints.
CRON_SECRET=… pnpm smoke -- --cron-secret "$CRON_SECRET"

# CI-friendly JSON output.
pnpm smoke -- --json
```

Exit code is 0 when every check passes, 1 if any fails, 2 on
invocation errors. CI can gate on the exit code.

## What's covered

Each row is one check. The non-auth set runs by default; the cron set
runs only with `--cron-secret`.

| Check                              | Expects | Asserts                                 |
| ---------------------------------- | ------- | --------------------------------------- |
| `GET /api/health`                  | 200     | body contains `"ok"`                     |
| `GET /`                            | 200     | body contains "Quarrel"                 |
| `GET /pricing`                     | 200     | body contains `$9.99`                    |
| `GET /legal`                       | 200     | body contains "Privacy"                  |
| `GET /legal/privacy/en`            | 200     | body contains "Privacy Policy"           |
| `GET /roast/linkedin`              | 200     | body contains "LinkedIn"                 |
| `GET /sitemap.xml`                 | 200     | body contains `<urlset`                  |
| `GET /robots.txt`                  | 200     | body contains `Sitemap:`                 |
| `GET /login`                       | 200     | body contains a sign-in cue              |
| `GET /signup`                      | 200     | body contains a sign-up cue              |
| `GET /chat` (unauth)               | 200     | redirects to login; final body has sign-in cue |
| `GET <workers>/health`             | 200     | body contains `"ok"`                     |
| `POST /cron/<name>` (with secret)  | 200     | each of contradiction-batch, mirror-mode, eulogy, daily-roast, wager-evaluator, drill-sergeant, data-export, account-deletion |
| `POST /cron/daily-roast` (no auth) | 401     | confirms the bearer guard is on          |

## When to run

- **After every production deploy.** Before posting "shipped" in the
  ops channel.
- **Before a launch milestone** per §28. Run with `--cron-secret` so
  the full set is exercised, not just public.
- **Manual sanity** after an outage where you don't fully trust that
  everything came back. Easier than clicking around.

## Adding a check

Each entry in `scripts/smoke.mjs` is `{ name, expect, contains?, fn }`.
Keep new checks idempotent and cheap; this runs against production —
no mutations, no signed-in flows. If you need a deeper check (signed-in
chat round-trip, sandbox Polar checkout, push delivery), put it in a
separate `scripts/smoke-deep.mjs` so the default smoke stays fast.

## Out of scope

The smoke harness is intentionally *not* a replacement for:

- `apps/workers/tests/` — these run in CI on every PR and cover the
  workers' business logic.
- `apps/web` Playwright tests — when those land, they cover signed-in
  flows that smoke can't reach without bringing up a session.
- Synthetic monitoring — UptimeRobot polls 24/7 (§63). Smoke is a
  one-shot.

## Deeper post-launch tests

To validate signed-in surfaces after launch, run the manual checklist:

1. Sign up with a fresh email; verify the magic-link email lands within
   30 seconds.
2. Complete onboarding through to the first chat.
3. Send one chat message in Argue mode with the `devils_advocate`
   persona. Confirm streaming starts within 2 seconds and the assistant
   message persists on reload.
4. Open `/contradictions`. Trigger a nightly batch run via
   `/cron/contradiction-batch` (with the secret). Confirm a new
   contradiction surfaces on a refresh.
5. Start a Polar checkout (sandbox) for the Pro tier. Cancel before
   payment. Confirm no subscription row is created.
6. Request a data export from `/settings/data`. Run
   `/cron/data-export`. Confirm the email lands with a working signed
   URL within 5 minutes.
7. Request account deletion from `/settings/data`. Confirm the grace
   email lands. (Don't wait 30 days — cancel deletion from the UI to
   keep the test account.)

Mark the test account so the §58 sweeper doesn't reap it before you
re-verify next quarter.
