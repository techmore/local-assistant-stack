#!/bin/bash
# SPDX-License-Identifier: MIT
# Start the logging proxy (Hermes -> 127.0.0.1:18432 -> llama-server/mlx on $1, default 18431).
LAB="$(cd "$(dirname "$0")/.." && pwd)"
UP="${1:-18431}"
if lsof -nP -iTCP:18432 -sTCP:LISTEN >/dev/null 2>&1; then echo "port 18432 busy" >&2; exit 1; fi
nohup "$LAB/.venv/bin/python" "$LAB/harness/proxy.py" 18432 "http://127.0.0.1:$UP" > "$LAB/logs/proxy.log" 2>&1 &
echo $! > "$LAB/run/proxy.pid"; sleep 1
kill -0 "$(cat "$LAB/run/proxy.pid")" && echo "proxy ready pid=$(cat "$LAB/run/proxy.pid") -> $UP"
