# Local and offline AI assistants on M4 Mac minis and Linux: state of play, 2026-11-18

This is the public copy of the report. Sections that described private machines and private repositories were removed, and the build plan was rewritten as a generic one.

Research date: 2026-11-18. Repo statistics (stars, license, last push, latest release) were read from the GitHub API on that date. Model listings were read from the Hugging Face API on that date. Source numbers in square brackets refer to the list at the end.

How to read the confidence labels:

- **Verified**: read today from a primary source (repo, release notes, project docs, vendor page, paper).
- **Secondary**: from a blog, index or news site. Treated as directional.
- **Not verified**: I could not confirm it today. Stated so in place.

## Short answer

No single open-source project is a complete "open-source Siri with agency" on both macOS and Linux today. Two projects come close enough that building a new agent from scratch would be a mistake:

- **Hermes Agent** (Nous Research, MIT) is the closest match to the brief. It has chat, a voice mode, an on-device wake word, a managed local llama.cpp runtime, a durable cron scheduler, a task board, persistent goals, memory, macOS skills for iMessage, Reminders and Notes, and desktop apps on macOS, Windows and Linux [1][2][3][4][5].
- **OpenClaw** (OpenClaw Foundation, MIT) is the other. It has a macOS companion app that brokers system permissions and voice wake, more than 20 messaging channels including iMessage, and optional Docker sandboxing [6][7][8].

What neither has, and what nothing else has either:

1. A real per-app, per-action permission model enforced by the operating system rather than by the agent's own allowlists. On macOS the practical grant for Messages and Mail data is still Full Disk Access, which Apple itself is now restricting because of AI agents [9][10].
2. Parity on Linux for personal data. Calendar, reminders, notes and messages on Linux are reachable only through scattered community bridges with unclear permission boundaries [11].
3. A local model that is reliable enough to run multi-hour unattended work on a 16 to 64 GB machine. The harnesses are ready; the models that fit are not [12][13][14].
4. A tested, documented combination of all the layers (model, runtime, voice, integrations, scheduler, guardrails) for Apple Silicon minis plus Linux clients.

The gap is the integration, the permission model, the review queue and the Linux side. That is a legitimate project and site. Section 7 lists the gaps precisely.

A note on "Hermes underneath": there are two different things called Hermes. The Hermes **model** line has not had a release since Hermes 4.3 36B in November 2025 [15]. The newest Nous model is Arete-27B (2026-11-06), a post-trained Qwen3.8-27B that is not a Hermes release and is not tuned for tool calling [16]. Hermes **Agent** is the harness and is very active (v0.23.2 on 2026-11-16) [1]. Today, "Hermes underneath" should mean Hermes Agent running a Qwen or Gemma model, not a Hermes model.

---

## 1. Is there a single project? Survey of candidates

### 1.1 Requirements matrix

Legend: Y = present and documented, P = partial or through plugins, N = absent, ? = not verified today.

| Project | Voice in/out | Wake word | Local models | Apple app access (Mail, Messages, Calendar, Reminders, Notes) | Linux personal data | Permission model | Scheduler / long tasks | macOS | Linux | Fully offline possible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hermes Agent | Y | Y (on-device) | Y (managed llama.cpp, any OpenAI-compatible endpoint) | P (skills wrapping `imsg`, `remindctl`, Notes; email by IMAP/SMTP or Himalaya; no Calendar skill found in the bundled Apple set) | N | P (command approval modes, allowlists, Docker backend; not OS-enforced per app) | Y (cron, kanban, goals, heartbeat) | Y | Y | Y, if you choose local STT, local TTS and a local model |
| OpenClaw | Y (companion app) | Y (macOS app) | Y (llama.cpp managed, Ollama, LM Studio, MLX, vLLM) | P (iMessage channel, `imsg`, skills) | N | P (macOS app brokers TCC prompts, exec approvals, optional Docker sandbox that is off by default) | Y (cron and heartbeat; not re-verified in detail today) | Y (native app) | P (CLI and gateway; Linux app listed in README, docs page for it not found) | Y, with caveats the project itself documents |
| OpenJarvis (Stanford, new in 2026) | P (spoken digest preset) | ? | Y (local-first by design, installs Ollama) | P (Gmail, Calendar, Tasks through Google OAuth; a "morning-digest-mac" preset) | P (a "morning-digest-linux" preset exists) | ? | Y ("scheduled-monitor" preset) | Y | Y | Y for the model; connectors are cloud accounts |
| Goose | N | N | Y (Ollama and others) | N natively; through MCP extensions | N | P (extension permissions) | P (recipes and scheduling; not re-verified today) | Y | Y | Y |
| Leon | Y (historically) | Y (historically) | P | N | N | N | N | Y | Y | 2.0 alpha is not released; the README says the docs describe the previous version |
| Home Assistant Assist | Y | Y | Y (as a conversation agent) | N | N | Y, but scoped to home entities | Y (automations) | server only | Y | Y |
| Open Interpreter | N (the 01 voice project has had no push since 2024-11-01) | N | Y | N | N | P | N | Y | Y | Y |
| Apple Siri + App Intents (macOS 27) | Y | Y | Apple's own on-device model; third-party models through the new LanguageModel protocol | Y, first party | n/a | Y, OS-enforced | P (Shortcuts automations) | Y | N | Partly; not open source, not on Linux |

No row is all Y. Hermes Agent and OpenClaw are the only two that have voice, wake word, local models, messaging integrations and a scheduler in one project. Hermes Agent has them on both operating systems; OpenClaw's voice and wake word are in its macOS app and its Linux side is partial.

### 1.2 Candidate details

All repo figures verified through the GitHub API on 2026-11-18 [17].

| Project | Repo | Stars | License | Latest release | Last push | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| Hermes Agent | NousResearch/hermes-agent | 264,390 | MIT | v0.23.2, 2026-11-16 | 2026-11-18 | General personal agent with gateway, desktop, TUI, messaging, cron, skills, memory |
| OpenClaw | openclaw/openclaw | 394,718 | MIT | v2026.11.5, 2026-11-17 | 2026-11-18 | Personal assistant gateway with channels and companion apps; stewarded by a 501(c)(3) foundation |
| OpenJarvis | open-jarvis/OpenJarvis | 16,769 | Apache-2.0 | desktop-v1.0.5, 2026-11-11 | 2026-11-18 | Local-first personal AI framework and research platform; created 2026-02-15 |
| NanoClaw | nanocoai/nanoclaw | 31,119 | MIT | not checked | 2026-11-18 | Small OpenClaw alternative; each agent in its own Linux container; created 2026-01-31 |
| nanobot | HKUDS/nanobot | 50,176 | MIT | not checked | 2026-11-18 | Lightweight personal agent; created 2026-02-01 |
| ZeroClaw | zeroclaw-labs/zeroclaw | 33,403 | Apache-2.0 | not checked | 2026-11-18 | Small autonomous assistant infrastructure; created 2026-02-13 |
| PicoClaw | sipeed/picoclaw | 30,138 | MIT | not checked | 2026-11-05 | Tiny deployable agent; created 2026-02-04 |
| IronClaw | nearai/ironclaw | 12,717 | Apache-2.0 | not checked | 2026-11-09 | "Agent OS" focused on privacy and security; created 2026-02-03 |
| Moltis | moltis-org/moltis | 2,970 | MIT | not checked | 2026-10-23 | Rust personal agent server with sandboxed execution and voice; created 2026-01-29 |
| Speakrail | speakrail/speakrail | 215 | Apache-2.0 | not checked | 2026-11-09 | Full-duplex local voice assistant; created 2026-10-04 |
| Goose | aaif-goose/goose (moved from Block to the Agentic AI Foundation at the Linux Foundation) | 56,747 | Apache-2.0 | v1.60.1, 2026-11-18 | 2026-11-18 | General agent: desktop app, CLI, API; MCP extensions |
| Leon | leon-ai/leon | 17,692 | MIT | none | 2026-11-18 | Personal assistant; 2.0 alpha in progress |
| Home Assistant | home-assistant/core | 92,344 | Apache-2.0 | 2026.11.2, 2026-11-16 | 2026-11-18 | Home automation with the Assist voice pipeline |
| Open Interpreter | openinterpreter/openinterpreter | 68,902 | Apache-2.0 | rust-v0.0.61, 2026-11-11 | 2026-11-15 | Now described as "a coding agent for open models" |
| 01 | openinterpreter/01 | 5,165 | AGPL-3.0 | n/a | 2024-11-01 | Voice interface; dormant for two years |
| Open WebUI | open-webui/open-webui | 159,009 | custom (no SPDX id) | v0.13.4, 2026-11-17 | 2026-11-18 | Web chat UI for local and hosted models |
| AnythingLLM | Mintplex-Labs/anything-llm | 68,395 | MIT | v1.20.0, 2026-11-17 | 2026-11-18 | Desktop and server chat with documents and agents |
| Jan | janhq/jan | 45,793 | custom (no SPDX id) | v0.8.8, 2026-10-28 | 2026-11-18 | Offline desktop chat app |
| Khoj | khoj-ai/khoj | 38,170 | AGPL-3.0 | 2.0.0-beta.28, 2026-03-26 | 2026-08-02 | "Second brain"; activity has slowed |
| Onyx | onyx-dot-app/onyx | 33,450 | custom (no SPDX id) | v5.1.3, 2026-11-16 | 2026-11-18 | Team AI chat and search platform |
| LocalAI | mudler/LocalAI | 50,432 | MIT | v4.12.1, 2026-10-23 | 2026-11-18 | OpenAI-compatible local engine for text, voice, images |
| Letta | letta-ai/letta | 25,480 | Apache-2.0 | 0.16.8, 2026-05-14 | 2026-10-18 | Stateful agent platform with memory |
| OpenHands | OpenHands/OpenHands | 93,731 | MIT | v1.41.0, 2026-11-16 | 2026-11-18 | Autonomous software development agent |
| opencode | anomalyco/opencode | 227,729 | MIT | v1.19.6, 2026-11-17 | 2026-11-18 | Terminal coding agent |
| pi | earendil-works/pi | 122,685 | MIT | v1.5.2, 2026-11-10 | 2026-11-18 | Agent toolkit and coding agent CLI; OpenClaw credits it |
| Codex CLI | openai/codex | 135,762 | Apache-2.0 | 0.170.0, 2026-11-18 | 2026-11-18 | Terminal coding agent |
| Cline | cline/cline | 71,750 | Apache-2.0 | v4.1.26, 2026-10-26 | 2026-11-17 | Coding agent as SDK, IDE extension, CLI |
| Aider | Aider-AI/aider | 50,164 | Apache-2.0 | v0.86.0, 2025-08-09 | 2026-05-22 | Terminal pair programmer; no release in 15 months |
| Roo Code | RooCodeInc/Roo-Code | 24,238 | Apache-2.0 | n/a | 2026-05-15 | Archived |
| Qwen Code | QwenLM/qwen-code | 30,746 | Apache-2.0 | not checked | 2026-11-18 | Terminal coding agent tuned for Qwen models |
| cua | trycua/cua | 32,583 | MIT | 2026-11-17 | 2026-11-18 | Background computer-use driver for macOS, Windows, Linux; Hermes uses it |

