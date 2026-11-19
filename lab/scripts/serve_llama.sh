#!/bin/bash
# SPDX-License-Identifier: MIT
# Start llama-server for the lab. Usage: scripts/serve_llama.sh [q4|q8] [extra llama-server flags...]
# Binds 127.0.0.1 only. PID goes to run/llama.pid, log to logs/llama-server.log.
set -euo pipefail
LAB="$(cd "$(dirname "$0")/.." && pwd)"
QUANT="${1:-q4}"; shift || true
case "$QUANT" in
  q4) MODEL="$LAB/models/gguf/Qwen3.5-4B-Q4_K_M.gguf" ;;
  q8) MODEL="$LAB/models/gguf/Qwen3.5-4B-Q8_0.gguf" ;;
  *) echo "unknown quant $QUANT" >&2; exit 2 ;;
esac
PORT="${LAB_PORT:-18431}"
CTX="${LAB_CTX:-65536}"
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then echo "port $PORT busy" >&2; exit 1; fi
nohup llama-server -m "$MODEL" --alias "qwen3.5-4b-$QUANT" \
  --host 127.0.0.1 --port "$PORT" --api-key-file "$LAB/run/api_key" \
  -c "$CTX" -np "${LAB_SLOTS:-1}" -ngl 99 --jinja --cache-prompt --metrics --no-webui "$@" \
  > "$LAB/logs/llama-server.log" 2>&1 &
echo $! > "$LAB/run/llama.pid"
for _ in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then echo "ready pid=$(cat "$LAB/run/llama.pid") port=$PORT model=$QUANT"; exit 0; fi
  kill -0 "$(cat "$LAB/run/llama.pid")" 2>/dev/null || { echo "server died" >&2; tail -20 "$LAB/logs/llama-server.log" >&2; exit 1; }
  sleep 1
done
echo "timeout waiting for server" >&2; exit 1
