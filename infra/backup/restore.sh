#!/usr/bin/env bash
#
# Restore a Postgres dump from DigitalOcean Spaces (CLAUDE.md §25.2,
# §27 step 65). Companion to pg_dump.sh.
#
# Usage:
#   restore.sh <bucket> <object_key> <dsn>
#
#   bucket      Spaces bucket name (quarrel-backups).
#   object_key  Full path inside the bucket, e.g.
#               litellm/daily/20260524T030000Z-litellm.sql.gz.age
#   dsn         Postgres DSN of the *target* database (typically a freshly
#               provisioned restore instance, NEVER production).
#
# Decrypts with the age identity at $PG_DUMP_AGE_IDENTITY (path to the
# private key file) and feeds the plain SQL to psql.
#
# This script REFUSES to run if the target DSN points at the same host
# as the production env var SUPABASE_DB_URL. We don't restore in-place;
# restores go into a side instance and traffic gets cut over manually.

set -euo pipefail

if [[ "${#}" -ne 3 ]]; then
  echo "usage: $0 <bucket> <object_key> <dsn>" >&2
  exit 64
fi

BUCKET="${1}"
OBJECT_KEY="${2}"
DSN="${3}"

: "${PG_DUMP_AGE_IDENTITY:?set PG_DUMP_AGE_IDENTITY to path of age private key file}"
: "${AWS_ACCESS_KEY_ID:?set AWS_ACCESS_KEY_ID}"
: "${AWS_SECRET_ACCESS_KEY:?set AWS_SECRET_ACCESS_KEY}"
: "${AWS_S3_ENDPOINT:?set AWS_S3_ENDPOINT}"

# Production-host guard.
if [[ -n "${SUPABASE_DB_URL:-}" ]]; then
  prod_host="$(printf '%s' "${SUPABASE_DB_URL}" | sed -E 's|^.*@([^:/?]+).*$|\1|')"
  target_host="$(printf '%s' "${DSN}" | sed -E 's|^.*@([^:/?]+).*$|\1|')"
  if [[ "${prod_host}" == "${target_host}" ]]; then
    echo "refusing to restore over production host (${prod_host})" >&2
    exit 71
  fi
fi

workdir="$(mktemp -d)"
trap 'rm -rf "${workdir}"' EXIT
filename="$(basename "${OBJECT_KEY}")"

aws s3 cp \
  --endpoint-url "${AWS_S3_ENDPOINT}" \
  --no-progress \
  "s3://${BUCKET}/${OBJECT_KEY}" \
  "${workdir}/${filename}"

age --decrypt --identity "${PG_DUMP_AGE_IDENTITY}" "${workdir}/${filename}" \
  | gunzip \
  | psql --dbname="${DSN}" --single-transaction --set ON_ERROR_STOP=on

echo "restored ${filename} → ${DSN}"
