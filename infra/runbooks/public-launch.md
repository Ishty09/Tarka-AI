# Public launch

CLAUDE.md §27 step 75 — the last step. §28 is the gate it must pass
before flipping the announcement switch.

This runbook is the single page the founder reads end-to-end on launch
day. Other runbooks (`incident-response`, `product-hunt-launch`,
`smoke-tests`, `beta-cohort`) are the depth; this one is the path.

## §28 go/no-go checklist

Each item maps to a concrete command or UI surface. Don't tick a box
without verifying the underlying signal — the gate exists because
"feels ready" is not ready.

### Automated gates (run `pnpm launch-check` to drive all of these)

- [ ] **All §27 phases complete.** Last commit is in `main`. No
      uncommitted changes (`git status`).
- [ ] **All e2e + worker tests pass.** `pnpm test` → 0 failures across
      the suite.
- [ ] **All required env vars set in production.** `pnpm verify:env`
      against a production env snapshot → exit 0.
- [ ] **Type checks pass.** `pnpm typecheck` → exit 0 on every
      workspace.
- [ ] **Smoke harness passes.** `pnpm smoke -- --base https://quarrel.ai
      --workers https://api.quarrel.ai --cron-secret $CRON_SECRET` →
      every check green.
- [ ] **Retention gate hit.** `pnpm report:retention -- --cohort wave-1`
      (or the production cohort tag) → exit 0 and retention rate ≥ 30%.

### §22 security checklist

- [ ] No service-role key in `apps/web` client components (grep).
- [ ] No `dangerouslySetInnerHTML` in marketing or chat surfaces.
- [ ] Webhook handlers verify HMAC (Polar — confirmed in
      `polar_webhooks.py`).
- [ ] CSP header on `apps/web` responses (verify in browser devtools).
- [ ] Rate limits live at LiteLLM virtual keys for free/pro/max + at
      slowapi in workers.
- [ ] Migrations are append-only (last 10 reviewed for drops/renames).
- [ ] Secrets rotated per `SECRETS.md` — at minimum
      `LITELLM_MASTER_KEY`, `WORKERS_INTERNAL_SECRET`, `CRON_SECRET`,
      `POLAR_WEBHOOK_SECRET`.

### Compliance + legal

- [ ] Privacy policy + ToS in 6 launch locales — visit
      `/legal/privacy/{en,bn,hi,es,pt,ar}` and `/legal/terms/{...}`.
      Locales without localised content show the fallback banner;
      that's fine.
