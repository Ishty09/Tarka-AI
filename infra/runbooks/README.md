# Runbooks

Operational documentation for running Quarrel AI in production. Each
file is read top-to-bottom during a real situation — no skimming.

| Runbook                          | When to read it                                                       |
| -------------------------------- | --------------------------------------------------------------------- |
| [`incident-response.md`](./incident-response.md) | You got paged. Severity tiers, ack windows, comms templates, post-mortem format. |
| [`uptimerobot.md`](./uptimerobot.md)             | Adding or pausing an external uptime monitor. Defines the canonical monitor set. |
| [`status-page.md`](./status-page.md)             | Posting an incident on `status.quarrel.ai`, configuring Uptime Kuma, or onboarding a new public component. |
| [`backups.md`](./backups.md)                     | Verifying daily/weekly backups; running a restore drill; recovering from a database outage. |
| [`deploy.md`](./deploy.md)                       | Shipping a change. Web (Vercel) and workers (Coolify) procedures, including rollback. |
| [`database-migrations.md`](./database-migrations.md) | Authoring or applying a Supabase migration; handling production schema issues. |
| [`safety-triage.md`](./safety-triage.md)         | Daily review of `safety_incidents`, moderation queues, abuse / minor-safety / threat handling. |
| [`env-vars.md`](./env-vars.md)                   | Per-variable owner table, where each value lives, pre-deploy checklist. |
| [`smoke-tests.md`](./smoke-tests.md)             | What `pnpm smoke` covers; when to run; the deeper signed-in checklist. |
| [`beta-cohort.md`](./beta-cohort.md)             | Hand-picked beta invitees: staging the list, triggering sends, retention query for §28. |
| [`product-hunt-launch.md`](./product-hunt-launch.md) | T-14 → T+7d launch playbook: assets, timing, comment SLA, status-page protocol, retro template. |
| [`../SECRETS.md`](../SECRETS.md)                 | Quarterly rotation, emergency rotation, per-secret procedures.        |

Companion scripts and config live one level up:

- `../backup/` — `pg_dump.sh`, `restore.sh`, `crontab`.

When you add a new runbook, add a row above and commit in the same
change.

## Conventions

- Imperative voice — "Run X", not "We would run X".
- Concrete commands, no pseudocode.
- Templates inline so an operator at 3 AM doesn't have to dig.
- Every promise the runbook makes (RTO, RPO, SLA window) ties back to a
  §-number in `CLAUDE.md`.
- No blame. Post-mortems describe systems, not people.
