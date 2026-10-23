# RedForge v2.1.0 — Release Notes

> Draft candidate only. Do not publish until the remaining release gates in
> [the audit](docs/release-readiness-audit.md) are complete.

**RedForge is a local-first AI engineering platform.** Version 2.1.0 adds
optional LLM tracing, prompt versioning and privacy controls, model comparisons
and routing, cost estimates and budgets, anomaly alerts and trace feedback,
plus reviewed security cases and evidence-only release gates.

Existing local projects and desktop workflows remain supported. New migrations
are additive; back up the local database before upgrading.

## New in v2.1.0
- **Traces** — project ingestion tokens, SDK wrappers, a local explorer, and
  separate capture controls. Prompt and response bodies are off by default.
- **Prompt registry** — drafts, immutable published versions, diffs, activation
  of older versions, and version links to evaluations and traces.
- **Model decisions** — comparison records, explicit routing policies, operator
  prices, cost reports, and soft or hard estimated budgets. Estimates are not
  provider invoices or guaranteed spend caps.
- **Health and feedback** — bounded local anomaly alerts and a reviewed path
  from sanitized production traces to evaluation cases.
- **Security and release review** — trace-derived candidates require review;
  release gates assess evidence but do not deploy or roll back code.

## Install
Download the installer for your operating system from the GitHub release page.
Source-archive users can run `install.cmd` (Windows) or `./install.sh`
(Linux/macOS), then `start.cmd` or `./start.sh`. This path requires Python
3.11+ and, in strict mode, preinstalled dependencies or an offline wheelhouse.
For local inference, configure a compatible runtime such as Ollama.

Follow the on-screen setup. Bring an already installed local runtime and model;
strict mode does not download them. Then explore the sidebar (or press
**⌘K / Ctrl-K**).

## Requirements
- **Python 3.11+** and one local **runtime** (Ollama recommended; LM Studio,
  llama.cpp, vLLM also work). Node.js is **not** required to run.
- **Real GPU training** additionally needs a CUDA GPU and the Unsloth stack
  (`unsloth`, `peft`, `transformers`, `bitsandbytes`, `trl`). Without it, the
  Training Lab runs a dependency-free **simulation** so you can learn the flow.

## Trust model
RedForge's desktop management API is **single-user, localhost-oriented, and
unauthenticated by design**. SDK trace ingestion uses local project tokens.
Optional trace capture is stored locally under a project policy, not sent to
a RedForge cloud service. The default strict profile blocks RedForge-managed
hosted inference, remote trace ingestion, downloads, update checks, and
non-loopback server binding. This is an application policy, not an OS firewall.
**Do not expose RedForge to an untrusted network.** See
[SECURITY.md](SECURITY.md) and the website privacy policy for details.

## Known limitations
- Local project boundaries do not provide multi-user enterprise RBAC.
- Local alert history has no email or webhook notifications by default.
- Estimated budget limits cannot preempt calls made directly to external SDKs.
- Release gates do not deploy, invoke production tools, or execute rollback.
- Live training progress and background jobs do not survive a backend restart;
  interrupted jobs are marked `interrupted` on the next start.
