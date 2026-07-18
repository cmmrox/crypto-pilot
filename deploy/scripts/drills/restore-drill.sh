#!/usr/bin/env bash
# Restore drill: back up, restore into a scratch DB, verify row counts match.
# An untested backup is not a backup (BSD §13 acceptance).
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; [ -f .env ] && . ./.env; set +a
SCRATCH="cryptopilot_restore_drill"

echo "[1/4] Creating fresh backup..."
scripts/backup.sh
BK=$(ls -t /tmp/cryptopilot-*.sql.gz.enc | head -1)

echo "[2/4] Recreating scratch DB ${SCRATCH}..."
docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -c "DROP DATABASE IF EXISTS ${SCRATCH};" -c "CREATE DATABASE ${SCRATCH};"

echo "[3/4] Restoring into scratch..."
scripts/restore.sh "${BK}" "${SCRATCH}"

echo "[4/4] Verifying row counts..."
SRC=$(docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc "SELECT count(*) FROM events;")
DST=$(docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d "${SCRATCH}" -tAc "SELECT count(*) FROM events;")
echo "events: source=${SRC} restored=${DST}"
docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "DROP DATABASE ${SCRATCH};" >/dev/null
[ "${SRC}" = "${DST}" ] && echo "RESTORE DRILL PASSED ✓" || { echo "RESTORE DRILL FAILED ✗"; exit 1; }