- [ ] Privacy + ToS lawyer-reviewed for US + EU (note in 1Password the
      lawyer's name + review date).
- [ ] EU AI Act Article 50 modal verified in each of the 6 launch
      locales — sign in fresh in a private window, switch locale,
      confirm modal renders.
- [ ] Cookie banner appears once and dismisses correctly.
- [ ] Crisis flow tested with native speakers in ≥ 5 locales.

### Payments

- [ ] Polar production keys live (`ENABLE_POLAR=true`, product IDs
      point to the Polar production catalog, not sandbox).
- [ ] $1 test purchase succeeds, the user moves from `free` → `pro` on
      the test profile, then a downgrade returns to `free` at period
      end.
- [ ] Refund within the 14-day window also succeeds (refund the $1).

### Observability

- [ ] `status.quarrel.ai` is live and rendering all 5 components.
- [ ] UptimeRobot monitors all green for ≥ 24h.
- [ ] A test Sentry event from web + workers appears in the Sentry
      dashboard.
- [ ] Umami `signup_started` event count increased during the beta
      cohort window (sanity check that analytics actually fires).
- [ ] Langfuse `chat.stream` traces visible for beta-cohort messages
      with the §21 metadata (mode, persona, tier, locale).

### Operations

- [ ] Backup cron tested with a successful Spaces upload in the last
      24h (check `s3://quarrel-backups/litellm/daily/`).
- [ ] At least one restore drill from the monthly rotation completed
      successfully (see `backups.md`).
- [ ] On-call SMS reaches the founder's actual phone — fire a test
      UptimeRobot alert by toggling a monitor off and back.
- [ ] Status page admin password verified accessible from 1Password.

### Beta cohort

- [ ] 100 hand-picked invitees sent (`select count(*) from beta_invites
      where sent_at is not null`).
- [ ] ≥ 30% signed-up.
- [ ] Week-1 retention ≥ 30% per `/admin/retention`.

### Product Hunt

- [ ] Launch scheduled for ≤ 14 days out, ideally Tue/Wed/Thu.
- [ ] Assets staged in `infra/launch/product-hunt/`.
- [ ] Maker's first comment drafted.
- [ ] Hunter briefed (or self-hunt decision recorded).

### Founder

- [ ] **Mental load is sustainable.** This is the gate that doesn't
      have a script. If the founder can't honestly answer "I can run
      this for 90 days at this pace" — delay.

If every box above is ticked, proceed. If any is not, the launch
delays. There is no partial launch.

## Launch-day procedure

### T-24h

- Final `pnpm launch-check` against production. Fix anything red.
- Apply the deploy freeze per `deploy.md`. From here, no commits to
  `main` unless they're a P1 hotfix landing in this runbook's "Bail-out
  procedures" section.
- Confirm beta cohort retention is still ≥ 30% (the number can drop
  between scheduling and launch if late drop-offs aren't backfilled —
  re-run `pnpm report:retention`).
- Pre-write the §28 retro post template (see end of this file). The
  founder fills it in T+24h post-launch.

### T-1h

- Run `pnpm smoke` once more.
- Open the dashboards in browser tabs and pin them: Vercel, Coolify,
  Sentry web, Sentry workers, Langfuse, Umami, `/admin/retention`,
  `/admin/incidents`, `status.quarrel.ai`, the Product Hunt scheduled
  post page.
- Brew coffee. (The runbook calls this out because the founder forgets
  every time.)

### T-0 (00:01 PST = 08:01 UTC for the PH path)

1. Confirm the PH post appears at `producthunt.com/featured`.
2. Set `NEXT_PUBLIC_PRODUCT_HUNT_URL` in Vercel to the launch URL.
   Redeploy (one-click "Redeploy" in the Vercel dashboard; the env
   change requires a rebuild — apex is static).
3. Post the maker's first comment within 5 minutes of going live.
4. Post the launch tweet from `@quarrel_ai` (link in first line per
   `product-hunt-launch.md`).

### T+0 through T+24h

The status page is the user-facing source of truth. Any user-visible
breakage gets an Investigating post within 10 minutes per
`incident-response.md`. Severity tiers apply unchanged.

- Comment SLA: 30 minutes on PH.
- Sentry watch: refresh the workers project every 15 minutes.
- LiteLLM cost watch: the Anthropic + OpenAI dashboards every 2 hours.
  If the rate of spend doubles the projection, throttle the free tier
  in the LiteLLM admin UI (cut the free-tier RPM in half) until the
  spike passes.
- Signups watch: `/admin` dashboard — pending personas + feed posts
  pile up fast. Triage every hour to keep the queues short.

### T+24h

- Pull the metrics in `product-hunt-launch.md`'s post-launch section.
- Lift the `NEXT_PUBLIC_PRODUCT_HUNT_URL` env var at T+48h (or earlier
  if the PH thread is no longer fresh).
- Lift the deploy freeze.

## Bail-out procedures

If during launch day something breaks badly:

### Soft bail (degrade and continue)

Triggered by: chat slowness, intermittent 5xx, one tool broken.

1. Roll back the most recent deploy (`vercel rollback` and Coolify
   "Redeploy previous").
2. Flip the affected `ENABLE_*` flag off (e.g. `ENABLE_WAGERS=false`
   if Polar is acting up).
3. Post an Investigating + Identified pair on the status page.
4. Continue launch — degraded launches still beat delayed launches as
   long as users can sign up and chat.

### Hard bail (pause launch)

Triggered by: chat path totally broken, data integrity issue, a
safety incident the system mishandled.

1. Take the deploy freeze further — disable Vercel auto-deploys
   completely (per `deploy.md`).
2. Post a Critical incident on the status page with explicit "do not
   sign up" language.
3. Update the maker's PH comment to acknowledge the issue and link to
   the status page. Don't delete the PH post.
4. Email beta cohort with a one-line apology + ETA.
5. Fix forward — the entire incident-response runbook applies.
6. When resolved, post a public post-mortem within 48 hours per the
   template in `incident-response.md`.

A hard bail is bad but recoverable. A hard bail followed by silence
is brand-damaging.

## Post-launch retro template

Append to `infra/runbooks/post-mortems/YYYY-MM-DD-public-launch.md`
within 7 days:

```
# Public launch — YYYY-MM-DD

## Numbers
- Signups (T+24h):
- Signups (T+7d):
- Tier conversions (T+7d):
- D2-D7 retention on launch cohort:
- Total LLM cost (T+7d, USD):
- Peak Sentry error rate (per 1k requests):
- Incidents during launch window:
- PH rank / upvotes at T+24h:

## Decisions to log in §29
- (additions to the CLAUDE.md decision log)

## What worked
- ...

## What didn't
- ...

## Open follow-ups
- [ ] item (owner, due)
- [ ] item (owner, due)
```

The retro is what makes the next launch better. Skipping it is the
single most expensive thing the founder can do after the launch
itself.
