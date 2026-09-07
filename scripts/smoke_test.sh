#!/usr/bin/env bash
set -u

check_service() {
  local name="$1"
  local url="$2"
  if ! curl --fail --silent --show-error --max-time 10 "$url" >/dev/null; then
    echo "SMOKE TEST FAILED: ${name} is down or unhealthy (${url})" >&2
    exit 1
  fi
  echo "OK: ${name}"
}

check_service "backend-api" "http://localhost:8000/api/v1/health"
check_service "data-pipeline" "http://localhost:8001/health"
check_service "ml-models" "http://localhost:8002/health"
check_service "frontend" "http://localhost:5173/"
echo "SMOKE TEST PASSED: all local TerraScope services are reachable."
