# FAQ

**What is RedForge?**
A local AI security laboratory. It runs a library of adversarial prompts and an
800-case benchmark against a model you host locally, then produces a scored
security report with findings and recommendations.

**Does RedForge send my data anywhere?**
No. By default everything — models, prompts, and findings — stays on your
machine. Nothing is sent to a cloud service. The only exception is if *you*
configure a cloud provider (e.g. OpenAI), in which case prompts go to that
provider's API using your own key.

**Do I need an API key?**
Not for local runtimes (Ollama, LM Studio, llama.cpp, vLLM). Cloud providers need
their own API key, which you set in the environment. RedForge never stores or
logs keys. See [providers.md](providers.md).

**Which runtimes are supported?**
Ollama (default), LM Studio, llama.cpp, and vLLM locally; OpenAI, Anthropic,
Gemini, Groq, and OpenRouter as cloud providers. Switch from the Runtime page or
with `REDFORGE_RUNTIME_PROVIDER`.

**Which model should I use?**
RedForge's onboarding recommends models that fit your hardware (based on RAM and
VRAM). A 7–8B model such as `llama3.1:8b` is a good general starting point.

**Can I download models from within RedForge?**
Yes. Onboarding can pull recommended models through your local runtime, with a
progress bar. You can also use your runtime directly (`ollama pull <model>`).

**Do I need Node.js?**
No. Node.js is only used to build the interface during development. Installed
releases ship a prebuilt UI and run with Python and a runtime only.

**Is RedForge secure to run?**
It binds to `127.0.0.1` and is reachable only from your machine by default. It
has no authentication, so do not expose it to a network you don't trust. Binding
to a non-local address prints a warning first.

**Where is my data stored?**
Evaluation history lives in a local SQLite database; settings, logs, and the
runtime environment live under `~/.redforge` (or the install directory).
`redforge uninstall` preserves this data unless you pass `--purge`.

**How do I update?**
`redforge update` — it checks GitHub Releases, verifies the download's checksum,
preserves your history and settings, and rolls back on failure.

**How do I report a problem?**
Run `redforge diagnose` and share the resulting `diagnostics.zip` — it contains
system, runtime, and log details with all secrets redacted. See
[troubleshooting.md](troubleshooting.md).

**Is it open source?**
Yes, under the MIT license.
