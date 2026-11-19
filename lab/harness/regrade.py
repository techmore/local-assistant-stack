# SPDX-License-Identifier: MIT
"""Re-apply the current checks in tasks.py to stored results (no model calls).

  .venv/bin/python harness/regrade.py            # all results/*.json

The fixture world is rebuilt by replaying each run's recorded tool calls, which is
deterministic. Use after changing a check so every config is graded by the same rules.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks as tasks_mod  # noqa: E402
import tools  # noqa: E402

import runner  # noqa: E402

RES = Path(__file__).resolve().parent.parent / "results"
ap_dirs = [(RES, "v1"), (RES / "heldout", "heldout")]

for d_, suite in ap_dirs:
    if not d_.exists():
        continue
    import importlib
    tasks_mod = importlib.import_module(runner.SUITES[suite]["tasks"])
    for p in sorted(d_.glob("*.json")):
        d = json.loads(p.read_text())
        if "results" not in d or "config" not in d:
            continue
        changed = 0
        for row in d["results"]:
            t = tasks_mod.BY_ID[row["id"]]
            for x in row["runs"]:
                if x.get("fail_cat") == "harness_or_server_error":
                    continue
                others = x.get("other_tool_calls") or []
                if "snapshot" in x:  # new format: full call results and end state are stored
                    cl = x["calls"]
                    world = runner.Snap(x["snapshot"])
                else:  # first-benchmark format: rebuild the world by replaying the calls
                    w = tools.World(t.get("overrides"))
                    for c in x["calls"]:
                        if c["name"] in tools.TOOL_NAMES:
                            w.call(c["name"], c["args"])
                        else:
                            w.calls.append({"name": c["name"], "args": c["args"], "norm": {}, "result": {"error": c.get("error") or "unavailable"}})
                    cl, world = w.calls, runner.Snap(w.snapshot())
                run = {"calls": cl, "final": x["final"], "finals": [tn.get("final", "") for tn in x.get("turns", [])] or [x["final"]],
                       "turns": x.get("turns", []), "world": world, "unsafe": x.get("unsafe", []),
                       "n_tool_calls": len(cl) + len(others), "tool_names": [c["name"] for c in cl] + others}
                ok, cat, detail = tasks_mod.grade(t, run)
                if ok != x["pass"] or cat != x["fail_cat"]:
                    changed += 1
                    x.setdefault("first_grade", {"pass": x["pass"], "fail_cat": x["fail_cat"]})
                    x["pass"], x["fail_cat"], x["detail"] = ok, cat, detail
            row["pass_rate"] = sum(x["pass"] for x in row["runs"]) / len(row["runs"])
        if changed and "--dry" not in sys.argv:
            d["regraded"] = True
            p.write_text(json.dumps(d, indent=1))
        total = sum(x["pass"] for r in d["results"] for x in r["runs"])
        n = sum(len(r["runs"]) for r in d["results"])
        print(f"{suite:8s} {p.name:40s} {total}/{n}  ({changed} runs changed)")
