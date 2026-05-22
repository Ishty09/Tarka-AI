# Public status page — status.quarrel.ai

CLAUDE.md §25.3 promises a public status page with five components and
≤30-minute incident updates. §3 lets us choose between hosted Statuspage
and self-hosted Uptime Kuma; we picked **Uptime Kuma**, MIT-licensed,
deployed via Coolify alongside the other self-hosted observability stack
(LiteLLM, Langfuse, Umami).

This runbook is the source of truth. UptimeRobot pages on-call when
upstream services break; this status page is what users see during an
incident.

## 1. Deploy Uptime Kuma

In Coolify on the production droplet:

1. **Resources → New Service → Docker image**
   - Image: `louislam/uptime-kuma:latest`
   - Domain: `status.quarrel.ai`
   - Volume: `/app/data` → persistent (mandatory — incident history lives
     here).
   - Coolify auto-issues a Let's Encrypt cert via Caddy.

2. Once green, open `status.quarrel.ai`, complete the first-run setup
   wizard. Username: `ops`. Password lives in 1Password under
   `Status page admin`.

3. **Settings → General**
   - Time zone: UTC (so the public timeline is unambiguous).
   - Theme: Auto.
   - Footer text: `Operated by Quarrel AI. Incidents update within 30
     minutes per our SLA.`

4. **Settings → Maintenance**
   - Default cron + duration policy: 15-minute window unless overridden.

## 2. Components

§25.3 lists five public components. Create each as a separate **Status
Page → Monitor** in Uptime Kuma. The list is intentionally short — users
care about chat working, not which subdomain hosts what.

| Component  | What it covers                                          | Underlying probe                                                      |
| ---------- | ------------------------------------------------------- | --------------------------------------------------------------------- |
| Web        | `quarrel.ai` apex + signed-in app shell                | HTTPS keyword `"ok"` on `https://quarrel.ai/api/health`               |
| Workers    | Chat streaming, tools, cron processors                  | HTTPS keyword `"ok"` on `https://api.quarrel.ai/health`               |
| LiteLLM    | LLM gateway. When down, all chat replies fail.          | HTTPS keyword `"ok"` on `https://litellm.quarrel.ai/health/liveliness` |
| Supabase   | Database, auth, storage. Surfaced via a synthetic check. | HTTPS keyword `"swagger"` on `https://<project>.supabase.co/rest/v1/` |
| Polar      | Web subscriptions. Synthetic public-status check.       | HTTPS keyword `"ok"` on `https://status.polar.sh/api/v2/status.json`  |

The Supabase + Polar entries are **synthetic** — we don't operate either,
we surface their availability so users have one place to look. When the
upstream provider has an outage we publish an incident pointing at their
status page.

Probe interval: 60s for everyone (Uptime Kuma default). UptimeRobot
remains the on-call pager at 5-minute granularity; Uptime Kuma's 60s
probes are public-display only.

## 3. Status Page configuration

**Status Pages → Add New Status Page**:

- Slug: `quarrel`
- Title: `Quarrel AI`
- Description: `Live status for Quarrel's chat, workers, and supporting
  services.`
- Domain alias: `status.quarrel.ai`
- Visibility: **Public**
- Footer text:
  ```
  Subscribe to updates: status.quarrel.ai/subscribe
  Incident reports: https://github.com/quarrel-ai/quarrel-ai/issues
  ```

Pin all 5 monitors above into one group called **Services**.

Enable **Search Engine Indexing** = on (Google should index this).

## 4. Incident SLA

§25.3: "Incident updates within 30 min of detection." Concretely:

| Time           | Action                                                                                          |
| -------------- | ----------------------------------------------------------------------------------------------- |
| T+0            | UptimeRobot pages on-call. On-call acknowledges in the alert channel within 5 min.              |
| T+10 min       | Post **Investigating** incident on the status page (Uptime Kuma → Incidents → New).             |
| T+30 min       | Post **Identified** if the cause is known, else stay in Investigating with a clarifying note.   |
| Recovery       | Post **Resolved**, include 1-line cause and what changed.                                       |
| Within 48h     | Post a **post-mortem** comment on the incident with detection time, root cause, follow-ups.     |

Incident posting from the Uptime Kuma admin: **Incidents → New Incident**,
pick the affected components, write a one-paragraph user-facing
description (no jargon — assume a non-engineer is reading), set
**Severity**: Minor / Major / Critical, then **Publish**.

## 5. Maintenance windows

Use **Settings → Maintenance → Add** before any planned downtime longer
than 5 minutes. The status page shows the window in advance and
suppresses red bars during the window.

Always include in the description:
- What's happening (e.g., "Supabase major version upgrade").
- Expected duration.
- What users should expect (e.g., "chat may be unavailable for ~10
  minutes during the cutover").

## 6. Subscriptions

Users subscribe via `status.quarrel.ai/subscribe`. Uptime Kuma supports:

- **Email** — primary channel for non-technical users.
- **Webhook / Slack / Discord** — for power users and partners. We don't
  promise these will exist forever; they're best-effort.

Don't enable **SMS subscriptions** for the public page — costs scale
linearly with subscriber count and we have no budget for it.

## 7. Meta-monitor

UptimeRobot already monitors `status.quarrel.ai/` for the keyword
`Quarrel` (see `uptimerobot.md`). When the status page itself is down,
UptimeRobot pages on-call — there's no chicken-and-egg.

If both UptimeRobot and the status page are simultaneously unreachable,
post the incident manually to:

- `@quarrel_ai` on X (post the text from the template below).
- A pinned message in the founder's public Discord.

Template:

> Quarrel is currently experiencing an outage affecting [components].
> Our status page itself is reachable at status.quarrel.ai once
> connectivity returns; in the meantime updates will be posted here every
> 30 minutes. We're investigating.

## 8. Adding a component

When a new public-facing service launches (e.g., webpush, mobile API):

1. Add the monitor in Uptime Kuma per the table format above.
2. Add the matching UptimeRobot monitor per `uptimerobot.md`.
3. Edit this file: add the row to the table.
4. Commit.

## 9. Removing a component

Pause-don't-delete (same rule as UptimeRobot). Deleting a component
loses its historical uptime graph, and we publish those graphs on the
public page.
