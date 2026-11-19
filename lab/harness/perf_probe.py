# SPDX-License-Identifier: MIT
"""Speed and memory probe for whatever server is currently running.

  .venv/bin/python harness/perf_probe.py --label llama_q4_ctx64k [--base-url http://127.0.0.1:18431/v1]

For each prompt shape (our compact prompt, and the real first-turn requests captured from
Hermes in results/hermes_prompts/) it measures, 3 repetitions each:
  cold  - time to first token when nothing is cached (a random nonce is put at the very top
          of the system prompt so the whole prompt must be prefilled)
  warm  - the identical request again (prompt cache hit)
plus decode speed on a 256-token generation, and the server's memory.
"""
import argparse
import json
import statistics as st
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner  # noqa: E402
import tools  # noqa: E402

LAB = runner.LAB


def shapes():
    cfg = runner.load_config(LAB / "configs" / "raw_baseline.json")
    out = {"raw_compact_14_tools": ([{"role": "system", "content": runner.system_prompt(cfg)},
                                     {"role": "user", "content": "What's on my calendar this Friday?"}], tools.schemas("plain"))}
    for p in sorted((LAB / "results" / "hermes_prompts").glob("*.json")):
        cap = json.loads(p.read_text())
        msgs = [m for m in cap["messages"] if m["role"] == "system"] + [{"role": "user", "content": "What's on my calendar this Friday?"}]
        out["hermes_" + p.stem] = (msgs, cap["tools"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--base-url", default="http://127.0.0.1:18431/v1")
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    cfg = dict(runner.DEFAULTS, base_url=a.base_url, max_tokens=64, thinking=False)
    rows = {}
    for name, (msgs, tl) in shapes().items():
        cold, warm = [], []
        for _ in range(a.reps):
            m = [dict(msgs[0], content=f"[{uuid.uuid4().hex}]\n" + msgs[0]["content"])] + msgs[1:]
            for bucket in (cold, warm):
                r = runner.chat(cfg, m, tl, {"seed": 1})
                bucket.append(runner.perf_of(r))
        rows[name] = {
            "prompt_tokens": cold[0]["prompt_tokens"], "n_tools": len(tl),
            "cold_ttft_s": round(st.median(x["ttft_s"] for x in cold), 2),
            "cold_prefill_tps": round(st.median(x["prompt_tps"] for x in cold if x["prompt_tps"])) if cold[0]["prompt_tps"] else None,
            "warm_ttft_s": round(st.median(x["ttft_s"] for x in warm), 3),
            "warm_cached_tokens": warm[0]["cache_n"],
        }
        print(name, rows[name], flush=True)
    cfg["max_tokens"] = 256
    dec = [runner.perf_of(runner.chat(cfg, [{"role": "user", "content": "Write a 200-word story about a lighthouse keeper."}], None, {"seed": i}))
           for i in range(a.reps)]
    decode = {"decode_tps": round(st.median(x["decode_tps"] or (x["completion_tokens"] / x["wall_s"]) for x in dec), 1)}
    cfg["thinking"] = True
    decode_think = runner.perf_of(runner.chat(cfg, [{"role": "user", "content": "Write a 200-word story about a lighthouse keeper."}], None, {"seed": 1}))
    decode["decode_tps_thinking"] = round(decode_think["decode_tps"] or 0, 1)
    doc = {"label": a.label, "prompts": rows, **decode, "server_memory": runner.server_memory()}
    print(json.dumps({k: v for k, v in doc.items() if k != "prompts"}))
    (LAB / "results" / f"perf_{a.label}.json").write_text(json.dumps(doc, indent=1))


if __name__ == "__main__":
    main()
