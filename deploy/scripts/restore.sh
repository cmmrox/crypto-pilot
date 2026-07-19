#!/usr/bin/env bash
# Restore an encrypted backup into a target database.
# Usage: restore.sh <encrypted-backup-file> [target_db]
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
FILE="${1:?usage: restore.sh <backup.sql.gz.enc> [target_db]}"
TARGET="${2:-${POSTGRES_DB}}"
: "${CP_MASTER_KEY:?MASTER_KEY required}"
: "${CP_DB_NETWORK:?CP_DB_NETWORK required}"
: "${CP_DB_HOST:?CP_DB_HOST required}"
: "${POSTGRES_USER:?POSTGRES_USER required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD required}"
POSTGRES_IMAGE="${CP_POSTGRES_IMAGE:-postgres:16-alpine}"
export PGPASSWORD="${POSTGRES_PASSWORD}"
MAC="${FILE}.mac"

if [ ! -f "${MAC}" ]; then
  echo "Restore refused: authentication file missing (${MAC})." >&2
  exit 1
fi
python3 scripts/backup_auth.py verify "${FILE}" "${MAC}"

echo "Restoring ${FILE} → ${TARGET}..."
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
  -pass env:CP_MASTER_KEY -in "${FILE}" \
  | gunzip \
  | docker run --rm -i --network "${CP_DB_NETWORK}" \
      -e PGPASSWORD \
      "${POSTGRES_IMAGE}" \
      psql -v ON_ERROR_STOP=1 \
        -h "${CP_DB_HOST}" -U "${POSTGRES_USER}" -d "${TARGET}"
echo "Restore complete."