Closed or partly closed products in the brief: LM Studio (the app is closed source; the `lms` CLI is MIT, 5,439 stars, and its README mentions a headless "llmster" and a "Bionic" app for making a device available to other devices [18]) and Msty (closed source; not researched further). Neither is an assistant with agency; both are model runners with chat.

Notes on the individual candidates:

**Hermes Agent.** Read from the project's own docs as of v0.21.4 (2026-09-26) and from the v0.22.0 and v0.23.0 release notes [1][2][3][4][5]:

- Voice mode in CLI, TUI and desktop, with push-to-talk, silence detection and streaming TTS. Local STT through Faster-Whisper needs no API key. TTS providers include local Piper, NeuTTS and KittenTTS, and any OpenAI-compatible endpoint such as Kokoro-FastAPI. The default TTS is Edge TTS, which is a Microsoft cloud service, so the defaults are not offline.
- Wake word, off by default, detected on-device. Engines: openWakeWord with a bundled "hey hermes" model, sherpa, or Porcupine. A remote desktop client can capture the microphone and stream frames to a headless backend, which fits a mini in a closet.
- Local models: a managed llama.cpp runtime that picks a quantization for the machine, never offers below 4-bit, guarantees at least a 64K context window for recommended models, and unloads idle models after 15 minutes. In the September docs this was a canary feature; v0.22.0 (2026-10-13) announced "one-click llama.cpp runtime".
- Apple skills: iMessage through `imsg`, Reminders through `remindctl`, Notes, Find My. All macOS only. iMessage is also available as a gateway channel through BlueBubbles (self-hosted Mac server) or Photon (a managed service, so not offline).
- Email: an IMAP/SMTP gateway adapter and a Himalaya-based mailbox skill. The docs tell you to use a dedicated account for the agent rather than your personal mailbox.
- Unattended work: cron with per-job model and reasoning pins, a no-agent script mode, and webhook triggers; `/goal` for single-session iterate-until-done with a judge model; a kanban board that dispatches cards to worker processes; `/heartbeat` for recurring prompts inside a session.
- Security: eight documented layers, including command approval modes (`smart`, `manual`, `off`), a separate `cron_mode: deny` default for scheduled jobs that hit a dangerous command, write denylists, Docker and other container backends, and MCP credential filtering. These are application-level controls.
- v0.23.0 (2026-11-05) made one gateway per machine own every session, with CLI, TUI, desktop, editors, bots and cron as clients, and added a browser webapp served from your own gateway. That is the architecture a LAN setup needs.
- Scale and churn: v0.23.0 reports about 10,080 commits and 1,950 merged PRs since v0.22.0, three weeks earlier. This is a fast-moving codebase. Pin a stable release.

**OpenClaw.** From its README and docs [6][7][8]: gateway on the host, a macOS app that prompts for screen, microphone, speech, automation and accessibility permissions and shows exec approval prompts, voice wake and push-to-talk on the Mac, an iMessage channel, a plugin hub. Sandboxing "is off by default" and the docs say "This is not a perfect security boundary". The local model docs are frank: "A model that loads or answers a short prompt may still fail an agent turn" and "Local models do not provide hosted providers' safety filters". Whether macOS speech recognition is on-device was not stated on the page I read.

**OpenJarvis.** New in 2026 and worth knowing about. It is the only candidate designed around local models as the default. Its paper reports that swapping Claude Opus 4.6 for Qwen3.5-9B in a personal agent stack drops accuracy by 25 to 39 points on tasks such as PinchBench and GAIA, and that its search over prompts, tools and settings brings on-device configurations to within 3.2 points of the best cloud baseline on average, matching or beating cloud on 4 of 8 benchmarks [14]. These are the authors' own results. Its README cites earlier research claiming local models handle 88.7% of single-turn chat and reasoning queries [19]. It is younger and smaller than Hermes Agent and OpenClaw, and its personal-data connectors in the README are Google accounts, not Apple apps.

**Home Assistant Assist.** The most mature open voice pipeline (wake word, STT, intent, LLM, TTS over the Wyoming protocol), but it is an appliance for home control, not a desktop or personal-data assistant. Its value here is as a source of voice satellites and as a tool the agent can call. Hermes Agent has a Home Assistant toolset and messaging adapter [3]. The Wyoming satellite repo was archived in January 2026 in favour of an ESPHome-protocol Linux voice assistant [17].

**Coding agents** (opencode, Codex CLI, Claude Code, pi, Qwen Code, Cline, OpenHands, Goose): these are the right tools for the long-horizon class of work. None is an assistant. They do not do voice, personal data or messaging.

**Chat front ends** (Open WebUI, AnythingLLM, Jan, LM Studio, Msty, Onyx, Khoj, LocalAI): useful as a chat window or model runner. None combines voice, app integrations with permissions and scheduled agent work. Feature-by-feature checks of these were not done today; the classification rests on their repo descriptions and my prior knowledge.

**Apple's own stack in macOS 27.** Verified from Apple's WWDC26 macOS guide [20]: the Foundation Models framework "can now work with any language model, including Apple Foundation Models, cloud models like Claude and Gemini, or any other provider that conforms to the Language Model protocol". Apple's `mlx-swift-lm` repo ships an `MLXLanguageModel` that plugs MLX models into the same session API with tool calling and guided generation [21] (secondary summary; repo exists, 875 stars, pushed 2026-11-17). Siri now reaches third-party apps through App Intents entity and intent schemas, and SiriKit is reported as deprecated (secondary) [22]. Apple said the framework core would be open sourced and usable on Linux servers; I could not confirm that this has shipped. `apple/foundation-models-utilities` exists under Apache-2.0 [17]. Reports of a Siri "Extensions" system and a model delegation API come from beta code analysis, not from Apple documentation [23].

What this means: Apple now offers the cleanest permission model (App Intents, per-app consent) and a supported way to run your own MLX model behind a system API. It is not open source end to end, it does not exist on Linux, and it does not give a third-party agent access to Mail or Messages content. A native Swift client that speaks App Intents on one side and an OpenAI-compatible endpoint on the other is a plausible component of a new project, and nobody appears to have built it as an open project yet. That absence is my reading of the search results, not a proven negative.

**MCP servers for Apple apps.** Several exist: JonathanRReed/Apple-MCPs (Mail, Calendar, Reminders, Messages, Contacts, Notes, Shortcuts, Files, Maps; MIT; 34 stars), griches/apple-mcp (131 stars, no license file, last push 2026-03), gabythiesse/apple-mcp-swift, aheusingfeld/AppleMCP (read-only), AndreLYL/Apple2Agent (requires approval on the Mac before outgoing mail is sent) [24][17]. Three of those five have zero stars. This layer is immature. The better-maintained building blocks are the single-purpose CLIs: `imsg` (1,414 stars, v0.21.1 on 2026-11-16) and `remindctl` (426 stars) [25][17].

**Linux equivalents.** Deskbrid (a desktop control daemon with MCP for GNOME, KDE, Hyprland, X11), GNOME Desktop MCP, kwin-mcp, a generic `mcp_dbus` bridge, and Newelle (a GNOME assistant with MCP support) exist. A third-party review of `mcp_dbus` notes that its permission model is unclear and that a malicious prompt could trigger destructive D-Bus calls [11]. I found nothing that gives an agent scoped access to Evolution or KDE PIM calendars, or anything using xdg-desktop-portal as an agent permission broker. cua's Linux backend uses AT-SPI over D-Bus for the accessibility tree [3][11].

### 1.3 Verdict

No single project. Hermes Agent is the best base because it already covers most layers on both operating systems, is MIT licensed, and has the gateway architecture a LAN deployment needs. OpenClaw is the alternative if a native Mac app that brokers permissions matters more than Linux parity. The missing pieces are listed in section 7.

---

## 2. Model layer on M4 Mac minis

### 2.1 Hardware facts

- Apple's published power figures: Mac mini (2024) M4 draws 4 W idle and 65 W maximum; M4 Pro draws 5 W idle and 140 W maximum [26].
- Memory bandwidth decides token speed for models that fit. One source cites 273 GB/s for the M4 Pro mini [27]. The base M4 figure of about 120 GB/s is from my prior knowledge of Apple's specifications and was not re-verified today. Expect a base M4 to generate at a bit under half the speed of an M4 Pro on the same model.
- RAM configurations, from prior knowledge and not re-verified today: base M4 comes in 16, 24 or 32 GB; M4 Pro comes in 24, 48 or 64 GB. So "64 GB" implies an M4 Pro and "32 GB" implies a base M4.
- Sources now benchmark against a Mac mini M6 [28]. The M4 minis are previous-generation hardware. This does not change what they can run.

### 2.2 Speed numbers with stated hardware

