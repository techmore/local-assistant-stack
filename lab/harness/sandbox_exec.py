# SPDX-License-Identifier: MIT
"""Run a command inside the lab sandbox, or refuse. The only way the lab starts Hermes.

  python harness/sandbox_exec.py --mode eval -- <command> [args...]
  python harness/sandbox_exec.py --mode eval --prepare        # (re)generate the profile only

Exits 78 without running anything when no sandbox wrapper is available (fail closed).
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import platforms  # noqa: E402

LAB = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["guard", "eval"], default="guard")
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    try:
        sb = platforms.get_sandbox()
    except platforms.SandboxUnavailable as e:
        sys.stderr.write(f"sandbox unavailable, refusing to run: {e}\n")
        sys.exit(78)
    if a.prepare:
        print(sb.prepare(a.mode, LAB))
        return
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not cmd:
        ap.error("no command given")
    argv = sb.wrap(cmd, a.mode, LAB)
    os.execvp(argv[0], argv)


if __name__ == "__main__":
    main()
