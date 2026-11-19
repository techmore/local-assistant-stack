# pocket-assistant: the compact assistant persona, packaged as a Hermes profile distribution

Hermes Agent v0.23 packages a reusable agent as a *profile distribution*: a directory (normally a
git repository) with `distribution.yaml`, `SOUL.md`, `config.yaml` and optional skills, installed
with `hermes profile install <repo>` and updated with `hermes profile update`.

| file | role |
|---|---|
| `SOUL.md` | the whole prompt: one identity line, six rules, seven worked examples. Hermes puts `SOUL.md` in slot 1 of its system prompt in place of its stock identity, so nothing goes in `agent.system_prompt`. |
| `config.yaml` | tool search off, tool-use enforcement off, thinking off, 64K context, the tool server under `mcp_servers.lab` |
| `distribution.yaml` | manifest |

Run it with the lab toolset only: `hermes -p pocket-assistant chat -t lab`. Do not give a 4B model
Hermes' terminal, file, browser or computer-use toolsets (see the incident note in `docs/`).

Things the profile cannot set, because Hermes v0.23 has no setting for them:

- **Generation cap.** Hermes no longer sends or reads `max_tokens`. Cap at the endpoint: start
  `llama-server` with `-n 2048`, or put `harness/proxy.py` in front of it (it adds `max_tokens`
  to every request). Without a cap a repetition loop runs until the context is full.
- **Thinking off for Qwen.** `agent.reasoning_effort: none` is sent as a reasoning field; for a
  llama.cpp endpoint the reliable switch is `chat_template_kwargs.enable_thinking=false`, which the
  proxy also adds.
- **Today's date.** The persona contains no dates. The tools resolve dates against their own clock;
  the harness adds a one-line "(Context: today is ...)" prefix to the user message.

The examples name tools as `mcp__lab__<tool>` because Hermes prefixes MCP tools with the server
name; keep the server called `lab` or edit the examples.

`SOUL.md` is also the single source for the raw-endpoint prompt (`rules2` and `fewshot2` in
`harness/runner.py` are read from it), so the two levels cannot drift apart.

`SOUL-v3.md` is the third-round prompt (eight examples, written for the `"v3": true` tools). It was
measured against `SOUL.md` on a new task set and was not better (see `results/THIRD-FAILURES.md`),
so `SOUL.md` remains the packaged persona.