| Hardware | Model | Quant | Runtime | Tokens/s | Kind | Source, date |
| --- | --- | --- | --- | --- | --- | --- |
| M4 mini 24 GB, under normal desktop load | Qwen 3 14B dense | 4-bit | MLX | 11.5 | measured | [29], 2026-03 |
| M4 mini 24 GB, same | Qwen 3 30B-A3B MoE | 4-bit | MLX | 44.8, with 2.74 GB swap and memory pressure | measured | [29] |
| M4 mini 24 GB, same | Qwen 3.5 35B-A3B MoE | 4-bit | MLX | Metal out-of-memory crash at 20.4 GB | measured | [29] |
| M4 mini 24 GB, same | Llama 3.2 3B | Q4_K_M | Ollama | 42.0 | measured | [29] |
| M4 mini 24 GB, same | DeepSeek-R1 32B dense | Q4_K_M | Ollama | 0.28 (swapping) | measured | [29] |
| M4 mini 16 GB | Mellum2.1-12B-A2.5B-Thinking | Q4_K_M | llama.cpp | about 50 | community run | [28], 2026-11-14 |
| M4, 24 GB | LFM2.5-24B-A2B | 4-bit | MLX | 59.9 | community run | [30], 2026-11-14 |
| M4, 16 GB | LFM3-1.7B | 4-bit | MLX | 92.5 | community run | [30] |
| M4, 16 GB | Qwen 3.5 9B | Q4_K_M | LM Studio | 18 | estimate from a bandwidth model | [30] |
| M4, 16 GB | gpt-oss 20B | MXFP4 | MLX | 34 | estimate | [30] |
| M4, 16 GB | Gemma 4 12B | Q4_K_M | MLX | 13 | estimate | [30] |
| M4 Pro mini 64 GB | Qwen3.5-35B-A3B | 8-bit | llama.cpp | 40.0 at 512 context, 35.7 at 16K | measured | [12], 2026-09-12 |
| M4 Pro mini 64 GB | Qwen3.5-35B-A3B | 8-bit | mlx_lm | 49.3 at 512, 43.7 at 16K | measured | [12] |
| M4 Pro mini 64 GB | Qwen3.5-35B-A3B | 8-bit | EXO | 66.8 at 512, 57.0 at 16K | measured (EXO Labs co-authored the paper) | [12] |
| M4 Pro 48 GB | Qwen 3.5 9B | 4-bit | MLX | 50.2 | community run | [30] |
| M4 Pro 48 GB | Qwen 3.5 9B | Q4_K_M | llama.cpp | 39.1 | community run | [30] |
| M4 Pro 48 GB | Recursive Flint (40B, about 2.5B active) | Q4_1 | llama.cpp | 79.6 | community run | [28][30] |
| M4 Pro 48 GB | Qwen 3.8-27B dense | Q4_K_M | Ollama | 13 | estimate | [30] |
| M4 Pro 64 GB | Qwen3-Coder-Next (80B, 3B active) | Q4_K_M | Ollama | about 44 | estimate; the source says no measured Mac run exists | [28] |
| M4 Pro 24 GB | Qwen 3.6-35B-A3B | Q4_K_M | Ollama | 74 | estimate; and it does not fit comfortably in 24 GB | [30] |
| M6 mini 32 GB | Qwen 3.6-35B-A3B | 4-bit | MLX and oMLX | 59 | community runs | [28] |
| M6 mini 24 GB | Qwen 3.8-27B dense | 4-bit | not stated | about 10, "too slow for an agent loop" | community run | [28] |

Prefill matters as much as decode for agents. On the M4 Pro 64 GB mini with the 8-bit 35B-A3B model, processing a 16K-token prompt took 25.0 s on llama.cpp, 22.8 s on mlx_lm and 18.8 s on EXO [12]. An agent turn with a large tool list and history pays that cost every time the cached prefix is invalidated. Prompt caching is not optional.

The index in [30] labels its figures as 73 published, 246 community and 300 estimated, and reports a 14% median gap between its estimates and measurements. Treat its estimate rows accordingly. The measured M4 24 GB study found that "theoretical estimates were 1.5-2x too optimistic" under real desktop load [29].

### 2.3 What currently leads for local agent work

Model families that exist on Hugging Face today (verified by listing, 2026-11-18) [15]: Qwen 3.5 (February 2026), Qwen 3.6-35B-A3B (April 2026), Qwen 3.8-27B (August 2026), Gemma 4 (E2B, E4B, 12B, 26B-A4B, 31B; March to May 2026), NVIDIA Nemotron 3.5 Lightning 30B-A3B (August 2026) and Bolt E4B (October 2026), GLM-5.3 and GLM-5.3-Flash (August 2026), DeepSeek V4.1 Flash (September to October 2026), Recursive Flint (October 2026), JetBrains Mellum2.1-12B-A2.5B (September 2026), Cohere North Mini Code 1.0 (June 2026), Kwaipilot KAT-Coder-V2.5 (July 2026), Ornith 1.5 9B and 35B-A3B (August 2026), LiquidAI LFM3 (October 2026), Qwen3-Coder-Next (January 2026), gpt-oss 20b and 120b (August 2025), Devstral Small 2 24B and Devstral 2 123B (December 2025), Mistral Small 4 119B (January 2026), Hermes 4 (August 2025) and Hermes 4.3 36B (November 2025). I found no Phi-5 and no Llama 5; the newest Phi and Llama entries in these searches are old.

Published coding-agent scores, all vendor or secondary, with different scaffolds, so not directly comparable [28][16][27]:

| Model | Size | Score | Scaffold | Source |
| --- | --- | --- | --- | --- |
| Recursive Flint | 40B, about 2.5B active | 74.2 SWE-bench Verified | mini-swe-agent, vendor run | [28] |
| Qwen 3.6-35B-A3B | 35B, 3B active | 73.4 SWE-bench Verified | Qwen's own scaffold; 64.4 in a third-party Claude Code run | [28] |
| Qwen3-Coder-Next | 80B, 3B active | 70.6 SWE-bench Verified | SWE-Agent | [28] |
| KAT-Coder-V2.5 | 35B, 3B active | 69.4 SWE-bench Verified | Claude Code 2.1.195, vendor run | [28] |
| North Mini Code 1.0 | 30.5B, 3B active | 67.6 SWE-bench Verified | SWE-agent, vendor | [28] |
| MiMo-V2.6-Distill-Qwen-9B | 9.4B dense | 61.1 SWE-bench Verified | scaffold not named | [28] |
| Mellum2.1-12B-A2.5B | 12B, 2.5B active | 47.0 SWE-bench Verified | Pi harness, vendor | [28] |
| Qwen 3.8-27B | 27B dense | 67% Terminal-Bench 2.1; 65.77% Hermes Bench | Nous Research's runs | [16] |
| Arete-27B (Nous) | 27B dense | 70% Terminal-Bench 2.1; 65.60% Hermes Bench | Nous Research's runs | [16] |
| GLM-5.3 | 753B, about 40B active | 88.2 Terminal-Bench 2.1 | cited without a primary link | [27] |

GLM-5.3 at 4-bit is about 425 GB [27]. It is not a Mac mini model. The gap between it and Qwen 3.8-27B on the same benchmark (88.2 against 67) is a rough measure of what fitting in a mini costs. I did not find hosted frontier scores on Terminal-Bench 2.1 from a primary source today.

### 2.4 Tool-calling reliability

There is no single authoritative tool-calling leaderboard for these models that I could find. What the evidence shows:

- **The runtime changes the result.** In SiliconBench's agent split on Gemma 4 E4B, llama.cpp completed 100 of 100 requests, oMLX 94, vllm-metal 93 and mlx_lm 56, with the paper attributing part of the failures to tool-call serialization [12]. On Qwen3-0.6B, Ollama failed the paper's five-shot fidelity check and streamed about 254 tokens with an empty tool-call field on tool prompts; the paper traces this to a chat-template import bug in April [12]. A model that calls tools correctly on one server can fail on another.
- **The quantization source changes the result.** One hands-on OpenCode comparison found Unsloth's IQ3_XXS build of Qwen 3.5 27B made 5.0% errors on a migration task while another publisher's IQ3_XXS of the same model made 100% [31] (secondary; hardware was a 16 GB VRAM PC, not a Mac; no date on the page).
- **Small models skip tools.** In the same test, `qwen3.5:9b` at the default Ollama quantization "never called a tool" and claimed a build without touching files. gpt-oss 20b failed at default reasoning and passed with high reasoning. Devstral Small 2 24B wrote shell commands into `go.mod`. Qwen3-Coder-Next, Gemma 4 26B-A4B and the good Qwen 3.5 27B build passed with single-digit error rates [31].
- **KV cache quantization hurts.** One guide reports that aggressive KV cache quantization degrades tool-calling accuracy [32] (secondary).
- **Published numbers**: Qwen 3.6-35B-A3B reports 62.8 on MCP-Atlas and 67.2 on TAU3-Bench (vendor); an arXiv agent benchmark scored Gemma 4 26B at 0.82 overall and Gemma 4 31B at 0.86, with gpt-oss-120b lowest at 0.71 [32][33] (both secondary summaries; I did not read the paper).

Practical rule: pick the model with your own evaluation, on the runtime that will be used in production, at the quantization that will be used.

### 2.5 Recommendations per RAM tier

These assume a dedicated mini with no desktop apps competing for memory. The 24 GB study that hit swap had 12 to 13 GB committed to other apps before loading a model [29]. Speeds for the base M4 are my inference from the rows above unless a row is cited; they are not measurements.

| Tier | Chip | (a) Fast assistant chat and tool calls | (b) Long-horizon agent work | Context in practice | Honest verdict |
| --- | --- | --- | --- | --- | --- |
| 16 GB | M4 | Gemma 4 E4B or Qwen 3.5 9B at 4-bit (about 18 tok/s estimated for the 9B [30]). Mellum2.1-12B-A2.5B if coding-flavoured answers are fine (about 50 tok/s on a 16 GB M4, community [28]). | Do not. Use hosted. | 16K to 32K | Fine as a voice and chat endpoint and for classification. A 9B model dropped 25 to 39 points against a frontier model in agent benchmarks [14] and skipped tools in a hands-on test [31]. |
| 24 GB | M4 or M4 Pro | Gemma 4 26B-A4B at 4-bit (16 GB of weights [27]) or LFM2.5-24B-A2B (59.9 tok/s in a community run on a 24 GB M4 [30]) or gpt-oss 20b with reasoning set high. | Marginal. A 30B-A3B MoE at 4-bit fits only on a headless machine with a capped context; the 35B-A3B class crashed at 20.4 GB on a loaded 24 GB machine [29]. Nemotron 3.5 Lightning 30B-A3B is the same size class. | 32K, sometimes 64K | Good assistant tier. Agent work is limited to narrow, structured, checkable jobs such as read-only upstream triage. |
| 32 GB | M4 | Same as 24 GB, with room for STT and TTS models alongside. | Qwen 3.6-35B-A3B at 4-bit (23 to 24 GB [28]) or Recursive Flint (23 GB [28]). Qwen 3.8-27B dense fits at 18 GB but is slow: about 10 tok/s on a faster M6 [28]. | 32K to 64K. Flint's full 262K window needs 48 GB [28]. | The first tier where a credible local coding agent runs. Expect it to be slower and less reliable than hosted, and keep context short. On a base M4 expect well under the 59 tok/s reported in community runs on an M6. |
| 64 GB | M4 Pro | Keep a small fast model pinned for chat and voice (Gemma 4 E4B or a 9B) and swap the big one in for work. | Three sensible choices: Qwen 3.6-35B-A3B at 8-bit (39 GB in Ollama [28]; the older 3.5 version of this class measured 40 to 67 tok/s at 8-bit on this exact hardware [12]) for speed; Qwen 3.8-27B at 6 or 8-bit for quality at roughly 13 tok/s or less [30]; Qwen3-Coder-Next at Q4 (52 GB, 64 GB "is the practical floor" [28]) for repo-scale work. | 64K to 128K realistically. Full 256K fits for the 27B per one source [27] but prefill time makes that slow. | The only tier where local long-horizon work is worth attempting. Still below hosted frontier models. |

Quantization guidance:

