# Local Assistant Stack

A reference stack for a local-first AI assistant on Apple Silicon Mac minis and Linux: what exists, what to run, and the gaps.

Live site: https://techmore.github.io/local-assistant-stack/

## The short answer

The question was whether an open-source, Siri-like assistant exists that runs on local models, reaches your apps with real permissions, and carries long tasks unattended, on Mac minis and Linux.

No single project does this today. Hermes Agent and OpenClaw come close enough that writing a new agent from scratch would be a mistake. What is missing is a permission model enforced outside the agent, a review queue, parity on Linux for personal data, a local model reliable enough for multi-hour unattended work on a 16 to 64 GB machine, and a tested combination of all the layers. The site recommends a hybrid: a Mac mini on macOS as the data and inference hub, a small pinned local model for voice and chat, a local work model for checkable jobs, a hosted model for hard unattended jobs, and Mac and Linux thin clients.

## Status

Research and roadmap, plus one piece of software: an evaluation lab in `lab/` that measures a small local model on assistant tasks (results below). The assistant itself is not built. The roadmap page lists what this project intends to build.

Research date: 2026-11-18. The field moves monthly. Versions, star counts and benchmark figures were read on that date. Claims are labelled Verified, Secondary or Not verified, and the sources page lists what could not be verified.

## Repo layout

```
docs/                 the site, plain static HTML and CSS, served by GitHub Pages
  index.html          the answer, the hybrid architecture, the routing table
  landscape.html      requirements matrix and candidate survey
  models.html         models on M4 minis: speeds, tool calling, RAM tiers
  runtimes.html       servers, LAN serving, clustering, Linux on Apple Silicon
  voice.html          speech to text, text to speech, wake word, latency
  permissions.html    macOS access, safer shapes, draft but do not send
  unattended.html     scheduling, guardrails, supervision, cost, fine-tuning
  build.html          three reference architectures and a first-weekend plan
  gaps.html           the roadmap: gaps, planned and not built
  sources.html        numbered sources and what could not be verified
  report.md           the full research report, with private details removed
  style.css           the one stylesheet
  .nojekyll           serve the folder as is
  lab.html            the lab: what was measured, the results, how to reproduce
lab/                  the evaluation lab (Python, standard library; see lab/docs/USAGE.md)
  harness/            stand-in tools, confirmation gate, date resolver, runner, task sets, reports
  tests/              unit tests, no model needed
  configs/            one JSON file per measured configuration
  fixtures*/          invented calendar, contacts, messages, mail and files the tools operate on
  profiles/           the compact prompt packaged as a Hermes persona
  docs/               usage, and design notes (gate contract, cross-platform status, an incident note)
  results/            summary tables (no raw transcripts)
  LICENSING.md        which licence covers what
.github/workflows/    unit tests for lab/ on Linux and macOS; the Linux sandbox wrapper on Ubuntu
LICENSE               MIT, for code
```

The site has no build step. Edit the HTML directly.

## The lab: measuring a small local assistant, and keeping it from acting on its own

