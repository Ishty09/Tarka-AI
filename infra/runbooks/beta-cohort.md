# Beta cohort

CLAUDE.md §27 step 72 ("100 hand-picked beta users invited") and step 73
("7-day retention measured"). This runbook covers the closed-beta
window between deploying everything and the §27 step 75 public launch.

## Cohort tags

We track invitees by cohort tag so retention can be sliced. Suggested
naming:

- `wave-1` — the first 30 friends-and-family who tolerate rough edges.
- `wave-2` — the next 70 from the hand-picked list (HN, X, founder
  networks).
- `founder-friends` — anyone the founder personally pinged.
- `partners` — Polar, Supabase, OpenAI contacts who get an early look.

A user can appear in multiple cohorts; the `(email, cohort_tag)` unique
key allows re-inviting if the first link expired.

## Inviting a batch

1. Drop a list at `data/<cohort>.json` (or `.txt` for plain
   one-per-line). Example JSON:

   ```json
   [
     { "email": "alice@example.com", "notes": "ex-coworker, indie hacker" },
     { "email": "bob@example.com",   "notes": "HN, replied to launch tweet" }
   ]
   ```

2. Stage with `--dry-run` to validate format:

   ```bash
   NEXT_PUBLIC_SUPABASE_URL=... \
   SUPABASE_SERVICE_ROLE_KEY=... \
   pnpm invite:beta -- --file data/wave-1.json --cohort wave-1 --dry-run
   ```

3. Run for real:

   ```bash
   pnpm invite:beta -- --file data/wave-1.json --cohort wave-1
   ```

   Duplicates (email + cohort already in the table) are skipped via
   the Postgres unique key.

4. Trigger the drain immediately so the emails land in minutes rather
   than waiting for the next cron tick:

   ```bash
   curl -X POST -H "Authorization: Bearer $CRON_SECRET" \
     https://api.quarrel.ai/cron/beta-invites
   ```

## What happens server-side

- Each row in `beta_invites` with `sent_at IS NULL AND error_message IS
  NULL` is picked up by `/cron/beta-invites`.
- The worker calls Supabase admin's `generate_link({type: 'magiclink'})`
  which auto-creates the auth.users row if the email is new.
- The link plus the `beta_invite` email template ship via Resend with
  an idempotency key (`email:beta_invite:<invite_id>`) so retries don't
  double-send.
- `sent_at` and `expires_at` (24h) are stamped on success;
  `error_message` is stamped on failure and excludes the row from the
  next tick until an operator clears it.

When the invitee signs up, the `beta_invites_link_profile` trigger
(see the migration) backfills `signed_up_at` and `signed_up_user_id`
on every row that matches the email and was still pending.

## Cron schedule

The job is wired but no scheduler entry is added by default — beta
sends are bursty (a few hundred rows once or twice in the launch
window), not continuous. After staging a batch, operators trigger the
cron manually until the queue drains.

If we ever want it continuous, add a 5-minute cron entry on the
droplet:

```
*/5 * * * * root . /etc/quarrel/backup.env && curl -fsS -X POST \
  -H "Authorization: Bearer $CRON_SECRET" \
  https://api.quarrel.ai/cron/beta-invites
```

## Retention query (§27 step 73)

The 7-day retention story for a cohort:

```sql
with cohort as (
  select email, signed_up_at, signed_up_user_id
  from beta_invites
  where cohort_tag = 'wave-1'
    and signed_up_at is not null
),
active_d2 as (
  -- Users who sent ≥ 1 message on day 2-7 after signup.
  select cohort.signed_up_user_id
  from cohort
  join messages m on m.user_id = cohort.signed_up_user_id
  where m.created_at between cohort.signed_up_at + interval '1 day'
                         and cohort.signed_up_at + interval '7 days'
    and m.role = 'user'
  group by cohort.signed_up_user_id
)
select
  (select count(*) from beta_invites where cohort_tag = 'wave-1')             as invited,
  (select count(*) from cohort)                                               as signed_up,
  (select count(*) from active_d2)                                            as retained_d2_d7;
```

§28 launch criterion: `retained_d2_d7 / signed_up >= 0.30`.

## When an invitee never received the email

1. Open `/admin` (admin profile required).
2. Look at the row in `beta_invites` for the address. Check
   `error_message`.
3. Common causes:
   - **Typo in the email** — fix in Supabase or re-invite under a new
     cohort tag.
   - **Supabase admin link rate-limited** — Supabase enforces 30
     emails/hour by default on the free tier. Wait an hour or upgrade.
   - **Resend bounced** — Resend dashboard → Events. Hard bounces
     get the message permanently.
4. Clear `error_message` to re-queue:

   ```sql
   update beta_invites
      set error_message = null
    where email = '...' and cohort_tag = 'wave-1';
   ```

   The next cron tick will retry.

## Rotation back to invitee list

When the public launch closes the beta:

1. Run the retention query and archive the result alongside the
   launch retro in `infra/runbooks/post-mortems/`.
2. Keep the `beta_invites` rows — they're the historical record of who
   we vouched for. Don't delete.
