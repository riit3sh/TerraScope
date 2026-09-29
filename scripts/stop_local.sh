#!/usr/bin/env bash
# Stop the local (non-Docker) TerraScope services started by run_local.sh.
set -uo pipefail

for port in 8000 8001 8002 5173; do
  pids=$(netstat -ano 2>/dev/null | grep -E "LISTENING" | grep -E ":${port}[[:space:]]" | awk '{print $NF}' | sort -u)
  for pid in $pids; do
    [ -n "$pid" ] && taskkill //PID "$pid" //F >/dev/null 2>&1 && echo "stopped port $port (pid $pid)"
  done
done
echo "done"
