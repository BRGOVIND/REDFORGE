# Quick Start

Five minutes from download to your first security report.

## 1. Start
```bash
redforge start
```
Your browser opens at `http://127.0.0.1:8000`. If it's your first run, the **Setup**
wizard appears.

## 2. Pass the setup checks
The wizard checks Ollama, models, GPU, database, dataset, and runtime — live.
- **Ollama not running?** Run `ollama serve`.
- **No models?** Click a recommended model's copy button and run e.g.
  `ollama pull qwen3:8b`.

When everything is green, click **Launch RedForge**.

## 3. Run an evaluation
1. Go to **New Evaluation**.
2. Pick a **model** and a **profile**:
   - **Quick Scan** — fast sanity check (heuristic).
   - **Standard** — fuller run with an LLM judge and mutations.
   - **Thorough / Exhaustive** — deep, research-grade.
3. Review the estimate (time, RAM, GPU, LLM calls, warnings), then **Start**.

## 4. Watch it live
The **Live** page streams a stage timeline, progress, a running security score,
the event feed, and a real terminal.

## 5. Read the report
When it finishes, open the **Report**: executive summary, overall score, category
scores, top vulnerabilities, and recommendations. Export as **JSON**, **Markdown**,
or **PDF**.

## From the CLI
```bash
redforge models                     # what's installed
redforge evaluate qwen3:8b standard # start an evaluation
redforge status                     # progress
```
