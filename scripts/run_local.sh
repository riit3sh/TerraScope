#!/usr/bin/env bash
# Run TerraScope's UI without Docker.
#
# Starts backend-api (8000), ml-models (8002) and the Vite dev server (5173),
# and seeds one report so there is something to look at.
#
# Starts data-pipeline (8001) too, with its PostGIS snapshot archive disabled
# (DATABASE_URL unset). Evidence is still collected live from OpenStreetMap,
# Open-Elevation and the RERA seed, and the backend still stores every snapshot;
# only the second, spatial archive is skipped. Use Docker Compose for that.
#
# Analysis calls real external APIs, so it needs internet and takes ~10-40s.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
RUN_DIR="$ROOT/.local-ui-check"
mkdir -p "$RUN_DIR"
export BACKEND_STORE_PATH="$RUN_DIR/backend.sqlite3"

# Compose injects .env into each container; running bare on Windows we must load
# it ourselves, then override the paths that are container-absolute.
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi
export NOMINATIM_USER_AGENT="${NOMINATIM_USER_AGENT:-terrascope-local-dev/0.1.0}"
export RERA_SEED_PATH="$ROOT/data-pipeline/data/raw/maharera_seed.csv"
export TERRASCOPE_SATELLITE_CACHE_PATH="$RUN_DIR/satellite_cache.json"
export VALUATION_MODEL_PATH="$ROOT/valuation/artifacts/land_price_model.joblib"
# No PostGIS outside Compose; the archive disables itself and says so.
export DATABASE_URL=""

free_port() {
  local port="$1"
  local pids
  pids=$(netstat -ano 2>/dev/null | grep -E "LISTENING" | grep -E ":${port}[[:space:]]" | awk '{print $NF}' | sort -u)
  for pid in $pids; do
    [ -n "$pid" ] && taskkill //PID "$pid" //F >/dev/null 2>&1 && echo "  freed port $port (pid $pid)"
  done
}

echo "Stopping anything already on 8000/8001/8002/5173..."
for port in 8000 8001 8002 5173; do free_port "$port"; done
sleep 2

echo "Starting ml-models on :8002..."
( cd "$ROOT/ml-models" && nohup python -c "
import uvicorn
uvicorn.run('pipeline:app', host='127.0.0.1', port=8002, log_level='warning')
" > "$RUN_DIR/ml.log" 2>&1 & )

echo "Starting data-pipeline on :8001..."
# DATABASE_URL is deliberately left unset here: no PostGIS outside Compose.
( cd "$ROOT/data-pipeline" && nohup python -c "
import uvicorn
uvicorn.run('internal_api:app', host='127.0.0.1', port=8001, log_level='warning')
" > "$RUN_DIR/data-pipeline.log" 2>&1 & )

echo "Starting backend-api on :8000..."
nohup python -c "
import os, sys
root = os.path.abspath('.')
# These default to Compose hostnames (data-pipeline / ml-models), which do not
# resolve on Windows and fail with getaddrinfo. Point them at the local ports.
os.environ['DATA_PIPELINE_URL'] = 'http://127.0.0.1:8001'
os.environ['ML_MODELS_URL'] = 'http://127.0.0.1:8002'
os.environ.setdefault('BACKEND_STORE_PATH', os.path.join(root, '.local-ui-check', 'backend.sqlite3'))
sys.path[:0] = [root, os.path.join(root, 'backend-api'), os.path.join(root, 'backend-api', 'src')]
import uvicorn
uvicorn.run('terrascope_backend_api.main:app', host='127.0.0.1', port=8000, log_level='warning')
" > "$RUN_DIR/backend.log" 2>&1 &

for _ in $(seq 1 30); do
  curl -s --max-time 2 http://localhost:8000/api/v1/health >/dev/null 2>&1 && break
  sleep 1
done
curl -s --max-time 3 http://localhost:8000/api/v1/health >/dev/null 2>&1 \
  && echo "  backend-api ready" || { echo "  backend-api FAILED:"; tail -5 "$RUN_DIR/backend.log"; }

for _ in $(seq 1 30); do
  curl -s --max-time 2 http://localhost:8001/health >/dev/null 2>&1 && break
  sleep 1
done
curl -s --max-time 3 http://localhost:8001/health >/dev/null 2>&1   && echo "  data-pipeline ready" || { echo "  data-pipeline FAILED:"; tail -5 "$RUN_DIR/data-pipeline.log"; }
curl -s --max-time 3 http://localhost:8002/health >/dev/null 2>&1   && echo "  ml-models ready" || { echo "  ml-models FAILED:"; tail -5 "$RUN_DIR/ml.log"; }

if [ "$(curl -s --max-time 5 http://localhost:8000/api/v1/parcels | grep -c 'parcel_id')" = "0" ]; then
  echo "Seeding one demo report..."
  python scripts/seed_ui_demo.py >/dev/null 2>&1 && echo "  seeded" || echo "  seed failed"
fi

echo "Starting frontend on :5173..."
( cd "$ROOT/frontend" && VITE_BACKEND_API_URL=http://localhost:8000 \
  nohup npx vite --host 127.0.0.1 --port 5173 > "$RUN_DIR/frontend.log" 2>&1 & )

for _ in $(seq 1 40); do
  curl -s --max-time 2 -o /dev/null http://localhost:5173/ 2>/dev/null && break
  sleep 1
done

echo
echo "-------------------------------------------------------"
echo "  Open  http://localhost:5173"
echo
echo "  Search a place, draw a boundary, Analyze This Parcel."
echo "  Or scroll to SAVED REPORTS to reopen an earlier one."
echo
echo "  Logs: $RUN_DIR/{backend,data-pipeline,ml,frontend}.log"
echo "  Stop: bash scripts/stop_local.sh"
echo "-------------------------------------------------------"
