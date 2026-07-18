#!/usr/bin/env bash
# Restore an encrypted backup into a target database.
# Usage: restore.sh <encrypted-backup-file> [target_db]
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
FILE="${1:?usage: restore.sh <backup.sql.gz.enc> [target_db]}"
TARGET="${2:-${POSTGRES_DB}}"
KEY="${CP_MASTER_KEY:?MASTER_KEY required}"

echo "Restoring ${FILE} → ${TARGET}..."
openssl enc -d -aes-256-cbc -pbkdf2 -pass "pass:${KEY}" -in "${FILE}" \
  | gunzip \
  | docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d "${TARGET}"
echo "Restore complete."
