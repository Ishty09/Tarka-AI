"""One-shot migration applier (no Supabase CLI needed).

Each migration file runs in its own transaction so multi-statement
DDL (CREATE TABLE followed by CREATE POLICY referencing it) commits
atomically the same way Supabase CLI does.

Reads $PG_DSN. Applies every file in supabase/migrations/ in timestamp
order. Optional flags:
  --seed   apply supabase/seed.sql after migrations
  --reset  DROP SCHEMA public CASCADE first (use to recover from a
           partially-applied state). Destroys ALL data in the public
           schema — never run against a project with real users.

Usage:
  PG_DSN=postgresql://... uv run --with psycopg2-binary --no-project \
    python scripts/apply-migrations.py --reset --seed
"""

import os
import sys
from pathlib import Path

import psycopg2  # type: ignore[import-not-found]

dsn = os.environ.get("PG_DSN")
if not dsn:
    print("PG_DSN env var required", file=sys.stderr)
    sys.exit(2)

seed = "--seed" in sys.argv
reset = "--reset" in sys.argv

root = Path(__file__).resolve().parent.parent
migrations = sorted((root / "supabase" / "migrations").glob("*.sql"))

print(f"Connecting…")
conn = psycopg2.connect(dsn)
cur = conn.cursor()
print(f"Connected.\n")

if reset:
    print("Resetting public schema…")
    try:
        cur.execute(
            "drop schema if exists public cascade; "
            "create schema public; "
            "grant all on schema public to postgres, anon, authenticated, service_role;"
        )
        conn.commit()
        print("  reset ok\n")
    except Exception as err:
        conn.rollback()
        print(f"  reset FAILED\n  {err!r}")
        sys.exit(1)

print(f"Applying {len(migrations)} migrations (one transaction per file).\n")
ok = 0
for f in migrations:
    print(f"-> {f.name}", end=" ... ", flush=True)
    sql = f.read_text(encoding="utf-8")
    try:
        cur.execute(sql)
        conn.commit()
        print("ok")
        ok += 1
    except Exception as err:
        conn.rollback()
        print(f"FAILED\n  {err!r}")
        sys.exit(1)

print(f"\nMigrations: {ok}/{len(migrations)} applied.")

if seed:
    seed_file = root / "supabase" / "seed.sql"
    print(f"\nApplying seed {seed_file.name}…", end=" ", flush=True)
    sql = seed_file.read_text(encoding="utf-8")
    try:
        cur.execute(sql)
        conn.commit()
        print("ok")
    except Exception as err:
        conn.rollback()
        print(f"FAILED\n  {err!r}")
        sys.exit(1)

cur.close()
conn.close()
print("\nDone.")
