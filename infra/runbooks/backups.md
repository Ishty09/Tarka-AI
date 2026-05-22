# Backups + disaster recovery

CLAUDE.md §25 — RPO 24h, RTO 4h (web) / 24h (self-hosted).

## What we back up

| Source                 | Cadence               | Destination                          | Retention                                 |
| ---------------------- | --------------------- | ------------------------------------ | ----------------------------------------- |
| Supabase Postgres      | Daily (managed)       | Supabase platform                    | 7 days rolling                            |
| Supabase Postgres      | Weekly off-site dump  | `s3://quarrel-backups/supabase/weekly` | 30 days rolling (Spaces lifecycle policy) |
| LiteLLM Postgres       | Daily 03:00 UTC       | `s3://quarrel-backups/litellm/daily`   | 30 days                                   |
| Langfuse Postgres      | Daily 03:10 UTC       | `s3://quarrel-backups/langfuse/daily`  | 30 days                                   |
| Umami Postgres         | Daily 03:20 UTC       | `s3://quarrel-backups/umami/daily`     | 30 days                                   |
| Coolify volumes (full) | Weekly 05:00 UTC Sun  | `s3://quarrel-backups/coolify`         | 4 weeks                                   |

The Spaces lifecycle policy on `quarrel-backups` deletes objects older
than retention automatically. Configure once via:

```
aws s3api put-bucket-lifecycle-configuration \
  --endpoint-url https://<region>.digitaloceanspaces.com \
  --bucket quarrel-backups \
  --lifecycle-configuration file://infra/backup/lifecycle.json
```

(Lifecycle JSON is operator-side; not committed to keep the prefix list
flexible.)

## Encryption

Every dump is encrypted with `age` before it leaves the droplet.

- Public key (recipient): `age1...` lives in environment as
  `PG_DUMP_AGE_RECIPIENT`. Anyone with the public key can encrypt; only
  the private key can decrypt.
- Private key (identity): stored in 1Password under
  `Backup decryption key`. Used only during restore drills; never
  copied to the droplet that performs daily backups.

Rotation: regenerate every 12 months, or immediately if exposure is
suspected. After rotation, re-encrypt the most recent 30 days of dumps
under the new key (so any restore drill in the next month succeeds).

## Verification

The dailies must be touched without errors. We verify three ways:

1. **Mail-on-failure.** The crontab sets `MAILTO=ops@quarrel.ai`. If any
   line exits non-zero, cron mails the output. No mail = success.
2. **Spaces metadata probe.** A weekly cron on the droplet lists the
   latest object in each prefix and asserts the timestamp is within 26
   hours (slightly past the 24h budget for the 1-hour window between
   runs).
3. **Monthly restore drill.** See §"Restore drill" below.

## Restore drill (monthly)

The first Tuesday of each month, restore the most recent LiteLLM dump
into a throwaway Postgres on the staging droplet and run a sanity query:

```
infra/backup/restore.sh quarrel-backups \
  litellm/daily/<latest-key> \
  postgres://restore:restore@staging:5432/litellm_restore

psql postgres://restore:restore@staging:5432/litellm_restore \
  -c 'select count(*) from model;'
```

Record the run in `infra/runbooks/restore-drill-log.md` (created on
first drill — append-only). A drill counts as passed if the count is
non-zero and the schema introspection looks normal.

Drill cadence rotation:

- Month 1: LiteLLM
- Month 2: Langfuse
- Month 3: Umami
- Month 4: Supabase off-site dump
- Month 5: Coolify volume restore (full droplet rebuild rehearsal)

## Disaster recovery procedure

### Scenario A: Supabase Postgres lost

- RTO target: 4 hours.
- Steps:
  1. Open a P1 ticket with Supabase support — they restore from their
     managed daily backup.
  2. If Supabase is unreachable beyond 4 hours, provision a fresh
     Supabase project in a different region, run `supabase db push` from
     `supabase/migrations`, then restore the latest `supabase/weekly`
     dump with `infra/backup/restore.sh`.
  3. Point `NEXT_PUBLIC_SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` at
     the new project; redeploy `apps/web` on Vercel and `apps/workers`
     via Coolify.

### Scenario B: Droplet lost

- RTO target: 24 hours for self-hosted services.
- Steps:
  1. Re-provision a droplet per §26 bootstrap script.
  2. Re-install Coolify per §26.
  3. Restore the most recent `coolify` volume backup using Coolify's
     restore CLI.
  4. Restart the four services. They come back with their data because
     volume restore included the Postgres data directories.
  5. Re-point Cloudflare DNS A records to the new droplet IP.

### Scenario C: Single subsystem (LiteLLM, Langfuse, or Umami) corrupted

- RTO target: 4 hours.
- Steps:
  1. Stop the affected Coolify service.
  2. Drop and recreate its database.
  3. `infra/backup/restore.sh quarrel-backups <prefix>/daily/<latest> <dsn>`.
  4. Restart the service.

## Where credentials live

| Secret                   | Location                                                       |
| ------------------------ | -------------------------------------------------------------- |
| Spaces access + secret   | 1Password → "DO Spaces (backups)". Copied to `/etc/quarrel/backup.env`. |
| Age public key           | Same file, also in 1Password.                                  |
| Age private key          | 1Password only. Never on the droplet that runs daily backups. |
| Supabase DB URL          | 1Password → "Supabase prod". Also in `/etc/quarrel/backup.env`. |
| Coolify root credentials | 1Password → "Coolify admin".                                   |

`/etc/quarrel/backup.env` permissions:

```
sudo chown root:root /etc/quarrel/backup.env
sudo chmod 600 /etc/quarrel/backup.env
```

## Adding a new backed-up Postgres

1. Provision the Postgres in Coolify.
2. Add the DSN to `/etc/quarrel/backup.env` as `<NAME>_DB_DSN`.
3. Append a new cron line in `infra/backup/crontab` (stagger by 10
   minutes so the dumps don't all race).
4. Add a row to the table at the top of this file.
5. The next drill rotation picks it up.