- 4-bit is the floor for agent work. Hermes Agent refuses to offer anything lower because "the quality loss is too severe" [5]. Sub-4-bit builds produced erratic results in hands-on testing [31].
- For MoE models with about 3B active parameters, speed is cheap, so spend spare memory on 6 or 8-bit weights rather than a larger model.
- Prefer builds from the model vendor, Unsloth, `ggml-org`, `lmstudio-community` or `mlx-community`, and test the exact file. Publisher matters [31].
- Do not quantize the KV cache aggressively for tool-calling work [32].
- Set context explicitly. Ollama defaults to 4,096 tokens and silently truncates; llama.cpp also truncates unless the slot context is raised [12][28].

### 2.6 Where local still falls short, and the hybrid pattern

- METR's May 2026 report put the public frontier at about 12 hours of task length at 50% reliability and about 1.5 hours at 80% [34] (secondary summary of METR). METR notes this measures task difficulty, not how long an agent can run unattended.
- A long-horizon terminal benchmark published in October 2026 ran 15 frontier models on tasks of up to three hours. The best scored a dense mean reward of 0.69, and on its 30 reconstruction tasks the binary pass rate averaged 0.221 [13]. Frontier hosted models still fail most strict multi-hour tasks. The paper's abstract reports no open-weight results.
- Epoch AI's estimate, as reported, is that open weights trail the closed frontier by about four months [34] (secondary). That figure is for the best open models, which are hundreds of billions of parameters. Models that fit in 64 GB are a further step down, as the 88.2 against 67 comparison above suggests.
- Failure modes reported for small local models in agent loops: not calling tools and claiming success, fabricating endpoints, malformed or text-only tool calls, looping, and collapse when context is truncated silently [31][8][12].
- Local models have no provider-side safety filtering, so prompt injection from fetched content is a larger risk [8].

Hybrid setups people actually run:

- Hosted primary with local fallback, or the reverse. Both Hermes Agent (`fallback_providers`, per-job cron model pins, `cron.model`) and OpenClaw (`models.mode: "merge"`, per-turn fallback) support this in configuration [2][8].
- Local model extracts facts, deterministic code decides. This is the most robust use of a small model. A read-only upstream triage job is the standard example: the model labels, deterministic code computes priority, and nothing pushes.
- Local for anything that reads personal data (messages, mail, calendar), hosted for code in public repos.
- Frontier model at design time, local model at run time. OpenJarvis uses cloud models to search for a better local configuration and then runs fully on-device [14].
- A small hosted "judge" or a rules check on the output of a local worker before anything is published.

---

## 3. Runtime layer

### 3.1 Servers on macOS

All figures verified through the GitHub API on 2026-11-18 unless marked [17].

| Runtime | Version, date | License | Strengths | Weaknesses | Use it for |
| --- | --- | --- | --- | --- | --- |
| llama.cpp `llama-server` | v1.0.0, 2026-11-13 | MIT | Passed all three SiliconBench gates (completion, fidelity, model coverage). Low, flat memory. Most reliable tool-call completion in that test. OpenAI-compatible API, now including `/v1/audio/speech`. v1.0.0 added server hardening against SSRF, CORS and DNS rebinding, which matters for LAN exposure [35][12]. | Slower decode than MLX stacks on the same model (40.0 against 49.3 tok/s on the M4 Pro) [12]. Default four server slots; latency grows under concurrency. | The default for agent work. Also runs identically on Linux. |
| oMLX | v0.8.0, 2026-11-18 | Apache-2.0 | MLX speed, continuous batching, a hot memory plus cold SSD KV cache that survives context changes, model pinning and auto-swap, menu bar app, OpenAI-compatible API on port 8000, optional MCP. Passed all three SiliconBench gates [36][12]. | Memory "grows, bounded". 94 of 100 on the agent split. Some model families need custom Metal kernels that require full Xcode to build [36]. Single maintainer listed. | An always-on mini that serves several clients and swaps between a pinned small model and a larger one. |
| vllm-metal | v0.33.0, 2026-11-04 | Apache-2.0 | Best throughput under concurrency and lowest time to first token under load in SiliconBench; passed all three gates; has a sleep mode that returns memory when idle [12][37]. | Heavier to set up. Default context below agent prompt sizes, so it rejects long prompts unless raised [12]. | Several agents hitting one server at once. |
| mlx-lm `mlx_lm.server` | v0.32.2, 2026-10-16 | MIT | Reference MLX server. Simple. Supports tensor parallelism over Thunderbolt RDMA [12]. | Only 56 of 100 on the Gemma 4 agent split and partial runs on larger models in SiliconBench [12]. | Quick tests and LoRA training, not production agent serving. |
| Ollama | v0.40.16, 2026-11-09 | MIT | Easiest model management. Since v0.40.0 (2026-09-25) supported architectures run on MLX by default on Apple Silicon [38]. | In SiliconBench's August build it held 94 to 97% of the Metal memory hint, failed five-shot fidelity on one model, and covered one of three model releases [12]. Default 4,096-token context [28]. | Convenience, and apps that already speak the Ollama API, such as techmore/weather-me-timbers. Re-test before trusting it for tool calls. |
| LM Studio, llmster | `lms` CLI pushed 2026-11-17 | App closed; CLI MIT | Good GUI, headless daemon mentioned in the CLI README [18]. | Closed source core. Headless details not verified today. | Optional. |
| EXO | v1.0.71, 2026-04-23; last push 2026-11-06 | Apache-2.0 | Fastest single-node number in SiliconBench on the M4 Pro (66.8 tok/s), and the best two-node scaling [12]. | No tagged release in seven months. The benchmark that favours it was co-authored by EXO Labs. | Clustering experiments only. |
| Hermes managed llama.cpp | part of Hermes Agent | MIT | No configuration; hardware-aware quantization choice; 64K context guarantee; idle unload [5]. | Tied to Hermes. | A single-machine setup where Hermes is the only client. |

### 3.2 One always-on server for the LAN

This works and is the standard pattern. Every runtime above exposes an OpenAI-compatible endpoint. Points that matter:

- Bind to the LAN interface or a tailnet address, not to all interfaces, and require an API key. llama.cpp, oMLX and vllm-metal support keys; verify the exact flags against current docs.
- Keep the mini from sleeping, and run the server as a LaunchDaemon or LaunchAgent with KeepAlive. A crash-looping job pointed at a missing model file is easy to miss; add a health check.
- Set context length explicitly on the server and tell the client the same number.
- Turn prompt caching on and keep system prompts and tool lists stable so the prefix stays cached.
- One model resident at a time on 32 GB or less. On 64 GB, pin a small chat model and swap the large one.
- Put the agent gateway on the same Mac that holds the Apple data, because iMessage, Reminders and Notes access is macOS only. Linux machines connect as clients. Hermes Agent v0.23.0's single-gateway design and browser webapp are built for this [1].

### 3.3 Clustering multiple minis

Measured on two M4 Pro 64 GB minis linked by Thunderbolt 5 with RDMA, on a model that already fits on one node [12]:

| Stack | One node, decode at 512 context | Two nodes | Speedup |
| --- | --- | --- | --- |
| llama.cpp (pipeline over TCP) | 40.0 tok/s | 32.4 tok/s | 0.80 to 0.84x, a regression |
| mlx_lm (tensor parallel over RDMA) | 49.3 | 63.3 | 1.28 to 1.32x |
| EXO (tensor parallel over RDMA) | 66.8 | 87.0 | 1.30 to 1.37x |

Prefill roughly doubles at short contexts and gains 1.7 to 1.8x at 4K tokens [12].

Conclusions:

- Two M4 Pro minis give about 1.3x on decode, not 2x.
- Without RDMA, a second node makes things slower.
- RDMA over Thunderbolt needs Thunderbolt 5 and macOS 26.2 or later [39] (secondary). The base M4 mini has Thunderbolt 4 (from prior knowledge, not re-verified), so base M4 minis cannot use it.
- The only strong reason to cluster is to load a model that does not fit on one machine. For minis that means stepping from a 27 to 35B model to something like Qwen3-Coder-Next or a 120B-class model across two 64 GB Pros. I found no measured mini results for that case.
- oMLX has an experimental multi-Mac mode in source builds [36]. A related project, omarchy-cluster, targets one MLX model across Macs on macOS and Omarchy Linux (25 stars) [17].
- The better use of several minis is separate roles: one serves the chat model and voice, one runs agent jobs, one is the spare. Independent servers give you parallelism and isolation with no cluster software.

### 3.4 Linux on Apple Silicon

