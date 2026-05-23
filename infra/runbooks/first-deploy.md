# First production deploy

This is the **bridge** between §26 (accounts + droplet bootstrap) and
`deploy.md` (ongoing deploys). Read once, work top-to-bottom. You only
do this once.

Estimated time: 4-6 hours from a fresh accounts setup. Realistically:
plan a Saturday.

## Phase 0 — accounts (§26 pre-code)

Before anything else, all of these must exist with green KYC where
required:

- [ ] DigitalOcean droplet provisioned (4 vCPU / 8 GB / 80 GB, NYC3 or
      FRA1, SSH hardened per §26).
- [ ] Cloudflare account; domain on Cloudflare DNS.
- [ ] Supabase project created (region close to the droplet).
- [ ] OpenAI API key with GPT-5 access.
- [ ] Anthropic API key with Sonnet 4.6 + Haiku 4.5.
- [ ] Polar.sh account, **BD KYC submitted** (this is the slowest
      external item — start it weeks ago if you haven't).
- [ ] Resend account, domain verified (SPF + DKIM + DMARC in Cloudflare).
- [ ] Sentry account + project (web AND workers projects, separate DSNs).
- [ ] Vercel account linked to GitHub.
- [ ] DigitalOcean Spaces bucket `quarrel-backups` ($5/mo).

If anything above is missing, stop and finish it first. Deploying
without Sentry means the first error is silent; without Polar means
you can't take payment; without the backup bucket means your first
data loss is your first data loss.

## Phase 1 — Supabase (1 hour)

### 1.1 Apply migrations

From your laptop, with Supabase CLI installed and linked to the
project:

```bash
supabase link --project-ref <ref>
supabase db push
```

This runs every file in `supabase/migrations/` in timestamp order.
16 migrations as of this writing.

Verify in the Supabase dashboard → Database → Tables that all
expected tables exist: profiles, personas, conversations, messages,
user_facts, contradictions, mirror_reports, eulogy_reports,
couple_links, group_rooms, group_members, roast_feed_posts,
roast_feed_votes, wagers, wager_checkins, streaks, anti_charities,
subscriptions, usage_quotas, idempotency_keys, push_subscriptions,
crisis_hotlines, safety_incidents, audit_log, data_export_requests,
beta_invites.

### 1.2 Seed data

```bash
psql "$SUPABASE_DB_URL" -f supabase/seed.sql
```

Seeds 10 anti-charities (§9.6) + 15 crisis hotlines (§15) +
the 25 launch personas. **Verify the crisis_hotlines rows with a
native speaker before any user touches the product** — the §28 gate
includes this.

### 1.3 Storage bucket

The `data-exports` bucket is created by the step-57 migration. If
Supabase storage didn't pick that up (older Supabase versions), make
it manually in Dashboard → Storage → New bucket → name `data-exports`,
**private** (not public).

### 1.4 Auth providers

Dashboard → Authentication → Providers:

- Enable **Email** (magic link).
- Enable **Google OAuth** (paste your `GOOGLE_OAUTH_CLIENT_ID` +
  `_SECRET`).
- Enable **Apple Sign-In** if you've completed Apple Developer
  enrollment; otherwise skip and add post-launch.
- Set the **Site URL** to `https://quarrel.ai`.
- Add **Redirect URLs**: `https://quarrel.ai/auth/callback` plus your
  preview Vercel URLs.

### 1.5 Email templates

Dashboard → Authentication → Email Templates → upload the Quarrel-
branded magic-link template (basic HTML, your subject line, footer
with `Quarrel <noreply@quarrel.ai>`). Supabase manages this template,
not Resend — easy to forget.

## Phase 2 — Coolify + self-hosted services (1.5 hours)

If §26 bootstrap is done, Coolify is already running at
`http://DROPLET_IP:8000`. Point `coolify.quarrel.ai` to the droplet IP.

Deploy each service in this order. For each: in Coolify, **Resources
→ New Service → Docker image**, set the domain, attach persistent
volumes where listed, add env vars from `infra/runbooks/env-vars.md`.

### 2.1 LiteLLM proxy

- Image: `ghcr.io/berriai/litellm-database:main-stable`
- Domain: `litellm.quarrel.ai`
- Required env: `LITELLM_MASTER_KEY`, `LITELLM_SALT_KEY`, `DATABASE_URL`
  (Coolify Postgres for LiteLLM), `STORE_MODEL_IN_DB=true`,
  `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
- Upload `infra/litellm-config.yaml` via the LiteLLM admin UI after
  it's up (covers the model_list + fallback chains from §7.1).

### 2.2 Langfuse

- Image: `langfuse/langfuse:latest`
- Domain: `langfuse.quarrel.ai`
- Env per Langfuse docs. Take the API keys it emits and put them as
  `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` in LiteLLM.

### 2.3 Umami

- Image: `ghcr.io/umami-software/umami:postgresql-latest`
- Domain: `umami.quarrel.ai`
- Env: `DATABASE_URL` (Coolify Postgres for Umami), `APP_SECRET`.
- After it's up: log in, create a site for `quarrel.ai`, copy the
  website ID into `NEXT_PUBLIC_UMAMI_WEBSITE_ID`.

### 2.4 Uptime Kuma

- Image: `louislam/uptime-kuma:latest`
- Domain: `status.quarrel.ai`
- Configure the public status page per `status-page.md`.
- Add the 7 monitors per `uptimerobot.md` (UptimeRobot pages on-call;
  Kuma is the public surface).

### 2.5 Workers (apps/workers)

- Coolify → Applications → New from Git → point at your GitHub repo
  + branch `main`.
- Build: uses the `Dockerfile` in `apps/workers/`.
- Domain: `api.quarrel.ai`.
- Env: full set per `env-vars.md` Coolify column.
- Health check path: `/health`.

After deploy, hit `https://api.quarrel.ai/health` from your laptop.
Expect `{"status":"ok"}`.

## Phase 3 — Vercel (apps/web) (30 min)

- Import the repo in Vercel.
- **Root directory**: `apps/web`.
- **Framework**: Next.js (auto-detected).
- **Build command**: `pnpm build` (Vercel auto-runs in the right
  workspace).
- Env vars: full set per `env-vars.md` Vercel column.
- Connect `quarrel.ai` (apex) + `www.quarrel.ai` to the project.
- First build will fail if any required env var is missing — `pnpm
  verify:env` locally first to confirm.

## Phase 4 — Verification (45 min)

### 4.1 Smoke

```bash
CRON_SECRET="$(your secret)" \
pnpm smoke -- --base https://quarrel.ai \
              --workers https://api.quarrel.ai \
              --cron-secret "$CRON_SECRET"
```

Every check must pass. If any fail, fix before proceeding — these
are the gates that step 71 sets up.

### 4.2 Manual smoke (the signed-in flow `pnpm smoke` can't reach)

Per `smoke-tests.md`'s "Deeper post-launch tests" — work through the
7 steps with a real (your own) account:

1. Sign up with a fresh email. Magic-link email lands in < 30s.
2. Complete onboarding through to first chat.
3. Send one Argue-mode message with `devils_advocate`. Streaming
   starts < 2s, message persists on reload.
4. Trigger nightly contradiction batch via the cron endpoint with
   `CRON_SECRET`. Refresh `/contradictions` — should appear.
5. Start a Polar sandbox checkout for Pro. Cancel. Confirm no
   subscription row was created.
6. Request data export from `/settings/data`. Trigger
   `/cron/data-export`. Email arrives within 5 minutes with a
   working signed URL.
7. Request account deletion from `/settings/data`. Confirm grace
   email lands. Cancel deletion to keep the test account.

### 4.3 Sentry sanity

Throw a test event from each:

```bash
# Workers
curl -X POST https://api.quarrel.ai/health  # then break it manually

# Web — visit a non-existent server route, e.g. /api/this-fails
```

Confirm both events appear in their respective Sentry projects.

### 4.4 Langfuse sanity

Send one chat message. Open `langfuse.quarrel.ai` → Traces. Confirm
the trace has the §21 metadata: `generation_name` matching
`<mode>.<persona_slug>`, `user_id` (hashed), `session_id` (the
conversation id), tags.

### 4.5 Status page + UptimeRobot

- `status.quarrel.ai` renders with all 5 components green.
- UptimeRobot all monitors green for ≥ 1 hour before considering
  this section done.

## Phase 5 — Backups (30 min)

On the droplet:

1. Create `/etc/quarrel/backup.env` (chmod 600, root-only) with the
   keys from `backups.md`.
2. Install the crontab:
   ```
   sudo cp infra/backup/crontab /etc/cron.d/quarrel-backups
   sudo chmod 644 /etc/cron.d/quarrel-backups
   sudo systemctl restart cron
   ```
3. Trigger one manual dump to verify:
   ```
   sudo . /etc/quarrel/backup.env && \
     /opt/quarrel/infra/backup/pg_dump.sh "$LITELLM_DB_DSN" \
       quarrel-backups litellm/daily
   ```
   Then list the bucket and confirm the .age file is there.

## Phase 6 — Done. Now dogfood.

Before sending a single beta invite, **use Quarrel for 24-48 hours
yourself**. As a real user, not as the founder. The bug you find
yourself is the bug your inner circle won't have to find for you.

Specifically:

- Send 10+ chat messages across different modes.
- Set up a Daily Roast at a time you'll actually be awake for.
- Create a custom persona, watch it land in the moderation queue
  (or auto-approve if you've toggled it).
- Pin /admin/incidents in a tab, refresh every few hours for the
  first 48h.
- If you find a P1 bug, fix it before sending invites. P2-P3 — log
  in a follow-up file, ship the invites anyway.

Then come back to `public-launch.md` and continue from "T-24h".

## Common first-deploy traps

- **Migrations applied out of order.** Symptom: `relation does not
  exist` on a FK. Cause: timestamps got reordered when you cherry-
  picked a branch. Fix: roll the Supabase project back and re-apply.
- **LITELLM_MASTER_KEY mismatch.** Web + workers both use it; if you
  rotated on one but not the other, every chat returns 401. Fix:
  rotate everywhere, redeploy both.
- **Cloudflare proxy + SSE.** Cloudflare's default proxy buffers
  long-running responses; the chat stream falls apart. Fix: set the
  `api.quarrel.ai` DNS record to **DNS only** (gray cloud), not
  proxied (orange cloud).
- **Supabase storage bucket private flag missed.** If `data-exports`
  ends up public, signed URLs still work but anyone with an object
  path can read directly. Fix: dashboard → bucket → toggle off
  public.
- **Polar product IDs swapped.** Sandbox IDs in production env →
  every checkout fails or creates a $0 subscription. Fix: re-read
  `env-vars.md`, set the four `POLAR_PRODUCT_ID_*` vars from the
  Polar production catalog.
- **The Supabase email template doesn't include the magic link
  placeholder.** Symptom: users get an empty email. Fix: re-upload
  the template, verify the `{{ .ConfirmationURL }}` placeholder is
  present.

## If you get stuck

- Sentry will have the stack trace.
- Langfuse will have the LLM trace if the issue is mid-chat.
- `pnpm smoke` will narrow which surface is broken.
- For everything that points back at "I don't know which subsystem":
  follow `incident-response.md`'s triage flow.
