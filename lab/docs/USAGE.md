<!-- Licence: CC BY 4.0 -->
# Running the lab

All paths and commands below are relative to this `lab/` directory.

Everything runs locally. No hosted API is called and no key for any service is used.

## Unit tests (no model needed)

```bash
python -m unittest discover -s tests -v
```

Python 3.11 or newer, standard library only.

## Setup for model runs

```bash
# 1. harness virtualenv
python3 -m venv .venv && .venv/bin/pip install requests

# 2. weights (stored inside the lab directory)
export HF_HOME=$PWD/.hf
hf download unsloth/Qwen3.5-4B-GGUF Qwen3.5-4B-Q4_K_M.gguf --local-dir models/gguf

# 3. a local API key for the servers (never leaves the machine)
mkdir -p run logs && python3 -c "import secrets;print('lab-'+secrets.token_hex(16))" > run/api_key

# 4. Hermes Agent, isolated (only for level "hermes")
git clone --depth 1 --branch v0.23.2 https://github.com/NousResearch/hermes-agent.git hermes-agent
mkdir -p hermes-home && (cd hermes-agent && ../bin/guard bash ./setup-hermes.sh --runtime-only)
bin/hermes --version
cp -R hermes-home/skills run/skills.pristine
```

`llama-server` (llama.cpp) must be on `PATH`. Servers bind 127.0.0.1 only (18431 model, 18432 proxy).

## Running

```bash
# one configuration on one suite (start the server first)
scripts/serve_llama.sh q4
.venv/bin/python harness/runner.py configs/raw_gate_dates.json --suite heldout --runs 3
scripts/stop_servers.sh

# several configurations; servers are started and stopped for you; existing results are skipped
.venv/bin/python harness/sweep.py --suite heldout configs/raw_best.json configs/raw_gate_dates.json

# tables
.venv/bin/python harness/report_heldout.py      # results/HELDOUT.md
.venv/bin/python harness/report.py              # results/SUMMARY.md (first suite)

# re-apply the checks to stored runs without calling the model
.venv/bin/python harness/regrade.py
```

Suites: `v1` (55 tasks, `harness/tasks.py`, `fixtures/`) and `heldout` (63 tasks,
`harness/tasks_heldout.py`, `fixtures_heldout/`).

A configuration is a JSON overlay on the defaults at the top of `harness/runner.py`. The switches
added in the second round: `"gate": true` (confirmation gate and ambiguity surfacing),
`"nl_dates": true` (date/time-tolerant tools), `"system": ["base", "rules2", "fewshot2"]` (the
compact prompt, read from `profiles/pocket-assistant/SOUL.md`), and for Hermes `"hermes_soul"`
(install that persona as `SOUL.md`).

## Safety rules the harness keeps

- Hermes is only ever started through `bin/hermes`, which wraps it in an OS sandbox and exits
  without starting it if no sandbox is available.
- Evaluation runs give the model the stand-in tools only (`-t lab`): never a terminal, file,
  browser or computer-use tool.
- All tools are stand-ins over fixture files. Nothing reads a real calendar, message store, mail
  account, contact list or note.