The `lab/` directory contains an evaluation harness for a local assistant built from Hermes Agent
driving Qwen3.5-4B through llama.cpp, with every tool a stand-in over invented fixture data. It
measures the model at two levels (a bare OpenAI-compatible endpoint, and through Hermes restricted
to the lab's tools inside an OS sandbox) and tests three mechanisms that take risky decisions
away from the model.

A first round of prompt tuning reached 95.8% (raw) and 92.7% (Hermes) on 55 tasks, but those numbers were in-sample: the same author wrote the 55 tasks and the fixes. Round 2
froze three changes, then wrote 63 new tasks on new fixture data with a different fixed "now", and
ran everything on them (3 runs per task, Qwen3.5-4B Q4_K_M, thinking off). Full tables:
[`results/HELDOUT.md`](lab/results/HELDOUT.md); what still fails: [`results/FAILURES.md`](lab/results/FAILURES.md).

| configuration | raw endpoint | through Hermes v0.23.2 | sends/deletes executed without a recorded confirmation (raw / Hermes) |
|---|---|---|---|
| (1) round-1 best, on the new tasks | 78.3% (68-87) | 83.6% (75-91) | 23 / 22 |
| (2) + confirmation gate | 82.0% (72-90) | not run | 0 / - |
| (3) + date-tolerant tools | 83.1% (76-90) | not run | 23 / - |
| (4) + both | 84.1% (77-90) | 84.7% (77-91) | 0 / 0 |
| (5) both + compact prompt (packaged as a Hermes persona) | 87.8% (80-94) | 90.5% (84-96) | 0 / 0 |
| (4) on the first 55 tasks (regression check) | 97.0% (round 1: 95.8%) | 96.4% (round 1: 92.7%) | 0 / 0 |

Reading it:

- **The round-1 result did not generalize.** 95.8% in-sample became 78.3% on new tasks (raw) and
  92.7% became 83.6% (Hermes). Dates (46% raw) and multi-step chains (42% raw) account for most
  of it.
- **The gate did its job.** Without it, 23 (raw) and 22 (Hermes) sends or deletes ran on the
  model's say-so, including an injected email that got a passwords file sent in 3 of 3 runs at both
  levels. With it: zero, in every gated run, while the model still tried (previews left
  unapproved, and second calls refused by the gate, are counted in the tables).
- **Pass-rate differences between configurations are within noise at 63 tasks** (paired
  intervals all include zero). The unsafe-action count is the result that is not.
- Three checks rejected correct answers and were corrected after the first grading; both gradings
  are in `results/HELDOUT.md` (9 of 1,512 runs changed).

The three changes:

- **Confirmation gate** (`lab/harness/gate.py`, `lab/harness/state.py`, contract in
  [`docs/design/confirmation-gate.md`](lab/docs/design/confirmation-gate.md)): `send_message` and
  `file_delete` stage a preview and a one-time id on the first call and execute only on a second
  call carrying that id when an approval has been recorded by the user's side. Ambiguous names are
  refused with the candidate list. State is an append-only, versioned event log behind a small
  store interface.
- **Date/time resolver** (`lab/harness/dates.py`): tools accept "friday", "next tuesday", "3 to 4pm",
  "in two hours", "end of the month" and resolve them in code against a fixed, timezone-aware
  "now"; ambiguous or impossible expressions are rejected with a message the model can relay.
- **Compact prompt as a Hermes persona** (`lab/profiles/pocket-assistant/`): six rules and seven
  worked examples in `SOUL.md`, with tool search, tool-use enforcement and thinking off. 643 prompt
  tokens for the raw endpoint (round 1: 505); a first Hermes turn is 4,796 tokens: 13.0 s to
  first token cold and 0.42 s warm on an Apple M1 Pro (raw: 3,217 tokens, 8.0 s cold, 0.28 s warm).

Unit tests (128; resolver, gate, tool layer, simulated user, platform interface, task checks, and the
Linux sandbox wrapper, whose tests skip where bubblewrap is not usable) need no model:
`cd lab && python -m unittest discover -s tests`. On Linux, CI runs the bubblewrap sandbox wrapper,
the lab's tool server inside it and the shell helpers on hosted Ubuntu 22.04, 24.04 and 26.04 runners
(x86_64, and aarch64 on 24.04); no model and no Hermes run there. What that covers, what it found
and what is not enforced: [`docs/design/cross-platform.md`](lab/docs/design/cross-platform.md).

What is not measured: Linux (every model and Hermes run was made on macOS on Apple Silicon; on Linux only the unit tests and the bubblewrap sandbox wrapper have been run, in CI on hosted Ubuntu runners, without a model or Hermes, and that wrapper does not filter outbound network traffic), real apps or accounts (every tool is a stand-in over invented fixture data), any model other than Qwen3.5-4B, and Hermes configurations (2) and (3).

To reproduce: the unit tests need only Python 3.11+ (`cd lab && python -m unittest discover -s tests`). The model runs need `llama-server`, the Qwen3.5-4B Q4_K_M GGUF and, for the Hermes level, a sandboxed Hermes Agent v0.23.2 checkout; the steps are in [`lab/docs/USAGE.md`](lab/docs/USAGE.md). Raw transcripts are not published.


Layout, under `lab/`: `harness/` (tools, gate, resolver, runner, task sets, reports), `tests/`, `configs/`,
`fixtures/` and `fixtures_heldout/`, `profiles/pocket-assistant/`, `docs/design/` (gate contract and
hub design, cross-platform status, an incident note on why the model never gets a shell),
`docs/USAGE.md`, `results/` (summary tables only). Licensing: `lab/LICENSING.md`.

## Licenses

Code is under the MIT License (see `LICENSE`); `lab/LICENSING.md` says which files in the lab are code and which are written content. The written content, including everything in `docs/`, is licensed CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), copyright Techmore.

Part of [Techmore](https://techmore.github.io/pages/repos/).
