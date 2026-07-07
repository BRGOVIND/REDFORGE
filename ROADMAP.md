# Roadmap

RedForge v1.0.0 is a complete local AI-security lab. What's forging next:

## Near term
- **Live token streaming** — surface the runtime's streaming engine as SSE/WebSocket
  so the terminal shows tokens as they generate.
- **Cancellation through sessions** — propagate a cancellation token into the
  in-flight generation so pause/cancel is instant (today it stops at task boundaries).
- **CI release pipeline** — auto-build the Windows `.exe` and Linux AppImage on tag
  and attach them to GitHub Releases.

## Mid term
- **Second runtime provider** — an OpenAI-compatible `Provider` (unlocks LM Studio,
  vLLM, llama.cpp) with no changes above the provider layer.
- **Bundled Python runtime** in installers so end users need only Ollama.
- **macOS `.dmg`** (notarized).

## Longer term
- Enterprise features (team workspaces, audit trails).
- Fine-tuning workspace — turn findings into training signal.
- Shared research platform (benchmarks, leaderboards, reproducible studies).

Ideas and requests welcome — open an issue.
