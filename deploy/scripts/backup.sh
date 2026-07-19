#!/usr/bin/env bash
# Nightly encrypted pg_dump → object storage (BSD §15).
# Usage: backup.sh  (reads deploy/.env). Requires: docker, openssl, python3, aws (optional).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a

TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="/tmp/cryptopilot-${TS}.sql.gz.enc"
MAC="${OUT}.mac"
: "${CP_MASTER_KEY:?MASTER_KEY required for backup encryption}"
: "${CP_DB_NETWORK:?CP_DB_NETWORK required}"
: "${CP_DB_HOST:?CP_DB_HOST required}"
: "${POSTGRES_USER:?POSTGRES_USER required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD required}"
: "${POSTGRES_DB:?POSTGRES_DB required}"
POSTGRES_IMAGE="${CP_POSTGRES_IMAGE:-postgres:16-alpine}"
export PGPASSWORD="${POSTGRES_PASSWORD}"
umask 077
trap 'rm -f "${OUT}" "${MAC}"' ERR HUP INT TERM

echo "Dumping database..."
docker run --rm --network "${CP_DB_NETWORK}" \
  -e PGPASSWORD \
  "${POSTGRES_IMAGE}" \
  pg_dump --no-owner --no-privileges \
    -h "${CP_DB_HOST}" -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
  | gzip \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 \
      -pass env:CP_MASTER_KEY -out "${OUT}"
# OpenSSL enc does not provide AEAD. Authenticate the complete salted
# ciphertext with a derived HMAC key. The helper reads CP_MASTER_KEY only from
# the environment, so neither the master key nor the MAC key enters argv.
python3 scripts/backup_auth.py create "${OUT}" "${MAC}"
echo "Encrypted backup written: ${OUT} ($(du -h "${OUT}" | cut -f1))"

# Upload if a bucket is configured (S3-compatible). No-op locally.
if [ -n "${CP_BACKUP_BUCKET:-}" ]; then
  echo "Uploading to ${CP_BACKUP_BUCKET}..."
  aws s3 cp "${MAC}" "${CP_BACKUP_BUCKET}/$(basename "${MAC}")"
  aws s3 cp "${OUT}" "${CP_BACKUP_BUCKET}/$(basename "${OUT}")"
fi
# Local drill artifacts are retained briefly; production's backup service
# removes each local copy immediately after both uploads succeed.
find /tmp -maxdepth 1 -type f \
  \( -name 'cryptopilot-*.sql.gz.enc' -o -name 'cryptopilot-*.sql.gz.enc.mac' \) \
  -mtime +7 -delete
trap - ERR HUP INT TERM
echo "Backup complete."
