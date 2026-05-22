# Incident response

When something breaks at 3 AM, this is the page you read first.

## Severity tiers

| Tier | Definition                                                                 | Ack window | Comms                                                       |
| ---- | -------------------------------------------------------------------------- | ---------- | ----------------------------------------------------------- |
| SEV1 | User-facing chat path broken or data loss in progress.                     | 5 min      | Status page Investigating within 10 min. Update every 30 min until resolved. |
| SEV2 | Degraded but not fatal (slow streaming, one tool down, fallbacks engaged). | 30 min     | Status page within 1 hour. Update every 2 hours.            |
| SEV3 | Observability or operator-side (Langfuse down, Umami down, Coolify down).  | 4 hours    | Internal note in ops channel; no public status page entry.   |

UptimeRobot alert mapping (see `uptimerobot.md`):

- SMS-tier monitors (apex, api, litellm) → assume SEV1 until you've
  confirmed otherwise.
- Email-tier (langfuse, umami, coolify) → SEV3 unless symptoms suggest
  broader fallout.

## On-call flow

1. **Ack.** Reply to the UptimeRobot SMS/email within the tier's ack
   window. If you can't ack, escalate (see §"Escalation tree").
2. **Triage.** Open the live dashboards:
   - `status.quarrel.ai` (what users see).
   - Sentry web + Sentry workers (active error rate).
   - Langfuse (`langfuse.quarrel.ai`) for LLM-side anomalies.
3. **Post Investigating.** Status page entry within the tier's comms
   window. Template in §"Status page templates".
4. **Mitigate.** In order of preference:
   - Restart the affected Coolify service.
   - Flip the relevant feature flag in `.env` (e.g. `ENABLE_WAGERS=false`
     during a Polar incident).
   - Roll back the last deploy (`vercel rollback`, or Coolify
     "Redeploy previous").
   - Failover (DR scenario in `backups.md`).
5. **Communicate.** Update the status page entry every interval per the
   table above. Keep entries factually descriptive; never promise an
   ETA you don't have.
6. **Resolve.** Status page → Resolved with a one-sentence cause.
7. **Post-mortem.** Within 48 hours, fill in the template in
   §"Post-mortem template".

## Escalation tree

| Order | Contact                        | Reach                                          |
| ----- | ------------------------------ | ---------------------------------------------- |
| 1     | Primary on-call (founder)      | UptimeRobot SMS; `oncall+pager@quarrel.ai`.    |
| 2     | Backup on-call                 | TBD when team grows past 1.                    |
| 3     | External help                  | Supabase support (DB), Polar support (billing), Vercel support (web hosting), DigitalOcean support (droplet). |

Until there's a backup, escalate after **30 minutes of no ack** by
posting in the founder's public Discord + emailing
`oncall+pager@quarrel.ai`. The runbook is the on-call.

## Status page templates

### Investigating

> We're investigating reports of [degraded chat replies / login
> failures / payment errors]. Affected: [Web / Workers / LiteLLM /
> Supabase / Polar]. Next update by HH:MM UTC.

### Identified

> We've identified the cause as [a database connection saturation / a
> bad deploy / an upstream LiteLLM timeout]. We're [restarting the
> service / rolling back / waiting on provider]. Next update by HH:MM UTC.

### Resolved

> Resolved at HH:MM UTC. Cause: [one sentence]. A post-mortem will be
> published within 48 hours.

## Post-mortem template

Append to `infra/runbooks/post-mortems/YYYY-MM-DD-<short-title>.md`:

```
# YYYY-MM-DD <short title>

**Severity:** SEV1/2/3
**Detected:** HH:MM UTC
**Resolved:** HH:MM UTC
**Duration:** N minutes
**Affected:** [components]
**User-visible impact:** [one paragraph]

## Timeline
- HH:MM — event 1
- HH:MM — event 2
- ...

## Root cause
[Concrete chain — "X happened, which caused Y, which caused Z".]

## What worked
[The detection signal, the mitigation that worked, etc.]

## What didn't
[The lag, the missing dashboard, the silent failure.]

## Follow-ups
- [ ] action item (owner, due)
- [ ] action item (owner, due)
```

No blame. Action items are concrete and dated; "improve monitoring" is
not an action item.

## Things to NEVER do during an incident

- Force-push or amend commits on `main`.
- Run `supabase db push` from a personal laptop. Migrations only via the
  documented procedure in `database-migrations.md`.
- Disable Sentry or analytics to "clear noise" — you're losing the only
  trail you have.
- Promise a fix ETA in the status page if you don't have one. "Next
  update by HH:MM" is the only promise to make.
- Skip the post-mortem. The 48-hour deadline is sacred — a missed
  post-mortem turns into a missed lesson.
