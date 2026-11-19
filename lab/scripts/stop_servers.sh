#!/bin/bash
# SPDX-License-Identifier: MIT
# Stop every server the lab started (by pid file), then show anything still listening on lab ports.
LAB="$(cd "$(dirname "$0")/.." && pwd)"
for f in "$LAB"/run/*.pid; do
  [ -f "$f" ] || continue
  pid="$(cat "$f")"
  if kill -0 "$pid" 2>/dev/null; then kill "$pid"; for i in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done; kill -9 "$pid" 2>/dev/null || true; fi
  rm -f "$f"
done
lsof -nP -iTCP:18431 -iTCP:18432 -sTCP:LISTEN 2>/dev/null || echo "no lab ports listening"
# Hermes auto-starts a background gateway for the lab home; stop it too (by PID, never via launchd).
GP="$("$LAB/.venv/bin/python" -c "import json,sys;print(json.load(open('$LAB/hermes-home/gateway.pid'))['pid'])" 2>/dev/null)"
if [ -n "$GP" ] && ps -o command= -p "$GP" 2>/dev/null | grep -q "$LAB"; then kill "$GP"; sleep 1; kill -9 "$GP" 2>/dev/null || true; fi
pgrep -fl "llama-server|harness/proxy.py|hermes_cli|harness/mcp_server.py|mlx_lm" | grep "$LAB" || echo "no lab server processes running"
