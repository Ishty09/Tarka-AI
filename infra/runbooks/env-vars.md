# Environment variables

CLAUDE.md §5 is the spec; this is the operational view — what each var
is for, where it lives, who needs it, and how to verify a fresh deploy.

## Quick check

```
pnpm verify:env                              # checks current shell env
pnpm verify:env -- --env path/to/.env        # checks a file
pnpm verify:env -- --json                    # CI-friendly output
```

The script reads `.env.example` and flags REQUIRED vars (entries with
no default value) that aren't set. Exit code is non-zero on any
missing required var.

## Per-environment owner

| Variable                                    | apps/web | apps/workers | Required for…                              | Lives in                |
| ------------------------------------------- | -------- | ------------ | ------------------------------------------ | ----------------------- |
| `NODE_ENV`                                  | ✓        | ✓            | logging + Sentry env tag                   | Vercel + Coolify        |
| `NEXT_PUBLIC_APP_URL`                       | ✓        | ✓            | OAuth callbacks, magic-link redirect, analytics hostname, Polar return URLs | Vercel + Coolify        |
| `WORKERS_URL`                               | ✓        | —            | apps/web → workers handshake               | Vercel                  |
| `NEXT_PUBLIC_DEFAULT_LOCALE`                | ✓        | —            | i18n routing fallback                      | Vercel                  |
| `NEXT_PUBLIC_SUPABASE_URL`                  | ✓        | ✓            | Supabase REST + auth                        | Vercel + Coolify        |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY`             | ✓        | ✓            | client-bound Supabase reads                | Vercel + Coolify        |
| `SUPABASE_SERVICE_ROLE_KEY`                 | —        | ✓            | workers' service-role writes (§1.3 — NEVER in web)| Coolify                 |
| `SUPABASE_DB_URL`                           | —        | ✓ (backups)  | off-site `pg_dump`                          | Droplet (backup.env)    |
| `LITELLM_PROXY_URL`                         | ✓        | ✓            | every LLM call                              | Vercel + Coolify        |
| `LITELLM_MASTER_KEY`                        | ✓ (server) | ✓          | bearer token to the proxy                   | Vercel server-only + Coolify |
| `LITELLM_SALT_KEY`                          | —        | LiteLLM      | virtual-key hash salt                       | Coolify (LiteLLM only)  |
| `OPENAI_API_KEY`                            | —        | LiteLLM      | primary LLM                                 | Coolify (LiteLLM only)  |
| `ANTHROPIC_API_KEY`                         | —        | LiteLLM      | fallback LLM                                | Coolify (LiteLLM only)  |
| `POLAR_ACCESS_TOKEN`                        | ✓        | ✓            | checkout + subscription mgmt                | Vercel + Coolify        |
| `POLAR_WEBHOOK_SECRET`                      | —        | ✓            | HMAC-verify Polar callbacks                 | Coolify                 |
| `POLAR_API_URL`                             | ✓        | ✓            | Polar API base URL                         | Vercel + Coolify        |
| `POLAR_MANAGE_URL`                          | ✓        | —            | customer portal deep link                  | Vercel                  |
| `POLAR_PRODUCT_ID_*_*`                      | ✓        | ✓            | tier resolution                            | Vercel + Coolify        |
| `ENABLE_POLAR`                              | ✓        | ✓            | feature flag — flip to true at launch       | Vercel + Coolify        |
| `RESEND_API_KEY`                            | —        | ✓            | transactional email                         | Coolify                 |
| `RESEND_FROM_EMAIL`                         | —        | ✓            | sender header                               | Coolify                 |
| `SUPPORT_EMAIL`                             | —        | ✓            | unsubscribe + footer                        | Coolify                 |
| `LEGAL_ADDRESS`                             | —        | ✓            | §16 privacy postal address in emails        | Coolify                 |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY`    | —        | ✓            | Web Push                                    | Coolify                 |
| `VAPID_SUBJECT`                             | —        | ✓            | VAPID `sub` claim                           | Coolify                 |
| `EXPO_ACCESS_TOKEN`                         | —        | ✓            | Expo push rate-limit lift                   | Coolify                 |
| `SENTRY_DSN`                                | —        | ✓            | workers Sentry                              | Coolify                 |
| `NEXT_PUBLIC_SENTRY_DSN`                    | ✓        | —            | web client + server Sentry                  | Vercel                  |
| `SENTRY_AUTH_TOKEN` / `SENTRY_ORG` / `SENTRY_PROJECT` | ✓ | — | source-map upload at build time             | Vercel build env        |
| `NEXT_PUBLIC_UMAMI_WEBSITE_ID`              | ✓        | ✓            | analytics dispatch                          | Vercel + Coolify        |
| `NEXT_PUBLIC_UMAMI_SCRIPT_URL`              | ✓        | ✓            | analytics endpoint                          | Vercel + Coolify        |
| `LANGFUSE_*`                                | —        | LiteLLM      | LLM trace ingest                             | Coolify (LiteLLM only)  |
| `GOOGLE_OAUTH_CLIENT_ID/SECRET`             | ✓        | —            | Google sign-in                              | Vercel + Supabase Auth  |
| `APPLE_SIGN_IN_*`                           | ✓        | —            | Apple sign-in                               | Vercel + Supabase Auth  |
| `WORKERS_INTERNAL_SECRET`                   | ✓        | ✓            | apps/web → apps/workers handshake bearer    | Vercel + Coolify        |
| `CRON_SECRET`                               | —        | ✓            | scheduler → /cron/* auth                    | Coolify + scheduler     |
| `ENABLE_*` feature flags                    | ✓        | ✓            | enable/disable features (§5)                | Vercel + Coolify        |
| `PG_DUMP_AGE_RECIPIENT`                     | —        | —            | backup encryption (droplet only)            | Droplet (backup.env)    |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | —      | —            | DO Spaces backup target (droplet only)      | Droplet (backup.env)    |
| `AWS_S3_ENDPOINT`                           | —        | —            | DO Spaces endpoint                          | Droplet (backup.env)    |

## Setting values

### Vercel (apps/web)

1. **Vercel → Project → Settings → Environment Variables**.
2. Pick scope: Production / Preview / Development.
3. For `NEXT_PUBLIC_*` vars, mark **Available to all environments**.
4. Redeploy after changing — env applies at build time.

### Coolify (apps/workers + self-hosted services)

1. **Coolify → quarrel-workers → Environment Variables** (or per
   service for LiteLLM / Langfuse / Umami).
2. **Restart required: yes** — FastAPI reads env at boot.
3. Use the **Secret** flag for sensitive vars (`SUPABASE_SERVICE_ROLE_KEY`,
   `POLAR_*`, `RESEND_API_KEY`, `OPENAI_API_KEY`, etc.).

### Droplet (backup automation)

Backup creds live in `/etc/quarrel/backup.env` per
`infra/runbooks/backups.md` (chmod 600, root-only). Not in Vercel, not
in Coolify — only the daily backup cron reads them.

## Pre-deploy verification

Before flipping the `ENABLE_*` flags on at launch, run through this
checklist:

- [ ] `pnpm verify:env` against a snapshot of production env returns 0
      missing required vars.
- [ ] `NEXT_PUBLIC_APP_URL` matches the production domain
      (`https://quarrel.ai`), not a preview URL.
- [ ] `NEXT_PUBLIC_SENTRY_DSN` is set on Vercel and `SENTRY_DSN` on
      Coolify. Hit `/api/health` and confirm a Sentry test event
      appears in the dashboard (`Sentry.captureMessage("deploy-check")`
      via a one-off script).
- [ ] `LITELLM_MASTER_KEY` is rotated to a fresh value (not a leftover
      dev value).
- [ ] `POLAR_PRODUCT_ID_*` match the Polar production product IDs (not
      sandbox).
- [ ] `ENABLE_POLAR=true` — payments turn on.
- [ ] `WORKERS_INTERNAL_SECRET` and `CRON_SECRET` are 32+ byte random
      hex, freshly rotated.
- [ ] Backup `/etc/quarrel/backup.env` exists and chmod 600.
- [ ] Supabase storage bucket `data-exports` exists and is private
      (one-time check; cascades from the migration in step 57 if
      Supabase storage migrations are enabled).

## Tracking changes

When a new env var is introduced:

1. Add the line to `.env.example` with a comment naming the consumer.
2. Add the row to the table above.
3. Set the value in Vercel and/or Coolify before merging the
   consumer code.
4. `pnpm verify:env` in CI catches drift.

`scripts/verify-env.mjs` is the single source of truth for the
required-vs-optional split — it derives "required" from "no default
value in `.env.example`". Don't ship a required var without setting it
in production first.
