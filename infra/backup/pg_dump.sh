#!/usr/bin/env bash
#
# Generic Postgres → DigitalOcean Spaces backup (CLAUDE.md §25.1, §27 step 65).
#
# Usage:
#   pg_dump.sh <dsn> <bucket> <prefix>
#
#   dsn      Full Postgres connection string, e.g.
#            postgres://user:pass@host:5432/dbname
#   bucket   Spaces bucket name, e.g. quarrel-backups
#   prefix   Path under the bucket, e.g. litellm/daily
#
# Outputs a gzipped, age-encrypted dump named
# YYYYMMDDTHHMMSSZ-<dbname>.sql.gz.age and uploads to
# s3://<bucket>/<prefix>/<filename>.
#
# Requirements on the droplet:
#   - postgresql-client (for pg_dump)
#   - age (preferred) or gpg as the encryption tool
#   - s3cmd or aws CLI configured for the DO Spaces endpoint
#
# Credentials:
#   - PG_DUMP_AGE_RECIPIENT: age public key (X25519). Required for age path.
#   - AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY: Spaces credentials.
#   - AWS_REGION + AWS_S3_ENDPOINT: Spaces region (nyc3, fra1, ...) and the
#     matching endpoint URL (https://<region>.digitaloceanspaces.com).
#
# Exits non-zero on any failure so cron's MAILTO catches it.

set -euo pipefail

if [[ "${#}" -ne 3 ]]; then
  echo "usage: $0 <dsn> <bucket> <prefix>" >&2
  exit 64
fi

DSN="${1}"
BUCKET="${2}"
PREFIX="${3}"

: "${PG_DUMP_AGE_RECIPIENT:?set PG_DUMP_AGE_RECIPIENT to the age public key}"
: "${AWS_ACCESS_KEY_ID:?set AWS_ACCESS_KEY_ID}"
: "${AWS_SECRET_ACCESS_KEY:?set AWS_SECRET_ACCESS_KEY}"
: "${AWS_S3_ENDPOINT:?set AWS_S3_ENDPOINT (e.g. https://nyc3.digitaloceanspaces.com)}"

dbname="$(printf '%s' "${DSN}" | sed -E 's|^.*/([^/?]+)(\?.*)?$|\1|')"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
filename="${timestamp}-${dbname}.sql.gz.age"
workdir="$(mktemp -d)"
trap 'rm -rf "${workdir}"' EXIT

# pg_dump with --no-owner so the dump restores cleanly into a fresh DB,
# and --no-acl so role grants don't bleed across environments.
pg_dump \
  --dbname="${DSN}" \
  --format=plain \
  --no-owner \
  --no-acl \
  --quote-all-identifiers \
  | gzip --best \
  | age --recipient "${PG_DUMP_AGE_RECIPIENT}" \
  > "${workdir}/${filename}"

bytes="$(stat -c %s "${workdir}/${filename}")"
echo "dumped ${dbname} → ${filename} (${bytes} bytes)"

# Upload via aws CLI configured for DO Spaces.
aws s3 cp \
  --endpoint-url "${AWS_S3_ENDPOINT}" \
  --acl private \
  --no-progress \
  "${workdir}/${filename}" \
  "s3://${BUCKET}/${PREFIX}/${filename}"

echo "uploaded s3://${BUCKET}/${PREFIX}/${filename}"
