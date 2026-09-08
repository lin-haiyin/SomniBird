#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PANTHERA_PYTHON:-python3}"
PIDFILE="/tmp/panthera-scene-api.pid"
LOGFILE="/tmp/panthera-scene-api.log"
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "scene API already running: $(cat "$PIDFILE")"
  exit 0
fi
export PANTHERA_PYTHON="$PYTHON"
nohup "$PYTHON" "$ROOT/service/http_api.py" >>"$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
echo "scene API started: $(cat "$PIDFILE") on 0.0.0.0:8000"
