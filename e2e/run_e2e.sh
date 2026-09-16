#!/usr/bin/env bash
# Starts the backend (8001) and a production build of the frontend (5173) against a
# throwaway database, runs the Playwright journey, then stops both servers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python}"
export MONGO_DB="${E2E_DB:-scamshield_e2e}"
export JWT_SECRET="e2e-secret-please-change-0123456789abcdef"
LOGS="$ROOT/e2e/.logs"
mkdir -p "$LOGS"
PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  "$PY" - <<EOF || true
import pymongo; pymongo.MongoClient("mongodb://127.0.0.1:27017").drop_database("$MONGO_DB")
EOF
}
trap cleanup EXIT

wait_for() {
  for _ in $(seq 1 60); do
    curl -fs "$1" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "timed out waiting for $1" >&2
  return 1
}

cd "$ROOT/backend"
"$PY" -c "import pymongo; pymongo.MongoClient('mongodb://127.0.0.1:27017').drop_database('$MONGO_DB')"
[ -f models/scamshield.joblib ] || "$PY" -m ml.train
"$PY" -m scripts.seed
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 >"$LOGS/backend.log" 2>&1 &
PIDS+=($!)

cd "$ROOT/frontend"
[ -d node_modules ] || npm install
npm run build >"$LOGS/build.log" 2>&1
node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5173 --strictPort >"$LOGS/frontend.log" 2>&1 &
PIDS+=($!)

wait_for http://127.0.0.1:8001/api/health
wait_for http://127.0.0.1:5173/

cd "$ROOT"
E2E_BASE_URL=http://127.0.0.1:5173 "$PY" -m pytest e2e/test_e2e.py -q -p no:cacheprovider "$@"