| Question | Answer today | Source |
| --- | --- | --- |
| Does Asahi support the M4 mini? | Device tree is in linux-asahi 7.4 (base M4) and 7.5 (M4 Pro). Wi-Fi, Bluetooth, NVMe and Ethernet are listed as working in linux-asahi. GPU, HDMI output, Thunderbolt, audio, ANE and suspend are all "TBA". There is no installer. | [40] |
| Is there any M4 GPU driver on Linux? | Gravity Linux, a Fedora remix forked from Asahi over its generative AI policy, released an alpha on 2026-09-18 with an M4 GPU driver: OpenGL ES 3.0 and OpenGL 3.3, HDMI works. Vulkan and OpenCL are listed as remaining work. Marked "FOR DEVELOPERS". | [41] |
| Can an M4 mini run LLM inference on its GPU under Linux? | No. The working paths (llama.cpp Vulkan, omarchy-mlx) need Vulkan compute, and M4 has no Vulkan driver. The omarchy-mlx README states M4 is "Not yet (no Linux GPU driver)". | [41], omarchy-mlx README |
| Is the M4 ANE usable on Linux? | No. omarchy-ane has an `h16` bring-up module that does not run real inference yet. Asahi lists ANE as TBA. | omarchy-ane README, [40] |
| What about M1 and M2 Macs on Linux? | This works. omarchy-mlx reports oMLX at about 82 to 91 tok/s on an M1 Max, and llama.cpp Vulkan with patched Mesa at 27.4 tok/s on Qwen3-30B-A3B on an M1 Max (up from 1.5 tok/s on stock Mesa). M1 Pro GPU is listed as untested; M1 Pro ANE is on by default. | omarchy-mlx README and `docs/ENGINES.md` (project's own measurements, October 2026) |
| Ordinary x86 or ARM Linux | llama.cpp with CUDA or Vulkan, vLLM on NVIDIA, Ollama. This is the mature path and needs no special comment. | general |

Conclusion: keep the M4 minis on macOS as the inference servers and treat Linux machines as clients. M1 and M2 machines are where Linux-side GPU inference is plausible today. The M1 Pro GPU is listed as untested upstream, so a test report for it would be a useful contribution. Re-check M4 status when a Vulkan driver lands; that is the single dependency.

---

## 4. Voice

### 4.1 Speech to text

| Model | Where it runs | Numbers | Notes |
| --- | --- | --- | --- |
| Parakeet TDT 0.6B v3 | Core ML through FluidAudio (Apache-2.0, v0.18.3, 2026-11-07), MLX through mlx-audio, GGUF builds, ONNX on Linux | On a MacBook Air M4 16 GB: 0.10 s average latency, real-time factor 0.014, WER 2.50% on a 50-utterance LibriSpeech sample [42] | 25 European languages. The best default on Apple Silicon. FluidAudio runs it on the Neural Engine. omarchy-mlx runs Parakeet on the ANE under Linux on M1 and M2. |
| Whisper large-v3-turbo | WhisperKit (argmax-oss-swift, MIT), mlx-audio, whisper.cpp, Faster-Whisper | Same test: 0.68 s, RTF 0.095, WER 2.89% [42] | 99+ languages and translation. The author notes the accuracy difference is within noise. Hermes Agent's built-in local STT is Faster-Whisper [4]. |
| Moonshine streaming (tiny, small, medium) | CPU, cross-platform; MIT for English and streaming models | Latency numbers not captured today | Does work while the user is still talking. Good for Linux boxes without a GPU [17][43]. |
| Voxtral Mini 4B Realtime | llama.cpp-family audio runtimes, mlx | Emits words and a turn signal every 80 ms in Speakrail's pipeline [44] | Streaming, heavier (4B). |
| Nemotron 3.5 ASR streaming 0.6B, Canary, Qwen3-ASR, Granite Speech 5.0 | various | not benchmarked today | Exist on Hugging Face with GGUF or MLX builds [15]. |

I found no Whisper large-v4 [15].

### 4.2 Text to speech

| Model | License | Numbers | Notes |
| --- | --- | --- | --- |
| Kokoro-82M | Apache-2.0 | One M5 Max test reports RTF about 0.08 and first audio around 90 ms (secondary, unverified) [45] | Small, fast, good quality, no voice cloning. Available through FluidAudio (Core ML), mlx-audio, ONNX, and Kokoro-FastAPI (OpenAI-compatible; Hermes documents using it) [3][17]. The original repo has had no push since 2025-08. |
| Pocket TTS (Kyutai) | MIT | "~200ms to get the first audio chunk", about 6x real time on a MacBook Air M4 using two CPU cores [46] | CPU only, streaming, voice cloning. Works the same on Linux. FluidAudio also runs it on the ANE. |
| Piper | GPL-3.0 (OHF-Voice/piper1-gpl, v1.8.0, 2026-09-04) | not measured today | Very light, many languages, robotic compared with Kokoro. Built into Hermes Agent and Home Assistant [3]. Note the licence change from the old MIT repo. |
| Qwen3-TTS 0.6B and 1.7B | see model card | not measured today | Voice design and custom voices; MLX builds; Hermes docs mention it through oMLX [3][15]. |
| CSM 1B (Sesame), Chatterbox, Dia, Voxtral TTS 4B | various | not measured today | More expressive, heavier, slower. In mlx-audio [47]. |
| NeuTTS, KittenTTS | see projects | not measured today | Local options built into Hermes Agent [3]. |

mlx-audio (MIT, v0.6.6, 2026-11-16, 8,298 stars) is the one package that covers most of these on Apple Silicon with an OpenAI-compatible server [47][17].

### 4.3 Wake word

- openWakeWord (Apache-2.0): the common open choice, CPU only. Hermes Agent bundles a trained "hey hermes" model for it; omarchy-mlx uses it for "hey_jarvis" [4]. The upstream repo's last push was 2025-12-30 [17], so it is stable but not actively developed.
- sherpa: open-vocabulary, typed phrases, no training. Hermes's fallback engine [4].
- Porcupine (Picovoice): proprietary, free tier, needs an access key [4].
- Home Assistant's microWakeWord runs on ESP32 satellites. Not researched further today.

### 4.4 Realistic latency for one voice turn

Measured end to end:

- Speakrail (full duplex, Voxtral Realtime plus a Gemma 4 LoRA plus Pocket TTS or Breeze TTS) reports a median of 0.54 to 0.74 s from the user's last word to audio, on an RTX 4090, from 12 and 66 replies [44]. It has a Mac configuration (`mac-e4b`, Apple Silicon 16 GB and up) but publishes no Mac latency in the README.

Budget for a cascaded pipeline on an M4 mini, assembled from the component numbers above. This is my estimate, not a measurement:

| Stage | Time | Basis |
| --- | --- | --- |
| End-of-speech detection | 0.2 to 0.6 s | Silence threshold; the largest tunable. Streaming turn detection (Speakrail, Moonshine) removes most of it. |
| STT | 0.1 to 0.2 s | Parakeet on Core ML [42] |
| LLM time to first token, small model, cached prompt | 0.2 to 0.5 s | SiliconBench TTFT p50 of 179 to 385 ms for Gemma 4 E4B on an M5 Pro [12]; an M4 will be slower |
| First sentence generated | 0.3 to 1.0 s | 15 to 20 tokens at 20 to 50 tok/s |
| TTS first audio | 0.1 to 0.2 s | Pocket TTS, Kokoro [46][45] |
| **Total to first audio** | **about 1 to 2.5 s** | A secondary source's own estimate for a similar stack is 1.5 to 2.5 s [48] |

What breaks this budget: a tool call adds a full extra model turn; an uncached prompt adds seconds; a 27B dense model at 10 to 13 tok/s adds one to two seconds to the first sentence; a model that was unloaded for idleness adds a cold load. For a Siri-like feel, voice turns should go to a small pinned model, with hand-off to the large model or a hosted one announced out loud.

---

## 5. Integrations and permissions

### 5.1 macOS: what each kind of access actually requires

| Data or action | Mechanism | Permission (TCC) | Scope you get | Tools |
| --- | --- | --- | --- | --- |
| Calendar, Reminders | EventKit | Per-app Calendar and Reminders grants, with a write-only option for Calendar | Good: per data type, per binary | `remindctl`; EventKit-based MCP servers [24][25] |
| Contacts | Contacts framework | Per-app Contacts grant | Good | MCP servers [24] |
| Notes | AppleScript or JXA to Notes.app | Automation grant from the host app to Notes | All notes, read and write | Hermes `apple-notes` skill; MCP servers [3][24] |
| Mail (Mail.app) | AppleScript or JXA; some tools read Mail's SQLite store directly | Automation to Mail; direct database reads need Full Disk Access | All mailboxes | MCP servers [24] |
| Mail (protocol) | IMAP and SMTP, or a provider API | None on the Mac. Scope comes from the credential. | As narrow as the provider allows (app password, OAuth scopes) | Hermes email gateway; Himalaya [3] |
| Messages, read | Read `~/Library/Messages/chat.db` | **Full Disk Access** for the host process | Everything Full Disk Access covers, far beyond Messages | `imsg` [25] |
| Messages, send | AppleScript to Messages.app | Automation to Messages | Can send to anyone | `imsg send`; BlueBubbles server [25][3] |
| Files | Direct | Folder grants (Desktop, Documents, Downloads, removable volumes) or Full Disk Access | Per folder | n/a |
| Screen and UI control | Accessibility, Screen Recording | Per-app grants | Whole desktop | cua, Peekaboo [3][17] |
| App actions through Siri | App Intents | System consent per app | Per intent; the cleanest model | Only for apps that ship intents; not a general agent API [20] |
| Shortcuts | `shortcuts run` CLI | Inherits each shortcut's own grants | Per shortcut; a good hand-built allowlist | Apple-MCPs lists Shortcuts support [24] |

Two things to know:

1. **TCC grants attach to the "responsible" app**, which for a CLI tool is usually the terminal or the launchd-run binary. Granting Full Disk Access to a terminal gives it to everything run in that terminal. This is from prior knowledge of macOS and is consistent with the `imsg` and Hermes skill instructions, which tell you to grant Full Disk Access to the terminal [25][3].
2. **Apple is tightening exactly this.** On 2026-10-02 Apple said it would add "additional controls" to Full Disk Access because of AI agents, noting that such access could expose "files, mail, messages, and even browsing history" [9]. The macOS 27.3 beta, reported 2026-11-16, splits the setting into "System & App Protection Override" and "Accessibility", encourages grants limited to specific apps or folders, adds an ask-each-time option, and shows a menu bar indicator when one app controls another. Existing grants stay in effect; developers must "gracefully handle" limited access; entitlement details are "coming soon" [10]. Any design that depends on blanket Full Disk Access is building on ground that is moving. Plan for per-folder grants and for helper binaries with a single narrow grant each.

### 5.2 A safer shape for macOS

- **Separate macOS user account for the agent.** It gets its own home directory, keychain and TCC database. Sign that account into only what the agent needs. The catch: Messages and iCloud data belong to the Apple ID signed in to that account, so reading your messages needs either your Apple ID on the agent account or a small broker in your own account. I found one tool (SandVault) that combines a separate account with sandbox-exec; I did not evaluate it [49].
- **Broker processes with one grant each.** A tiny signed helper that holds the Messages grant and exposes only "list recent threads", "read thread", "queue draft", over a local socket. The agent never holds Full Disk Access. No existing project packages this; it is gap 1 in section 7.
- **Sandbox the agent's shell.** Anthropic's `sandbox-runtime` (`srt`, Apache-2.0, 7,170 stars) wraps any process using `sandbox-exec` on macOS and bubblewrap on Linux, with a network allowlist proxy, without a container [50]. Codex CLI, Claude Code and Gemini CLI all use Seatbelt on macOS [49]. Limits reported in 2026 write-ups: `sandbox-exec` is marked deprecated though it still works on macOS 27.0.1; profiles that block writes can still leave secrets readable unless reads are denied explicitly; nested sandboxes break browsers launched inside [49] (secondary).
- **Containers and VMs.** Apple's `container` tool runs Linux containers in lightweight VMs on a Mac (Apache-2.0, 51,911 stars) [17]. Hermes Agent and OpenClaw both support Docker backends for tool execution; NanoClaw runs every agent in its own container by default [3][7][51]. A container cannot reach Apple app data at all, which is the point: run code tasks inside, keep personal-data tools outside behind the broker.
- **Agent-level approvals.** Hermes: `approvals.mode: manual` or `smart`, and keep `cron_mode: deny` so unattended jobs fail closed [3]. OpenClaw: tool allow and deny policies and exec approvals in the Mac app [7].

### 5.3 Draft but do not send

| Channel | Pattern | Notes |
| --- | --- | --- |
| Email over IMAP | Append the draft to the Drafts mailbox with IMAP APPEND. Give the agent IMAP only and no SMTP credential. | The mail client shows the draft on every device. The agent physically cannot send. Standard IMAP behaviour, from prior knowledge. |
| Gmail | A credential limited to composing drafts. | Scope names not re-verified today. |
| Mail.app | AppleScript: create an outgoing message with `visible:true` and never call `send`. | Weaker: the same Automation grant also permits `send`. Enforce in the broker, not in the prompt. |
| Messages | There is no drafts API. Use a review queue: the agent writes proposed replies to a queue; you approve; only the approval path calls `imsg send`. An alternative is opening an `sms:` or `imessage:` URL to prefill the compose field for you to press return; I did not test this today. | Apple2Agent implements native approval before outgoing mail [24]. Hermes's iMessage skill says to always confirm bulk sends but that is an instruction to the model, not an enforcement [3]. |
| Any channel | Split read tools and write tools into separate MCP servers or skills and enable only the read set for unattended jobs. | Hermes toolsets and OpenClaw tool policies both allow this [3][7]. |

### 5.4 iMessage specifically

| Option | How | Offline | Limits |
| --- | --- | --- | --- |
| `imsg` | Swift CLI on the Mac. Reads `chat.db`, watches for new messages as NDJSON or JSON-RPC, sends through Messages.app automation. v0.21.1, 2026-11-16. A Linux build can read a copied `chat.db` but cannot send. | Yes | Needs Full Disk Access on the Mac. No group management [25]. |
| BlueBubbles server | Open-source macOS server (Apache-2.0, 1,146 stars) bridging iMessage to other devices over a REST API and webhooks. Hermes has an adapter. | Yes on a LAN | Needs an always-on Mac signed into Messages [3][17]. |
| Photon | Managed iMessage line service with a Hermes plugin. | No | Third-party service; messages leave the house [3]. |
| blueferry | iPhone to Linux over Bluetooth, no Mac. v0.9.1, 2026-10-31, 343 stars. Clients for GTK, KDE, Quickshell and terminal. | Yes | Experimental. Sees only messages while connected. No attachments, reactions or full sent history. Apple could change the Bluetooth behaviour [17]. |
| OpenClaw iMessage channel | Built in, uses `imsg`. | Yes | Same permissions as `imsg` [6]. |

In practice: the always-on mini runs `imsg` or BlueBubbles and is the message hub; Linux clients talk to the agent gateway on the mini. blueferry is the fallback for a Linux box used away from the minis, and wiring it to an agent is unbuilt.

### 5.5 Linux

- Sandboxing is stronger than on macOS: bubblewrap (what `srt` uses), Landlock, systemd unit hardening (`ProtectHome`, `ReadWritePaths`, `PrivateNetwork`, `NoNewPrivileges`), dedicated service users, rootless Podman. These are standard and scriptable.
- Personal data is weaker: there is no common, permissioned API for calendar, contacts, mail and notes across desktops. The MCP bridges found expose D-Bus or the accessibility tree broadly [11]. On Omarchy (Hyprland) there is no desktop-wide portal permission system for these data types that I could find.
- The pragmatic approach on Linux is protocol-level access with narrow credentials: CalDAV and CardDAV for calendar and contacts, IMAP for mail, plain Markdown files for notes, `gh` with a fine-grained token for GitHub. That also works on macOS, which makes it the portable layer. iCloud calendars and contacts are reachable over CalDAV and CardDAV with an app-specific password (from prior knowledge; not re-verified today).
- KDE Connect (4,169 stars) covers Android notifications and SMS; it does not help with iMessage [17].

---

## 6. Long-horizon and unattended operation

### 6.1 Scheduling

| Scheduler | Where | Good for | Watch out for |
| --- | --- | --- | --- |
| launchd LaunchAgents | macOS | Anything that must survive reboots; runs in the user session so TCC grants apply | Silent failure. A job pointed at a missing model file can fail on every start without anyone noticing. Jobs need a health check and an alert. |
| systemd timers | Linux | Same, with sandboxing directives built into the unit | n/a |
| Hermes cron | both | Natural-language jobs, per-job model and reasoning pins, delivery to a chat or a file, script-only "no-agent" jobs, webhook-triggered jobs; `cron_mode: deny` by default [2][3] | Unpinned jobs follow whatever the main model is when they fire. Pin the model per job. |
| Hermes kanban and `/goal` | both | A queue of tasks with worker processes; iterate-until-done with a judge and a turn budget [2] | A judge model can be wrong; keep the turn budget low. |
| Headless coding agents (`claude -p`, `codex exec`, `opencode run`) under launchd or systemd | both | Repo work with the strongest models | Exact flags not re-verified today. |
| OpenClaw cron and heartbeat | both | Similar to Hermes | Not re-verified in detail today. |

What launchd and systemd do not give you is uniform health reporting across jobs. That is gap 8 in section 7.

### 6.2 Persistence, memory and checkpoints

- Hermes Agent: session database with full-text search, agent-curated memory, optional Honcho user modelling, checkpoints and rollback, session rewind (v0.23.0) [1][2]. Honcho is AGPL-3.0 [17].
- For unattended repo work the durable state should be files and git, not model memory: a run directory per job with inputs, the prompt, the model and quantization, tool transcripts, outputs and exit status.
- Use git worktrees or a bare mirror per job so a failed run cannot dirty a working tree. Hermes documents worktree support [2].

### 6.3 Guardrails for jobs that touch git remotes

Ordered from strongest to weakest. Use several.

1. **Credential scope.** A fine-grained GitHub token limited to the specific repos, with contents read-only for triage jobs. For jobs that must write, a separate token that can push only to a bot-owned fork and open pull requests. Never your main `gh` login. A separate bot account is cleaner still.
2. **Server-side rules.** Branch protection or rulesets on the default branch: no direct pushes, no force pushes, required review. This holds even if the agent misbehaves.
3. **No credentials in the sandbox.** Run the agent in a container or under `srt` with no token; a wrapper outside the sandbox takes the resulting branch or patch file and opens the PR.
4. **Local git config.** A `pre-push` hook that rejects non-fast-forward pushes and any push to protected branch names; `receive.denyNonFastForwards` on local mirrors; remotes configured with a push URL that points nowhere for read-only jobs.
5. **Command approval.** Hermes `cron_mode: deny` and command allowlists; OpenClaw tool deny policies [3][7]. These depend on pattern matching and are the weakest layer.
6. **Output contract.** Every job ends in one of: a Markdown report, a patch file, or a draft PR. Nothing merges without a human.

For pulling and triaging upstream changes across forks, the right approach is: `git cherry` for patches not yet upstream, `git merge-tree` for a clean-merge check with no working tree, the model labelling only.

### 6.4 Supervising overnight runs

- A morning digest: one message listing each job, its status, duration, tokens used, and links to the report or PR. Hermes cron can deliver to any configured channel [2]. OpenJarvis ships a morning-digest preset [19].
- Hard limits: wall-clock timeout per job, maximum turns, and for hosted models a spend cap. Hermes v0.23.0 added hard spending limits at the gateway and per-delegation cost reporting [1].
- A dead-man check: if the digest does not arrive, that is the alert.
- Keep transcripts. When a local model claims it ran tests, the transcript is the only way to check.
- Start every new job type in report-only mode for a week before allowing it to open PRs.

### 6.5 Cost and energy

Using Apple's wall-power figures [26] and an assumed electricity price of 0.17 USD per kWh (my assumption; substitute the real rate):

| Scenario | Energy per year | Cost per year |
| --- | --- | --- |
| M4 mini idle all year (4 W) | 35 kWh | about 6 USD |
| M4 mini at maximum 8 h per night, idle otherwise | about 213 kWh | about 36 USD |
| M4 Pro mini idle all year (5 W) | 44 kWh | about 7 USD |
| M4 Pro mini at maximum 8 h per night, idle otherwise | about 438 kWh | about 74 USD |

Maximum draw is an upper bound; inference load is normally below it. Energy is not the constraint. The real costs are the hardware, your time, and hosted tokens for the hard steps. I did not verify hosted model prices today and so give none. I also did not verify current Mac mini prices; the M4 generation is no longer the current one.

### 6.6 Fine-tuning and training on M4 minis

What the tooling does (verified from mlx-lm's `LORA.md`) [52]: `mlx_lm.lora` supports LoRA, DoRA and full fine-tuning; pointing it at a quantized model gives QLoRA automatically; `mlx_lm.fuse` merges adapters and can export GGUF for a limited set of architectures; memory is reduced with smaller batch size, fewer layers and gradient checkpointing. MLX-LoRA-Studio is a native Mac GUI for the same (MIT, 290 stars) [17].

Data points, all secondary and none on a Mac mini specifically [53]:

- Gemma 4 E2B, 600 iterations, LoRA on 8 layers: about 4 GB peak, about five minutes.
- Qwen 3.5 9B on an M4 Max 64 GB: about two hours for 600 iterations on a small dataset.
- Sizing guidance conflicts between guides. One says 16 GB handles 7 to 8B QLoRA; another says to stay at about 3B on 16 GB.

A working example of what a small adapter buys: Speakrail ships a Gemma 4 E4B LoRA that makes turn-taking decisions in one token per event [44].

Realistic scale on the minis, as my estimate from the above and from the bandwidth gap between an M4 Max and a base M4:

| Machine | Feasible | Not feasible |
| --- | --- | --- |
| M4 16 to 24 GB | QLoRA adapters on 2 to 9B models, hundreds to a few thousand examples, minutes to a few hours | Anything 12B and up at useful sequence lengths |
| M4 32 GB | QLoRA up to about 12B; 9B comfortably | 27B and up |
| M4 Pro 64 GB | QLoRA on 12 to 27B with short sequences and small batches, overnight | Full fine-tunes; MoE 35B-class adapters are untested territory |

Training from scratch or full fine-tuning of anything useful is not a mini workload. The sensible use here is narrow: train a small adapter on gold labels for one narrow task, such as triage labelling, so a 4 to 9B model does it at high speed, and measure it against a rules baseline. Rent a GPU for anything bigger.

---

## 7. Recommendation

### 7.1 Three reference architectures

**A. Single M4 mini, 16 to 32 GB: the assistant box**

| Layer | Choice | Why |
| --- | --- | --- |
| Agent | Hermes Agent, latest stable (v0.23.x), gateway as a LaunchAgent | Closest single project; one gateway serves every client [1] |
| Runtime | llama.cpp `llama-server` (or Hermes's managed llama.cpp) | Best tool-call completion and flat memory in the only controlled benchmark found [12] |
| Chat and voice model | 16 GB: Gemma 4 E4B or Qwen 3.5 9B at 4-bit. 24 to 32 GB: Gemma 4 26B-A4B at 4-bit or LFM2.5-24B-A2B | Speed first for voice; see 2.5 |
| Work model | 32 GB only: Qwen 3.6-35B-A3B at 4-bit with 32K context, swapped in for jobs | First credible local agent tier |
| STT | Parakeet TDT v3 through FluidAudio or mlx-audio | 0.10 s on an M4 [42] |
| TTS | Kokoro through Kokoro-FastAPI or mlx-audio; Pocket TTS as the CPU-only alternative | Local, fast, OpenAI-compatible so Hermes can use it [3] |
| Wake word | Hermes's openWakeWord "hey hermes" | Built in, on-device [4] |
| Integrations | `imsg`, `remindctl`, Notes skill; IMAP with drafts-only for mail; CalDAV for calendar | See section 5 |
| Long-horizon | Hosted models through Claude Code or Codex CLI on a schedule, PR-only | The local model at this size is not reliable for multi-hour work |
| Cost | Hardware; about 6 to 36 USD a year in electricity at the assumed rate; hosted tokens for the nightly jobs | |
| Will not work well | Unattended coding on the local model; anything needing more than about 32K context on 16 to 24 GB; two models resident at once below 32 GB | |

**B. One M4 Pro 64 GB mini as LAN inference and agent hub, thin clients on Mac and Linux**

| Layer | Choice | Why |
| --- | --- | --- |
| Runtime | oMLX as the primary server on the LAN, with llama.cpp kept available as the fallback for any model whose tool calls fail on MLX | Pinning, auto-swap, SSD KV cache and batching suit a shared server; both passed all SiliconBench gates [36][12] |
| Pinned model | Gemma 4 E4B or a 9B for voice and quick chat | Sub-second first token |
| Work model | Start with Qwen 3.6-35B-A3B at 8-bit; evaluate Qwen 3.8-27B at 6-bit and Qwen3-Coder-Next at Q4 against it | Fast MoE first; the 27B is slower, and whether it is better is for the evaluation to decide; Coder-Next needs nearly all 64 GB |
| Agent | Hermes Agent gateway on the Pro mini, because Apple data lives there; webapp and desktop clients from other machines | v0.23.0 architecture [1] |
| Other minis | Each runs its own small server for a dedicated role (voice satellite with local STT and TTS, a second agent worker). No cluster. | Clustering gave about 1.3x on decode and needs Thunderbolt 5 with RDMA [12] |
| Linux clients | Hermes desktop, TUI or browser pointed at the gateway; any OpenAI-compatible tool pointed at the mini's endpoint; local sandboxed shell tools on the Linux box | Linux on M4 has no GPU inference [40][41] |
| Messages | `imsg` or BlueBubbles on the Pro mini; blueferry on a roaming Linux laptop | Section 5.4 |
| Long-horizon | Local model for triage, summarising, labelling, first drafts; hosted for multi-file code changes | Section 2.6 |
| Cost | Requires an M4 Pro with 64 GB. If you do not have one, this is a purchase, and current-generation pricing was not checked. Electricity about 7 to 74 USD a year. | |
| Will not work well | Several concurrent heavy agents on one 64 GB machine; 256K contexts at interactive speed; expecting parity with hosted frontier models | |

**C. Hybrid local plus hosted (recommended)**

This is A or B with an explicit routing rule, and it is what the evidence supports regardless of which minis you have.

| Class of work | Route | Reason |
| --- | --- | --- |
| Voice turns, quick questions | Small local model, pinned | Latency and privacy |
| Anything that reads messages, mail, calendar, notes | Local model only | Private data stays in the house |
| Drafting replies | Local model writes to a review queue; nothing sends without approval | Section 5.3 |
| Upstream triage, labelling, digests | Local model plus deterministic rules, report-only | The model labels, code decides; checkable |
| Nightly repo clean-ups, multi-file changes, investigations | Hosted frontier model through Claude Code or Codex CLI in a sandbox, PR-only, with a spend cap | Local models that fit in 64 GB are well behind on long-horizon work |
| Fallback when hosted is down or over budget | Local work model, report-only | Degrade safely |

Hermes Agent expresses this with a main model, `fallback_providers`, `cron.model` and per-job pins [2]. Components per layer are as in A or B.

Why C: it does not depend on how much RAM the minis have, and it puts the unreliable component, the local model, only where its output is cheap to check.

### 7.2 First-weekend build plan

Saturday morning: foundations (one mini)

1. Record chip and RAM of each mini with `system_profiler SPHardwareDataType`. This decides between A and B.
2. Check free disk space before downloading anything. The larger models in section 2.5 are 16 to 52 GB of weights each.
3. Install the current stable Hermes Agent release and confirm `hermes doctor` passes.
4. Download two models only: one small chat model and one work model sized for the tier (section 2.5). Use vendor or Unsloth builds at 4-bit or better.
5. Start `llama-server` with explicit context, prompt caching on and an API key, under launchd, with a health check that alerts on failure.

Saturday afternoon: pick the model with evidence

6. Build a small evaluation set for your own task, with adjudicated gold labels and a rules baseline, and score each candidate on your production runtime at the quantization you will use. Record tokens per second, time to first token and memory alongside accuracy. This produces real, reproducible numbers for your own hardware and task.
7. Point Hermes at the local endpoint and run a short scripted tool-calling check (ten tasks that require real tool use, including "do not call a tool"). Reject any model and quantization that fakes a result.

Sunday morning: voice and integrations

8. Voice: enable Hermes voice mode with local STT; run Kokoro-FastAPI or mlx-audio as the TTS endpoint and set Hermes's TTS provider to it instead of the Edge default; enable the wake word. Measure time from end of speech to first audio with a stopwatch script and write it down.
9. Integrations, read-only first: `remindctl`, Notes skill, CalDAV calendar, IMAP inbox. For mail, give the agent IMAP without SMTP so it can only leave drafts.
10. Messages: install `imsg`, grant access to the smallest host process possible, enable read and watch only. Build the review queue as a plain folder of Markdown drafts with an `approve` script that is the only caller of `imsg send`.

Sunday afternoon: unattended work

11. Create a fine-grained read-only GitHub token and a bot-fork write token. Add the `pre-push` hook and branch rules.
12. Schedule two jobs: a daily read-only upstream triage job (local model, report-only) and one nightly repo clean-up (hosted model in `srt` or a container, draft PR only, spend cap, wall-clock timeout).
13. Add the morning digest and the dead-man check.
14. Write down what failed, and compare the list with the gaps in section 7.3.

### 7.3 Gaps that no existing project fills

These are the justification for a new project and site. Each is stated as something I looked for and did not find; an absence of search results is not proof that nothing exists.

1. **A scoped permission broker for personal data.** Small single-purpose helpers that hold one narrow OS grant each (Messages read, Messages send-with-approval, Mail drafts, Calendar) and expose a minimal, logged API to any agent. Today the agent's host process holds Full Disk Access and Automation rights, and scoping is done by prompts and allowlists. Apple's 27.3 changes make this urgent [9][10].
2. **A cross-agent review queue.** A standard "draft, approve, send" outbox for messages, mail and PRs, with enforcement outside the model, usable from Hermes, OpenClaw or a coding agent. Only fragments exist (Apple2Agent's mail approval, exec approval prompts).
3. **Linux parity for personal data.** A permissioned bridge for calendar, contacts, notes and messages on Linux, including on Hyprland-based desktops, and an agent adapter for blueferry.
4. **One assistant across macOS and Linux with the Mac as data hub.** A documented, tested topology: gateway and Apple data on a mini, Linux and Mac thin clients, voice satellites, with authentication. The pieces exist in Hermes v0.23; the reference deployment does not.
5. **An honest, reproducible model-selection harness for personal-agent tasks on Apple Silicon.** Per RAM tier, per runtime, per quantization, measuring tool-call correctness, refusal to fake results, time to first token with and without cache, and memory. SiliconBench covers serving engines on an M5 Pro and one pair of M4 Pros [12]; the public indexes are mostly estimates [30].
6. **Measured voice latency on M4-class Macs.** I found component numbers and an RTX 4090 end-to-end figure, but no published end-to-end measurement for a cascaded or full-duplex assistant on an M4 mini.
7. **A native macOS front end that bridges App Intents and Shortcuts to a local agent.** macOS 27 allows a third-party model behind Apple's session API and lets Siri reach app content through schemas [20][21]. An open project that exposes a self-hosted agent's actions as App Intents, and system intents as agent tools, would give OS-enforced consent for free.
8. **A local-first supervisor for unattended jobs.** Run directories, transcripts, budgets, digests, dead-man alerts and a uniform health view across launchd and systemd jobs and across harnesses. Each agent has its own partial version.
9. **Guardrail templates for git work.** Ready-made token scopes, hooks, rulesets and wrapper scripts for "read-only triage" and "PR-only changes", tested against several agents.
10. **Linux inference on M3 and M4.** Blocked on a Vulkan driver. omarchy-mlx has a tester kit that asks for M4 hardware.
11. **Small task-specific adapters as a supported workflow.** Collect traces, label with a hosted model, train a LoRA with MLX on a mini, evaluate, deploy to the pinned small model. OpenJarvis points in this direction [19]; there is no packaged path for a home setup.

A project that picks Hermes Agent as the base and delivers items 1, 2, 4, 5 and 8, with a site that publishes the measurements, would be new and useful. Items 3 and 7 are the larger builds.

---

## What I could not verify, and where sources conflict

- M4 base memory bandwidth, Thunderbolt version and RAM configurations: from prior knowledge, not re-checked.
- Exact output throughput for Qwen 3.8-27B and Qwen 3.6-35B-A3B at 4-bit on the M5 Pro in SiliconBench: those are in a figure; the extracted text shows axes topping out near 6 tok/s for the dense model and 30 tok/s for the MoE under agent prompts, which I could not read precisely.
- Most token-per-second rows for the base M4 are estimates from a bandwidth model, and one measured study found such estimates 1.5 to 2x optimistic under load [29][30].
- Ollama's MLX default: secondary sources disagreed on the version. The official v0.40.0 release notes (2026-09-25) settle it [38]. SiliconBench's negative Ollama findings predate that release (August builds) and may no longer hold.
- Hermes Agent feature descriptions come from the docs at v0.21.4 (2026-09-26) plus the v0.22.0 and v0.23.0 release notes. I did not read the v0.23.2 docs in full.
- OpenClaw: I did not confirm whether its macOS speech recognition is on-device, the current state of its Linux app, or its cron feature in detail.
- Feature claims for Open WebUI, AnythingLLM, Jan, Khoj, Onyx, LocalAI, Letta, OpenHands, Goose scheduling, LM Studio's headless mode and Msty were not checked feature by feature today.
- Apple: open-sourcing of the Foundation Models core and its Linux support; the Siri "Extensions" and model delegation reports; SiriKit deprecation. All secondary. Apple's own page confirms only the LanguageModel protocol and App Intents schemas [20].
- No hosted frontier scores on Terminal-Bench 2.1 from a primary source; the GLM-5.3 figure of 88.2 is cited by one secondary page [27].
- Tool-calling benchmark figures for Qwen 3.6 and Gemma 4 come from secondary summaries of vendor cards and one arXiv paper I did not read [32][33].
- Kokoro latency on Apple Silicon: one unverified M5 Max figure [45].
- METR doubling-time figures conflict across secondary sources; I did not use them.
- Hosted model prices and current Mac mini prices were not checked.
- The electricity price is an assumption.

---

## Sources

Dates are publication or release dates where known; "accessed" means read on 2026-11-18.

1. Hermes Agent releases v0.22.0 (2026-10-13), v0.23.0 (2026-11-05), v0.23.2 (2026-11-16). https://github.com/NousResearch/hermes-agent/releases (accessed through the GitHub API)
2. Hermes Agent documentation: cron, goals, heartbeat, kanban, fallback providers, checkpoints. Read at v0.21.4 canary, commit 40989563ec, 2026-09-26. Online: https://hermes-agent.nousresearch.com/docs/
3. Hermes Agent documentation: security, TTS, computer use, BlueBubbles, Photon, email, bundled Apple skills (`skills/apple/`). Same version, 2026-09-26.
4. Hermes Agent documentation: voice mode and wake word. Same version, 2026-09-26.
5. Hermes Agent documentation: local models. Same version, 2026-09-26.
6. OpenClaw README. https://github.com/openclaw/openclaw (accessed)
7. OpenClaw docs: sandboxing, https://docs.openclaw.ai/gateway/sandboxing ; macOS app, https://docs.openclaw.ai/platforms/macos (accessed)
8. OpenClaw docs: local models. https://docs.openclaw.ai/gateway/local-models (accessed)
9. MacRumors, "Apple Announces 'Full Disk Access' Changes on macOS Due to AI Agents", 2026-10-02. https://macrumors.com/2026/10/02/apple-announces-macos-full-disk-access-changes
10. MacRumors, "macOS 27.3 Warns Against Giving AI Apps Full Mac Control", 2026-11-16. https://macrumors.com/2026/11/16/macos-27-3-full-desk-access
11. Linux desktop agent bridges, search results accessed 2026-11-18: Deskbrid https://mcpservers.org/servers/coe0718/deskbrid ; GNOME Desktop MCP https://mcpservers.org/servers/sbuysse/gnome-desktop-mcp ; mcp_dbus health check https://castrojo.github.io/jorgepilot/reports/other/mcp-dbus-health-check ; Newelle MCP support https://www.phoronix.com/news/GNOME-AI-Newelle-MCP-Server ; cua on Linux https://cua.ai/blog/inside-linux-computer-use
12. Zhang et al., "SiliconBench: Speed, Memory, and Fidelity for LLM Serving on Unified-Memory Desktops", arXiv:2609.19169, 2026-09-12. https://arxiv.org/abs/2609.19169 (PDF read in full text; Tables 3 to 10, sections 6.1 to 6.4)
13. "Long-Horizon-Terminal-Bench 2.0", arXiv:2610.14146, 2026-10-09. https://arxiv.org/abs/2610.14146 (abstract only)
14. Saad-Falcon et al., "OpenJarvis: Personal AI, On Personal Devices", arXiv:2605.17172, 2026-05-16. https://arxiv.org/abs/2605.17172 (abstract only)
15. Hugging Face model listings by search and by author, accessed through the API 2026-11-18. https://huggingface.co/models ; https://huggingface.co/NousResearch
16. Nous Research, Arete-27B model card, created 2026-11-06. https://huggingface.co/NousResearch/Arete-27B
17. GitHub API repository and release metadata for all repos named in this report, accessed 2026-11-18. https://api.github.com/repos/OWNER/NAME
18. LM Studio CLI README. https://github.com/lmstudio-ai/lms (accessed)
19. OpenJarvis README. https://github.com/open-jarvis/OpenJarvis (accessed)
20. Apple, "WWDC26 macOS guide". https://developer.apple.com/wwdc26/guides/macos/ (accessed; June 2026)
21. Apple, mlx-swift-lm and its MLXFoundationModels library. https://github.com/ml-explore/mlx-swift-lm ; Apple WWDC26 sessions 241 and 339, https://developer.apple.com/videos/play/wwdc2026/241/ and https://developer.apple.com/videos/play/wwdc2026/339/ (search summaries; not viewed)
22. Apple WWDC26 session 240, "Build intelligent Siri experiences with App Schemas", https://developer.apple.com/videos/play/wwdc2026/240/ ; SiriKit deprecation per https://www.stork.ai/blog/wwdc-2026-graded-what-apple-shipped-ios-27 (secondary)
23. MacRumors, "Apple's Siri AI Can Be Swapped Out for Claude, ChatGPT, Code Shows", 2026-09-14. https://macrumors.com/2026/09/14/siri-can-be-swapped-out-for-chatgpt-claude (search summary)
24. Apple MCP servers: https://github.com/JonathanRReed/Apple-MCPs ; https://github.com/griches/apple-mcp ; https://github.com/gabythiesse/apple-mcp-swift ; https://github.com/aheusingfeld/AppleMCP ; https://github.com/AndreLYL/Apple2Agent (metadata accessed; READMEs via search summary)
25. imsg README, v0.21.1, 2026-11-16. https://github.com/openclaw/imsg ; remindctl https://github.com/openclaw/remindctl
26. Apple Support, "Mac mini power consumption and thermal output". https://support.apple.com/en-us/103253 (accessed)
27. Zach Rattner, "Best local LLMs for agentic coding on Apple silicon", undated, 2026. https://zachrattner.com/projects/ai-mac-cluster/coding-models (secondary; speeds calculated or community)
28. llmcheck.net, "Best Local LLM for Coding on Mac", updated 2026-11-14. https://llmcheck.net/blog/best-local-llm-for-coding-mac/ (secondary; labels each figure as sourced, estimated or community)
29. scott-crenshaw, "Local LLM Feasibility Study: Mac Mini M4 (24 GB)", last push 2026-03-09. https://github.com/scott-crenshaw/local-llm-feasibility-study (measured, stated hardware)
30. llmcheck.net, "Apple Silicon LLM Benchmarks", updated 2026-11-14. https://llmcheck.net/benchmarks (secondary; first half of the page read)
31. Rost Glukhov, "Best LLMs for OpenCode, tested locally", undated, 2026. https://www.glukhov.org/ai-devtools/opencode/llms-comparison/ (secondary; 16 GB VRAM PC)
32. InsiderLLM, "Best Local LLMs for Function Calling". https://insiderllm.com/guides/function-calling-local-llms/ (search summary)
33. "BekchiAI: Measuring, Observing, and Controlling LLM Agents in One Click", arXiv:2608.26867. https://arxiv.org/pdf/2608.26867 (search summary; not read)
34. METR, "Frontier Risk Report (February to March 2026)", 2026-05-19. https://metr.org/blog/2026-05-19-frontier-risk-report/ ; Epoch AI figure as reported in https://www.druva.com/blog/open-models-crossing-frontier-or-expensive (search summaries)
35. llama.cpp v1.0.0 release notes, 2026-11-13. https://github.com/ggml-org/llama.cpp/releases/tag/v1.0.0
36. oMLX README, v0.8.0, 2026-11-18. https://github.com/jundot/omlx
37. vllm-metal README, v0.33.0, 2026-11-04. https://github.com/vllm-project/vllm-metal
38. Ollama v0.40.0 release notes, 2026-09-25. https://github.com/ollama/ollama/releases/tag/v0.40.0
39. AppleInsider, "AI calculations on Mac cluster gets a big boost from new RDMA support on Thunderbolt 5", 2025-12-20. https://appleinsider.com/articles/25/12/20/ai-calculations-on-mac-cluster-gets-a-big-boost-from-new-rdma-support-on-thunderbolt-5 (search summary)
40. Asahi Linux, "M4 Series Feature Support". https://asahilinux.org/docs/platform/feature-support/m4/ (accessed; page undated)
41. "Building a Linux GPU Driver for the M4 Mac mini in One Month, Mostly With Coding Agents", 2026-10-24. https://dev.to/theeromi/building-a-linux-gpu-driver-for-the-m4-mac-mini-in-one-month-mostly-with-coding-agents-2pkm
42. Konrad Sierzputowski, "How I benchmarked on-device speech-to-text on Apple silicon (Whisper vs Parakeet)", run 2026-08-22, posted 2026-10-13. https://dev.to/konrad_sierzputowski_c86a/how-i-benchmarked-on-device-speech-to-text-on-apple-silicon-whisper-vs-parakeet-dne
43. Moonshine README, v0.1.6, 2026-11-06. https://github.com/moonshine-ai/moonshine
44. Speakrail README, last push 2026-11-09. https://github.com/speakrail/speakrail
45. Contra Collective, "Kokoro vs Piper vs XTTS v2: Local Text to Speech on M5 Max (2026)". https://contracollective.com/blog/kokoro-vs-piper-vs-xtts-local-text-to-speech-m5-max-2026 (search summary; unverified)
46. Kyutai, Pocket TTS README. https://github.com/kyutai-labs/pocket-tts
47. mlx-audio README, v0.6.6, 2026-11-16. https://github.com/Neywa-Labs/mlx-audio ; FluidAudio README, v0.18.3, 2026-11-07. https://github.com/FluidInference/FluidAudio
48. "Building a Local Voice AI Stack: Whisper + Ollama + Kokoro TTS on Apple Silicon". https://dev.to/xadenai/building-a-local-voice-ai-stack-whisper-ollama-kokoro-tts-on-apple-silicon-eo0 (search summary; stage numbers are the author's estimates)
49. macOS agent sandboxing write-ups, 2026: https://importstatic.com/ai/sandbox-coding-agent-macos ; https://www.metasimple.org/2026/07/29/coding-agent-sandboxing-pitfalls-on-macos.html ; https://gist.github.com/wincent/2752d8d97727577050c043e4ff9e386e ; https://www.infralovers.com/blog/2026-02-15-sandboxing-claude-code-macos/ (search summaries)
50. Anthropic Sandbox Runtime README. https://github.com/anthropics/sandbox-runtime
51. NanoClaw README. https://github.com/nanocoai/nanoclaw
52. mlx-lm, `mlx_lm/LORA.md`, v0.32.2, 2026-10-16. https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md
53. MLX fine-tuning write-ups: https://medium.com/@able_wong/part-3-fine-tuning-gemma-4-on-a-mac-mini-and-what-the-results-taught-me-4200ce5523e2 ; https://willitrunai.com/blog/qwen-3-5-mlx-apple-silicon-guide (search summaries)

Public repositories read through `gh` on 2026-11-18: techmore/omarchy-mlx-upstream (README; a fork of joshuaswarren/omarchy-mlx) and its upstream `docs/ENGINES.md`, techmore/omarchy-ane (README; a fork), techmore/blueferry (README; a fork of erikwb/blueferry).