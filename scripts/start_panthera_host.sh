#!/usr/bin/env bash
set -Eeuo pipefail

MODE="live"
PORT="5000"
ROOT="${PANTHERA_HOST_ROOT:?Set PANTHERA_HOST_ROOT to the cloned Panthera-HT_Host directory}"
PYTHON="${PANTHERA_PYTHON:-python3}"
PID_FILE="/tmp/panthera-host.pid"
LOG_FILE="/tmp/panthera-host.log"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo) MODE="demo"; shift ;;
    --live) MODE="live"; shift ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "Usage: $0 [--live|--demo] [--port PORT]" >&2; exit 2 ;;
  esac
done

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Panthera Host already running with PID $(cat "$PID_FILE")"
  exit 0
fi

APP="$ROOT/Panthera_digital_twin-main/backend/app.py"
CONFIG="$ROOT/Panthera_digital_twin-main/robot_param/Follower.yaml"
ARGS=("$APP" --config "$CONFIG" --port "$PORT")
[[ "$MODE" == "demo" ]] && ARGS+=(--demo)

nohup "$PYTHON" "${ARGS[@]}" >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
sleep 2
if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Panthera Host failed to start; see $LOG_FILE" >&2
  exit 1
fi
echo "Panthera Host started in $MODE mode on 0.0.0.0:$PORT (PID $(cat "$PID_FILE"))"
echo "Log: $LOG_FILE"
