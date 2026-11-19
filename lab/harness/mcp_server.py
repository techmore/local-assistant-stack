# SPDX-License-Identifier: MIT
"""Minimal MCP stdio server (standard library only) exposing the lab's fixture tools.

Hermes launches this per session. Per-task settings come from run/mcp_task.json
(schema variant, tool subset, forced tool results); every call is appended to
run/mcp_calls.jsonl so the runner can grade the session afterwards.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import state  # noqa: E402
import tools  # noqa: E402

RUN = Path(__file__).resolve().parent.parent / "run"


def settings():
    try:
        return json.loads((RUN / "mcp_task.json").read_text())
    except Exception:
        return {}


def make_world(cfg):
    # Pending confirmations live in an event log shared with the approver (the harness, standing in
    # for the user's UI). This process can stage and redeem; it never writes decisions.
    return tools.World(cfg.get("overrides"), fixture_name=cfg.get("fixture", "v1"), gate=cfg.get("gate", False),
                       nl_dates=cfg.get("nl_dates", False), store=state.JsonlStore(RUN / "gate_events.jsonl"),
                       device_id="hermes-tools", v3=cfg.get("v3", False))


def main():
    cfg = settings()
    world = make_world(cfg)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        mid, method = msg.get("id"), msg.get("method")
        if mid is None:
            continue  # notification
        if method == "initialize":
            res = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2024-11-05"),
                   "capabilities": {"tools": {}}, "serverInfo": {"name": "lab", "version": "1"}}
        elif method == "tools/list":
            res = {"tools": [{"name": s["function"]["name"], "description": s["function"]["description"],
                              "inputSchema": s["function"]["parameters"]}
                             for s in tools.schemas(cfg.get("variant", "plain"), cfg.get("names"),
                                                    gate=cfg.get("gate", False), nl_dates=cfg.get("nl_dates", False),
                                                    v3=cfg.get("v3", False))]}
        elif method == "tools/call":
            p = msg.get("params", {})
            # Hermes keeps this process alive across `hermes chat` invocations (it lives in the
            # gateway), so start a fresh fixture world whenever the runner announces a new task.
            fresh = settings()
            if fresh.get("nonce") != cfg.get("nonce"):
                cfg = fresh
                world = make_world(cfg)
            result = world.call(p.get("name"), p.get("arguments") or {})
            with open(RUN / "mcp_calls.jsonl", "a") as f:
                f.write(json.dumps(world.calls[-1]) + "\n")
            tmp = RUN / "mcp_world.json.tmp"
            tmp.write_text(json.dumps(world.snapshot()))
            tmp.replace(RUN / "mcp_world.json")
            res = {"content": [{"type": "text", "text": json.dumps(result)}], "isError": False}
        elif method == "ping":
            res = {}
        else:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": res}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
