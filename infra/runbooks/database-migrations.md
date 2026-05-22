# Database migrations

CLAUDE.md §1.6 + §1.13: append-only migrations under
`supabase/migrations/`, explicit human confirmation before any drop,
rename, or schema-incompatible change. This runbook is how those rules
translate into action.

## Authoring

1. New file under `supabase/migrations/` named
   `YYYYMMDDHHMMSS_<short_purpose>.sql`. Timestamps must be strictly
   monotonic — pull-rebase before pushing if a teammate landed one
   first.
2. The migration is **idempotent where possible**:
   - `CREATE TABLE IF NOT EXISTS` for new tables (Supabase replays on
     restore drills; idempotency saves us).
   - `ADD COLUMN IF NOT EXISTS` for column additions.
   - For RLS policies, `DROP POLICY IF EXISTS` then `CREATE POLICY`.
3. Append-only: never edit a landed migration. If you need to change
   something, add a new migration that does the alteration.
4. RLS on every new table. Tests in `apps/workers/tests/` should cover
   the policy by exercising the access patterns.
5. Cross-link in the PR description: which `apps/web` or
   `apps/workers` change relies on this migration.

## Reviewing

Migrations review against `infra/runbooks/database-migrations.md`
mentally:

- Does this drop a column? → STOP, ask the founder.
- Does this rename a column? → STOP, ask the founder.
- Does this change a CHECK constraint that existing rows might violate?
  → STOP, ask the founder. Plan a backfill first.
- Does this index without `CONCURRENTLY`? → fine for empty tables, but
  risky on hot tables (locks them). For tables with > 1M rows, use
  `CREATE INDEX CONCURRENTLY` in a second migration.

The destructive checklist matches §1.13's "stop and ask" rule.

## Applying

### Local / staging

```
supabase db push --workdir supabase
```

This applies every unapplied migration in timestamp order. Failure on
any migration halts and rolls back its transaction.

### Production

Production migrations apply at deploy time via the Supabase migration
runner. The flow:

1. Merge to `main`.
2. Supabase auto-applies new migrations against the production DB.
3. Watch the Supabase dashboard → Database → Migrations for green.
4. **Only then** does the Coolify or Vercel deploy proceed (use the
   coordinated-deploy procedure in `deploy.md`).

If Supabase can't reach the DB or the migration fails:

- The deploy halts.
- The previous code stays serving against the previous schema (good).
- Investigate before retrying.

## Rolling back

You do NOT roll back a migration in production. Migrations are
append-only by design — rolling back via a `DROP TABLE` or `DROP COLUMN`
breaks the rule and risks data loss.

Instead:

1. Land a new forward migration that walks back the harm (e.g., adds
   the column you accidentally dropped — with an `IF NOT EXISTS`
   guard).
2. Coordinate with the application code change.

If the migration is so broken it must be undone immediately:

- Restore from the most recent Supabase daily backup (§25.1).
- This is destructive — any user data written between the snapshot and
  the restore is lost. Treat as a SEV1 with all the comms that implies.

## Concurrent writes during migration

Supabase migrations run as a single transaction by default. Long-running
operations (`ALTER TABLE ... ADD COLUMN DEFAULT ...` on a big table)
take a table lock. Mitigations:

- Add the column NULLable first (cheap).
- Backfill in a separate migration with no lock (use a Postgres function
  that batches).
- Add the NOT NULL + default in a third migration after backfill.

The §57 GDPR export pipeline rolled `data_export_requests` in as a single
migration because the table was empty; that's the trivial case.

## Migration test

Every new migration should have at least one workers-side test that
exercises the new schema. Examples already in the repo:

- `tests/test_data_export.py` exercises the new
  `data_export_requests` table from step 57.
- `tests/test_account_deletion.py` exercises the `audit_log` FK change
  + the `deletion_grace_notified_at` column from step 58.

If a migration changes RLS, the test must verify both the allowed and
the denied path (positive + negative coverage).

## Restoring a single table from backup

Sometimes you need to recover one table without a full restore. Use the
`pg_restore --data-only --table=<name>` flow against a side database
loaded from the most recent dump:

```
infra/backup/restore.sh quarrel-backups \
  supabase/weekly/<dump>.sql.gz.age \
  postgres://restore:restore@staging:5432/restore_db

pg_dump --dbname=postgres://restore:restore@staging:5432/restore_db \
  --table=<table_name> --data-only --column-inserts \
  | psql --dbname=$SUPABASE_DB_URL
```

This is destructive on the target table — wrap in a transaction and
`TRUNCATE` first if you want a true replacement, or `INSERT` if you want
to merge. Treat as a SEV1-grade operation.
