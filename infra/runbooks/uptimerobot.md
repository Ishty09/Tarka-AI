# UptimeRobot monitors

CLAUDE.md §3 specifies UptimeRobot as the uptime tool; §27 step 63
brings the monitor set into existence.

UptimeRobot doesn't have an import-from-repo workflow, so this runbook
is the source of truth: when adding a subdomain or changing a check,
update this file first, then mirror the change in the UptimeRobot UI.

## Monitor set

All HTTPS, GET, 5-minute interval unless noted. Each monitor uses
**Keyword Exists** with the expected keyword so a degraded "200 with
HTML error page" still pages.

| Subdomain                | Path           | Keyword     | Notes                                                          |
| ------------------------ | -------------- | ----------- | -------------------------------------------------------------- |
| `quarrel.ai`             | `/api/health`  | `"ok"`      | Apex domain on Vercel. Static route — see web `app/api/health`. |
| `api.quarrel.ai`         | `/health`      | `"ok"`      | FastAPI workers, Coolify-hosted. See `apps/workers/app/main.py`. |
| `litellm.quarrel.ai`     | `/health/liveliness` | `"ok"` | LiteLLM proxy. The proxy serves `/health/liveliness` natively. |
| `langfuse.quarrel.ai`    | `/api/public/health` | `"ok"` | Langfuse public health endpoint. |
| `umami.quarrel.ai`       | `/api/heartbeat` | `"ok"`    | Umami's built-in health route. |
| `coolify.quarrel.ai`     | `/api/health`  | `"ok"`      | 10-minute interval — Coolify outage is operator-only, doesn't page on-call. |
| `status.quarrel.ai`      | `/`            | `Quarrel`   | Public status page — meta-monitor, alerts if our own status page is down. |

Future monitors when the feature lands:

- `webpush.quarrel.ai` (when self-hosted push proxy launches; out of MVP).
- TLS certificate-expiry monitor on apex — UptimeRobot does this
  natively; enable once DNS is on Cloudflare.

## Alert routing

- **On-call SMS** (founder): apex, api, litellm. Anything in this group
  going down means the chat path is broken.
- **Email only**: langfuse, umami. These are observability; an outage is
  embarrassing but not user-visible.
- **Email only**: coolify, status page. Operator-grade.

Configure these via UptimeRobot **Alert Contacts** + the per-monitor
"select alert contacts" picker. Default to:

- `oncall+pager@quarrel.ai` for SMS-tier monitors.
- `oncall+email@quarrel.ai` for email-only.

## Pause protocol

Pause a monitor in the UI when:

- You're cutting a deploy that involves restart (max 10 minutes — set a
  calendar reminder to un-pause).
- The DC has a known regional outage (e.g. Cloudflare RU edge); use the
  maintenance window so the public status page reflects it.

Never delete a monitor — pause it. Deletions lose the historic uptime
graph that we publish on the status page.

## Adding a new subdomain

1. Add the DNS record on Cloudflare.
2. Add the row to the table above with the keyword check.
3. In the UptimeRobot UI:
   - **Add New Monitor** → **HTTPS** → enter the URL.
   - **Monitor Settings** → set interval, **Alert Contacts** per the
     routing rules above.
   - **Advanced** → **Keyword monitoring** = `Exists`, keyword from the
     table.
4. Verify a manual "Check now" returns green within 2 minutes.

## Expected response shapes

For the in-house health endpoints we control:

- `quarrel.ai/api/health` → `{"status":"ok","app":"quarrel-web","build":"…"}`
- `api.quarrel.ai/health` → `{"status":"ok"}`

The shared substring `"ok"` is what the keyword monitor looks for, so a
deploy that changes the JSON shape must preserve that token.
