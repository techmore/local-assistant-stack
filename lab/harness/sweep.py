# SPDX-License-Identifier: MIT
"""Run a list of configs back to back, starting/stopping the right server for each.

  .venv/bin/python harness/sweep.py [--runs 3] configs/a.json configs/b.json ...

Skips a config whose results file already exists (delete it to re-run).
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner  # noqa: E402

LAB = runner.LAB


def sh(*cmd, **kw):
    return subprocess.run(list(cmd), capture_output=True, text=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("configs", nargs="+")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--suite", default="", help="v1 or heldout (default: each config's own, else v1)")
    a = ap.parse_args()
    current = None
    for path in a.configs:
        cfg = runner.load_config(path, a.suite or None)
        out = runner.out_path_for(cfg)
        if out.exists() and not a.force:
            print(f"== {cfg['name']}: results exist, skipping", flush=True)
            continue
        want = json.dumps([cfg["server"], cfg["level"] == "hermes"], sort_keys=True)
        if want != current:
            print(sh(str(LAB / "scripts" / "stop_servers.sh")).stdout.strip().splitlines()[-1], flush=True)
            srv = cfg["server"]
            if srv["runtime"] == "mlx":
                r = sh(str(LAB / "scripts" / "serve_mlx.sh"), *srv.get("args", []))
            else:
                r = sh(str(LAB / "scripts" / "serve_llama.sh"), srv["quant"], *srv.get("args", []))
            print((r.stdout + r.stderr).strip(), flush=True)
            if r.returncode:
                print(f"== {cfg['name']}: server failed to start, skipping", flush=True)
                current = None
                continue
            if cfg["level"] == "hermes":
                print(sh(str(LAB / "scripts" / "serve_proxy.sh"), cfg["base_url"].rsplit(":", 1)[1].split("/")[0]).stdout.strip(), flush=True)
            current = want
        print(f"== {cfg['name']} start {time.strftime('%H:%M:%S')}", flush=True)
        subprocess.run([sys.executable, str(LAB / "harness" / "runner.py"), path, "--runs", str(a.runs), "--suite", cfg["suite"]])
    print(sh(str(LAB / "scripts" / "stop_servers.sh")).stdout.strip(), flush=True)


if __name__ == "__main__":
    main()
