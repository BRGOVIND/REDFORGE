# FAQ

**Does RedForge send my data anywhere?**
No. Everything — prompts, responses, models, results — stays on your machine.
There is no cloud service and no API key.

**Do I need Node.js?**
No. Node.js is only used to build the frontend during packaging. The released app
is a single Python process that serves the built UI. End users need **Python 3.11+
and Ollama**.

**Which models can I test?**
Any model you've pulled in Ollama (`ollama list`). Start with `qwen3:8b`,
`llama3`, `gemma`, or `mistral`.

**Do I need a GPU?**
No, but it's much faster. Without one, evaluations run on CPU — use a smaller
model or the Quick Scan profile. See [GPU support](gpu-support.md).

**How long does an evaluation take?**
Quick Scan is a few minutes; Standard is 5–20; Thorough/Exhaustive can be much
longer. The New Evaluation page shows an estimate before you start.

**Can I run more than one model?**
Yes — the Comparative profile evaluates several models against the same cases and
produces a leaderboard.

**Where are my reports?**
In the app under **Reports**, and exportable as JSON / Markdown / PDF. Report data
is stored in the local database.

**Is it multi-user / networked?**
No — it's single-user and localhost-only by design (no authentication). Don't
expose it to the internet as-is.

**How do I update?**
`redforge update` (from a git checkout), or download the newest
[release](https://github.com/BRGOVIND/REDFORGE/releases).

**Is it open source?**
Yes — MIT licensed.
