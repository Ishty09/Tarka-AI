# Secrets policy

§22 mandates quarterly rotation. This document is the source of truth for
which secrets we hold, where they live, who can read them, and the
per-secret rotation procedure.

## Inventory

| Secret                               | Where it's used                | Rotation | Notes                                                       |
| ------------------------------------ | ------------------------------ | -------- | ----------------------------------------------------------- |
| `SUPABASE_SERVICE_ROLE_KEY`          | apps/workers                   | 90 days  | Rotate via Supabase dashboard; cascades to LiteLLM secret regen if shared. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY`      | apps/web (client + server)     | 90 days  | Rotate same day as service-role.                            |
| `OPENAI_API_KEY`                     | LiteLLM proxy                  | 90 days  | OpenAI dashboard → API keys → rotate.                       |
| `ANTHROPIC_API_KEY`                  | LiteLLM proxy                  | 90 days  | Anthropic console → API keys.                                |
| `LITELLM_MASTER_KEY`                 | apps/workers, apps/web         | 90 days  | LiteLLM `/key/regenerate`. Coordinate redeploys.            |
| `LITELLM_SALT_KEY`                   | LiteLLM proxy                  | annual   | One-way; rotating invalidates stored virtual-key hashes.    |
| `POLAR_ACCESS_TOKEN`                 | apps/web, apps/workers         | 90 days  | Polar dashboard → API tokens.                                |
| `POLAR_WEBHOOK_SECRET`               | apps/workers                   | 90 days  | Polar webhook settings → regenerate.                        |
| `RESEND_API_KEY`                     | apps/workers                   | 90 days  | Resend dashboard → API keys.                                |
| `SENTRY_DSN`                         | apps/web, apps/workers         | annual   | Sentry project settings → DSN. Rotate when leaving Sentry free. |
| `WORKERS_INTERNAL_SECRET`            | apps/web, apps/workers         | 90 days  | Random 32-byte hex; share via 1Password.                    |
| `CRON_SECRET`                        | apps/workers, scheduler        | 90 days  | Same shape as WORKERS_INTERNAL_SECRET.                       |
| `VAPID_PRIVATE_KEY`                  | apps/workers                   | annual   | Rotating invalidates push subscriptions; coordinate with users via in-app banner. |
| `GOOGLE_OAUTH_CLIENT_SECRET`         | apps/web                       | 180 days | Google Cloud Console → Credentials.                          |
| `APPLE_SIGN_IN_PRIVATE_KEY`          | apps/web                       | 180 days | Apple Developer → Keys.                                      |
| `EXPO_ACCESS_TOKEN`                  | apps/workers                   | 180 days | Expo dashboard → Tokens.                                    |
| `PG_DUMP_AGE_RECIPIENT` / identity   | droplet (recipient) + 1Password (identity) | annual | `age-keygen` → store identity 1Password-only; re-encrypt last 30d of dumps on rotation. |
| `AWS_ACCESS_KEY_ID` (DO Spaces)      | droplet (backups)              | 90 days  | DO Spaces dashboard → access keys.                          |

Add new secrets to this table the same commit they're introduced.

## Storage

- **Primary store**: 1Password vault `Quarrel Production`. Owners: ops
  team. Each entry's note field links to the rotation script section.
- **On disk**: only inside the apps' env files at deploy time. Never in
  Git. Never in Sentry breadcrumbs. Never in Langfuse traces (the
  Sentry scrubber in `apps/workers/app/observability.py` filters
  vendor names).
- **Droplet**: `/etc/quarrel/backup.env` for backup creds (chmod 600,
  root-only); Coolify-managed env vars for the running services.

## Quarterly rotation procedure

Run on the first Tuesday of January / April / July / October.

For each entry whose rotation cadence is ≤ 90 days:

1. Generate the new value in the provider's UI.
2. Stage the new value in 1Password as `<KEY> (next)`.
3. Update Coolify env vars (workers) and Vercel env vars (web) with
   the new value. Stage both before redeploying either.
4. Redeploy in dependency order:
   - LiteLLM (if its key changed)
   - apps/workers
   - apps/web
5. Verify with a synthetic chat round-trip + a successful Polar
   checkout (sandbox).
6. Revoke the old value at the provider.
7. In 1Password, promote `(next)` to the canonical entry and archive
   the previous value with the date of revocation.
8. Tick the row in `infra/runbooks/rotation-log.md` (append-only — create
   on first rotation).

Annual-cadence secrets follow the same script, scheduled in the calendar
12 months from the last rotation.

## Emergency rotation (suspected exposure)

If a secret is suspected to have leaked (committed by accident,
contractor laptop lost, etc.):

1. **Revoke first, communicate second.** Burn the value at the provider
   before anything else. Service downtime is preferable to a live leak.
2. Generate replacement; update env vars; redeploy.
3. Post an internal note in the ops channel with the timeline.
4. If user data was potentially exposed, write a §16 breach notification
   and email affected users within 72 hours per GDPR.
5. Update this file + rotation-log.md.

## Per-secret notes

### `LITELLM_MASTER_KEY`

LiteLLM exposes virtual keys derived from the master via the proxy's
`/key/regenerate` endpoint. When the master rotates:

1. Call `/key/regenerate` to invalidate downstream virtual keys.
2. Reissue virtual keys for each consumer (workers, ad-hoc scripts).
3. The master itself only lives in the LiteLLM service's env; rotating
   it does not require apps/web changes since apps/web uses a virtual
   key, not the master.

### `PG_DUMP_AGE_RECIPIENT`

Age uses asymmetric keys. The droplet has the *public* (recipient) key
which can only encrypt. The *private* (identity) key lives in 1Password
and is loaded only on restore drills (`infra/backup/restore.sh`).

After rotation, re-encrypt the last 30 days of dumps under the new key:

```
for key in $(aws s3 ls s3://quarrel-backups/ --recursive | awk '{print $4}' | grep '\.age$'); do
  aws s3 cp s3://quarrel-backups/"$key" - \
    | age --decrypt --identity old.key \
    | age --recipient $NEW_RECIPIENT \
    | aws s3 cp - s3://quarrel-backups/"$key"
done
```

(Run from a privileged machine; never on the daily-backup droplet.)
