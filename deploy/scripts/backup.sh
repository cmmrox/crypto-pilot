#!/usr/bin/env bash
# Nightly encrypted pg_dump → object storage (BSD §15).
# Usage: backup.sh  (reads deploy/.env). Requires: docker compose, openssl, aws/rclone (optional).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a

TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="/tmp/cryptopilot-${TS}.sql.gz.enc"
KEY="${CP_MASTER_KEY:?MASTER_KEY required for backup encryption}"

echo "Dumping database..."
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
  | gzip \
  | openssl enc -aes-256-cbc -pbkdf2 -pass "pass:${KEY}" -out "${OUT}"
echo "Encrypted backup written: ${OUT} ($(du -h "${OUT}" | cut -f1))"

# Upload if a bucket is configured (S3-compatible). No-op locally.
if [ -n "${CP_BACKUP_BUCKET:-}" ]; then
  echo "Uploading to ${CP_BACKUP_BUCKET}..."
  aws s3 cp "${OUT}" "${CP_BACKUP_BUCKET}/$(basename "${OUT}")"
fi
echo "Backup complete."
