"""Post-migration verification: table count + seed row counts."""

import os
import sys

import psycopg2  # type: ignore[import-not-found]

dsn = os.environ.get("PG_DSN")
if not dsn:
    print("PG_DSN required", file=sys.stderr)
    sys.exit(2)

conn = psycopg2.connect(dsn)
cur = conn.cursor()

EXPECTED_TABLES = {
    "anti_charities", "audit_log", "beta_invites", "contradictions",
    "conversations", "couple_links", "crisis_hotlines",
    "data_export_requests", "eulogy_reports", "group_members",
    "group_rooms", "idempotency_keys", "messages", "mirror_reports",
    "personas", "profiles", "push_subscriptions", "roast_feed_posts",
    "roast_feed_votes", "safety_incidents", "streaks",
    "subscriptions", "usage_quotas", "user_facts", "wager_checkins",
    "wagers",
}

cur.execute(
    "select table_name from information_schema.tables "
    "where table_schema = 'public' and table_type = 'BASE TABLE' "
    "order by table_name"
)
rows = [r[0] for r in cur.fetchall()]
found = set(rows)

print(f"Tables in public schema: {len(rows)}")
for t in rows:
    print(f"  - {t}")

missing = EXPECTED_TABLES - found
extra = found - EXPECTED_TABLES
print()
if missing:
    print(f"MISSING: {sorted(missing)}")
if extra:
    print(f"EXTRA (informational): {sorted(extra)}")
if not missing and not extra:
    print("All 26 expected tables present, no extras.")

print()
print("Seed row counts:")
for table, expected in [
    ("anti_charities", 10),
    ("crisis_hotlines", 15),
    ("personas", 25),
]:
    cur.execute(f"select count(*) from {table}")
    actual = cur.fetchone()[0]
    mark = "OK " if actual == expected else "FAIL"
    print(f"  {mark} {table}: {actual} (expected {expected})")

print()
print("Views:")
cur.execute(
    "select table_name from information_schema.views "
    "where table_schema = 'public' order by table_name"
)
for r in cur.fetchall():
    print(f"  - {r[0]}")

print()
print("Storage buckets:")
cur.execute("select id, public from storage.buckets order by id")
for r in cur.fetchall():
    print(f"  - {r[0]} (public={r[1]})")

cur.close()
conn.close()
