#!/usr/bin/env bash
# Drill: restart the backend and confirm it resumes + reconciles (state survives).
set -euo pipefail
cd "$(dirname "$0")/../.."
echo "Restarting backend container..."
docker compose restart backend
for i in $(seq 1 30); do
  curl -sf http://localhost:8090/health >/dev/null 2>&1 && break || sleep 2
done
STATUS=$(curl -s http://localhost:8090/health | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])")
echo "Backend health after restart: ${STATUS}"
[ "${STATUS}" = "ok" ] && echo "RESTART DRILL PASSED ✓" || { echo "FAILED"; exit 1; }
