#!/usr/bin/env bash
# Restore drill: back up, restore into a scratch DB, verify row counts match.
# An untested backup is not a backup (BSD §13 acceptance).
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; [ -f .env ] && . ./.env; set +a
SCRATCH="cryptopilot_restore_drill"
: "${CP_DB_NETWORK:?CP_DB_NETWORK required}"
: "${CP_DB_HOST:?CP_DB_HOST required}"
: "${POSTGRES_USER:?POSTGRES_USER required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD required}"
: "${POSTGRES_DB:?POSTGRES_DB required}"
POSTGRES_IMAGE="${CP_POSTGRES_IMAGE:-postgres:16-alpine}"
export PGPASSWORD="${POSTGRES_PASSWORD}"

db_psql() {
  docker run --rm --network "${CP_DB_NETWORK}" \
    -e PGPASSWORD \
    "${POSTGRES_IMAGE}" \
    psql -v ON_ERROR_STOP=1 \
      -h "${CP_DB_HOST}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" "$@"
}

cleanup() {
  db_psql -c "DROP DATABASE IF EXISTS ${SCRATCH};" >/dev/null || true
}
trap cleanup EXIT

echo "[1/4] Creating fresh backup..."
scripts/backup.sh
BK=$(ls -t /tmp/cryptopilot-*.sql.gz.enc | head -1)

echo "[2/4] Recreating scratch DB ${SCRATCH}..."
db_psql \
  -c "DROP DATABASE IF EXISTS ${SCRATCH};" -c "CREATE DATABASE ${SCRATCH};"

echo "[3/4] Restoring into scratch..."
scripts/restore.sh "${BK}" "${SCRATCH}"

echo "[4/4] Verifying row counts..."
SRC=$(db_psql -tAc "SELECT count(*) FROM events;")
DST=$(docker run --rm --network "${CP_DB_NETWORK}" \
  -e PGPASSWORD \
  "${POSTGRES_IMAGE}" \
  psql -v ON_ERROR_STOP=1 \
    -h "${CP_DB_HOST}" -U "${POSTGRES_USER}" -d "${SCRATCH}" \
    -tAc "SELECT count(*) FROM events;")
echo "events: source=${SRC} restored=${DST}"
if [ "${SRC}" != "${DST}" ]; then
  echo "RESTORE DRILL FAILED ✗"
  exit 1
fi
echo "RESTORE DRILL PASSED ✓"
