# Local Assistant Stack

A reference stack for a local-first AI assistant on Apple Silicon Mac minis and Linux: what exists, what to run, and the gaps.

Live site: https://techmore.github.io/local-assistant-stack/

## The short answer

The question was whether an open-source, Siri-like assistant exists that runs on local models, reaches your apps with real permissions, and carries long tasks unattended, on Mac minis and Linux.

No single project does this today. Hermes Agent and OpenClaw come close enough that writing a new agent from scratch would be a mistake. What is missing is a permission model enforced outside the agent, a review queue, parity on Linux for personal data, a local model reliable enough for multi-hour unattended work on a 16 to 64 GB machine, and a tested combination of all the layers. The site recommends a hybrid: a Mac mini on macOS as the data and inference hub, a small pinned local model for voice and chat, a local work model for checkable jobs, a hosted model for hard unattended jobs, and Mac and Linux thin clients.

## Status

Research and roadmap; no software yet. The roadmap page lists what this project intends to build. None of it exists.

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
LICENSE               MIT, for code
```

There is no build step. Edit the HTML directly.

## Licenses

Code is under the MIT License (see `LICENSE`). The written content, including everything in `docs/`, is licensed CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), copyright Techmore.

Part of [Techmore](https://techmore.github.io/pages/repos/).
